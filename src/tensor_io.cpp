#include "srcnn/tensor_io.hpp"

#include <cstring>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <limits>
#include <sstream>
#include <stdexcept>

namespace srcnn {
namespace {

[[noreturn]] void format_error(const std::filesystem::path& path,
                               const std::string& message) {
    throw std::runtime_error(path.string() + ": " + message);
}

std::string read_key(std::istream& stream, const std::filesystem::path& path,
                     const std::string& expected) {
    std::string key;
    if (!(stream >> key) || key != expected) {
        format_error(path, "expected field '" + expected + "'");
    }
    std::string value;
    if (!(stream >> value)) {
        format_error(path, "missing value for field '" + expected + "'");
    }
    return value;
}

}  // namespace

void save_tensor_file(const std::filesystem::path& path, const TensorFile& tensor) {
    const auto count = checked_element_count(tensor.shape);
    if (tensor.data.size() != count) {
        throw std::invalid_argument("cannot save tensor: shape requires " +
                                    std::to_string(count) + " elements, got " +
                                    std::to_string(tensor.data.size()));
    }
    if (tensor.name.empty() || tensor.layout.empty()) {
        throw std::invalid_argument("tensor name and layout must not be empty");
    }
    if (path.has_parent_path()) {
        std::filesystem::create_directories(path.parent_path());
    }
    std::ofstream output(path);
    if (!output) {
        throw std::runtime_error("cannot open tensor file for writing: " + path.string());
    }
    output << "SRCNN_TENSOR_V1\n"
           << "name " << tensor.name << '\n'
           << "dtype float32\n"
           << "layout " << tensor.layout << '\n'
           << "ndim " << tensor.shape.size() << '\n'
           << "shape";
    for (const auto extent : tensor.shape) {
        output << ' ' << extent;
    }
    output << "\ncount " << count << "\nchecksum_fnv1a64 "
           << fnv1a64_hex(tensor.data) << "\ndata\n";
    output << std::setprecision(std::numeric_limits<float>::max_digits10);
    for (std::size_t i = 0; i < tensor.data.size(); ++i) {
        output << tensor.data[i] << ((i + 1) % 8 == 0 ? '\n' : ' ');
    }
    if (tensor.data.size() % 8 != 0) {
        output << '\n';
    }
    if (!output) {
        throw std::runtime_error("failed while writing tensor file: " + path.string());
    }
}

TensorFile load_tensor_file(const std::filesystem::path& path,
                            const std::string& expected_layout,
                            const std::vector<std::size_t>& expected_shape) {
    std::ifstream input(path);
    if (!input) {
        throw std::runtime_error("cannot open tensor file: " + path.string());
    }
    std::string magic;
    if (!(input >> magic) || magic != "SRCNN_TENSOR_V1") {
        format_error(path, "invalid magic (expected SRCNN_TENSOR_V1)");
    }
    TensorFile tensor;
    tensor.name = read_key(input, path, "name");
    if (read_key(input, path, "dtype") != "float32") {
        format_error(path, "dtype must be float32");
    }
    tensor.layout = read_key(input, path, "layout");
    if (!expected_layout.empty() && tensor.layout != expected_layout) {
        format_error(path, "layout mismatch: expected " + expected_layout +
                           ", got " + tensor.layout);
    }
    const auto ndim_text = read_key(input, path, "ndim");
    std::size_t ndim{};
    try {
        std::size_t consumed{};
        ndim = std::stoull(ndim_text, &consumed);
        if (consumed != ndim_text.size() || ndim == 0) {
            format_error(path, "invalid ndim");
        }
    } catch (const std::exception&) {
        format_error(path, "invalid ndim");
    }
    std::string shape_key;
    if (!(input >> shape_key) || shape_key != "shape") {
        format_error(path, "expected field 'shape'");
    }
    tensor.shape.resize(ndim);
    for (auto& extent : tensor.shape) {
        if (!(input >> extent) || extent == 0) {
            format_error(path, "invalid or incomplete shape");
        }
    }
    if (!expected_shape.empty() && tensor.shape != expected_shape) {
        std::ostringstream message;
        message << "shape mismatch: expected";
        for (const auto extent : expected_shape) message << ' ' << extent;
        message << ", got";
        for (const auto extent : tensor.shape) message << ' ' << extent;
        format_error(path, message.str());
    }
    const auto count_text = read_key(input, path, "count");
    std::size_t declared_count{};
    try {
        std::size_t consumed{};
        declared_count = std::stoull(count_text, &consumed);
        if (consumed != count_text.size()) format_error(path, "invalid count");
    } catch (const std::exception&) {
        format_error(path, "invalid count");
    }
    const auto required_count = checked_element_count(tensor.shape);
    if (declared_count != required_count) {
        format_error(path, "declared count does not match shape: expected " +
                           std::to_string(required_count) + ", got " +
                           std::to_string(declared_count));
    }
    const auto expected_checksum = read_key(input, path, "checksum_fnv1a64");
    std::string data_key;
    if (!(input >> data_key) || data_key != "data") {
        format_error(path, "expected field 'data'");
    }
    tensor.data.resize(required_count);
    for (std::size_t i = 0; i < required_count; ++i) {
        if (!(input >> tensor.data[i])) {
            format_error(path, "short data: expected " + std::to_string(required_count) +
                               " elements, read " + std::to_string(i));
        }
    }
    std::string trailing;
    if (input >> trailing) {
        format_error(path, "extra data after " + std::to_string(required_count) +
                           " elements");
    }
    const auto actual_checksum = fnv1a64_hex(tensor.data);
    if (actual_checksum != expected_checksum) {
        format_error(path, "checksum mismatch: expected " + expected_checksum +
                           ", computed " + actual_checksum);
    }
    return tensor;
}

void save_chw(const std::filesystem::path& path, const std::string& name,
              const Tensor& tensor) {
    save_tensor_file(path, {name, "CHW", tensor.shape(), tensor.data});
}

Tensor load_chw(const std::filesystem::path& path,
                const std::vector<std::size_t>& expected_shape) {
    const auto file = load_tensor_file(path, "CHW", expected_shape);
    if (file.shape.size() != 3) {
        format_error(path, "CHW tensor must have exactly three dimensions");
    }
    Tensor tensor(file.shape[0], file.shape[1], file.shape[2]);
    tensor.data = file.data;
    return tensor;
}

std::string fnv1a64_hex(const std::vector<float>& values) {
    std::uint64_t hash = 14695981039346656037ULL;
    for (const float value : values) {
        std::uint32_t bits{};
        static_assert(sizeof(bits) == sizeof(value), "float must be 32 bits");
        std::memcpy(&bits, &value, sizeof(bits));
        for (unsigned shift = 0; shift < 32; shift += 8) {
            hash ^= (bits >> shift) & 0xffU;
            hash *= 1099511628211ULL;
        }
    }
    std::ostringstream result;
    result << std::hex << std::setfill('0') << std::setw(16) << hash;
    return result.str();
}

}  // namespace srcnn
