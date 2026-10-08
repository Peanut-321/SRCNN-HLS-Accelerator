#include "srcnn_hls/project_config.hpp"
#include "srcnn_hls/srcnn_hls.hpp"

#include <cstddef>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using srcnn_hls::numeric::data_t;

std::size_t element_count(const srcnn_hls::LayerShape& shape) {
    return static_cast<std::size_t>(shape.channels) * shape.height * shape.width;
}

template <typename T>
bool exact_equal(const T& lhs, const T& rhs) {
    return lhs == rhs;
}

bool exact_equal(const float& lhs, const float& rhs) {
    return std::memcmp(&lhs, &rhs, sizeof(float)) == 0;
}

template <typename T>
std::vector<T> deterministic_values(std::size_t count, int period,
                                    int numerator_offset, int denominator) {
    std::vector<T> values(count);
    for (std::size_t index = 0; index < count; ++index) {
        const int numerator =
            static_cast<int>(index % static_cast<std::size_t>(period)) +
            numerator_offset;
        values[index] = static_cast<T>(
            static_cast<double>(numerator) / static_cast<double>(denominator));
    }
    return values;
}

void require_equal(const char* case_name, const char* layer,
                   const std::vector<data_t>& natural,
                   const std::vector<data_t>& line_buffer) {
    if (natural.size() != line_buffer.size()) {
        throw std::runtime_error(std::string(case_name) + ": " + layer +
                                 " size mismatch");
    }
    for (std::size_t index = 0; index < natural.size(); ++index) {
        if (!exact_equal(natural[index], line_buffer[index])) {
            throw std::runtime_error(
                std::string(case_name) + ": " + layer +
                " first mismatch at flat index " + std::to_string(index) +
                ", natural=" +
                std::to_string(static_cast<double>(natural[index])) +
                ", line_buffer=" +
                std::to_string(static_cast<double>(line_buffer[index])));
        }
    }
}

void run_case(const char* name, int height, int width,
              srcnn_hls::PaddingMode padding_mode) {
    srcnn_hls::NetworkShape shape{};
    if (!srcnn_hls::make_network_shape(height, width, padding_mode, &shape)) {
        throw std::runtime_error(std::string(name) + ": invalid test shape");
    }

    const auto input = deterministic_values<data_t>(
        element_count(shape.input), 9, -4, 16);
    const auto conv1_weights = deterministic_values<data_t>(
        srcnn_hls::config::kConv1OutChannels *
            srcnn_hls::config::kConv1InChannels *
            srcnn_hls::config::kConv1KernelHeight *
            srcnn_hls::config::kConv1KernelWidth,
        7, -3, 32);
    const auto conv1_bias = deterministic_values<data_t>(
        srcnn_hls::config::kConv1OutChannels, 5, -2, 16);
    const auto conv2_weights = deterministic_values<data_t>(
        srcnn_hls::config::kConv2OutChannels *
            srcnn_hls::config::kConv2InChannels,
        7, -3, 64);
    const auto conv2_bias = deterministic_values<data_t>(
        srcnn_hls::config::kConv2OutChannels, 5, -2, 32);
    const auto conv3_weights = deterministic_values<data_t>(
        srcnn_hls::config::kConv3OutChannels *
            srcnn_hls::config::kConv3InChannels *
            srcnn_hls::config::kConv3KernelHeight *
            srcnn_hls::config::kConv3KernelWidth,
        7, -3, 64);
    const auto conv3_bias = deterministic_values<data_t>(
        srcnn_hls::config::kConv3OutChannels, 3, -1, 32);

    std::vector<data_t> natural1(element_count(shape.conv1));
    std::vector<data_t> natural2(element_count(shape.conv2));
    std::vector<data_t> natural3(element_count(shape.conv3));
    std::vector<data_t> buffered1(element_count(shape.conv1));
    std::vector<data_t> buffered2(element_count(shape.conv2));
    std::vector<data_t> buffered3(element_count(shape.conv3));
    std::vector<data_t> replicate1(element_count(shape.conv1));
    std::vector<data_t> replicate2(element_count(shape.conv2));
    std::vector<data_t> replicate3(element_count(shape.conv3));
    std::vector<data_t> oc2_1(element_count(shape.conv1));
    std::vector<data_t> oc2_2(element_count(shape.conv2));
    std::vector<data_t> oc2_3(element_count(shape.conv3));

    const int mode = static_cast<int>(padding_mode);
    if (srcnn_hls::srcnn_hls_top(
            input.data(), conv1_weights.data(), conv1_bias.data(),
            conv2_weights.data(), conv2_bias.data(), conv3_weights.data(),
            conv3_bias.data(), natural1.data(), natural2.data(), natural3.data(),
            height, width, mode) != 0) {
        throw std::runtime_error(std::string(name) + ": natural top failed");
    }
    if (srcnn_hls::srcnn_hls_line_buffer_top(
            input.data(), conv1_weights.data(), conv1_bias.data(),
            conv2_weights.data(), conv2_bias.data(), conv3_weights.data(),
            conv3_bias.data(), buffered1.data(), buffered2.data(),
            buffered3.data(), height, width, mode) != 0) {
        throw std::runtime_error(std::string(name) +
                                 ": line-buffer top failed");
    }

    require_equal(name, "conv1", natural1, buffered1);
    require_equal(name, "conv2", natural2, buffered2);
    require_equal(name, "conv3", natural3, buffered3);

    if (padding_mode == srcnn_hls::PaddingMode::kReplicateSame) {
        if (srcnn_hls::srcnn_hls_line_buffer_replicate_top(
                input.data(), conv1_weights.data(), conv1_bias.data(),
                conv2_weights.data(), conv2_bias.data(), conv3_weights.data(),
                conv3_bias.data(), replicate1.data(), replicate2.data(),
                replicate3.data(), height, width) != 0) {
            throw std::runtime_error(std::string(name) +
                                     ": replicate-only top failed");
        }
        require_equal(name, "replicate-only conv1", buffered1, replicate1);
        require_equal(name, "replicate-only conv2", buffered2, replicate2);
        require_equal(name, "replicate-only conv3", buffered3, replicate3);

        if (srcnn_hls::srcnn_hls_line_buffer_replicate_oc2_top(
                input.data(), conv1_weights.data(), conv1_bias.data(),
                conv2_weights.data(), conv2_bias.data(), conv3_weights.data(),
                conv3_bias.data(), oc2_1.data(), oc2_2.data(), oc2_3.data(),
                height, width) != 0) {
            throw std::runtime_error(std::string(name) +
                                     ": replicate OC2 top failed");
        }
        require_equal(name, "OC2 conv1", replicate1, oc2_1);
        require_equal(name, "OC2 conv2", replicate2, oc2_2);
        require_equal(name, "OC2 conv3", replicate3, oc2_3);
    }
    std::cout << "PASS: " << name << '\n';
}

}  // namespace

int main() {
    try {
        run_case("replicate_13x17", 13, 17,
                 srcnn_hls::PaddingMode::kReplicateSame);
        run_case("zero_13x17", 13, 17,
                 srcnn_hls::PaddingMode::kZeroSame);
        run_case("valid_13x17", 13, 17, srcnn_hls::PaddingMode::kValid);
        run_case("replicate_1x1", 1, 1,
                 srcnn_hls::PaddingMode::kReplicateSame);
        run_case("zero_1x1", 1, 1,
                 srcnn_hls::PaddingMode::kZeroSame);
        run_case("replicate_33x29", 33, 29,
                 srcnn_hls::PaddingMode::kReplicateSame);
        std::cout << "PASS: line-buffer top is exactly equal to natural top\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
