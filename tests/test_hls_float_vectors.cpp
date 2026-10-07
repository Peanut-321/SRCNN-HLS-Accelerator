#include "srcnn_hls/numeric_config.hpp"
#include "srcnn_hls/project_config.hpp"
#include "srcnn_hls/srcnn_hls.hpp"

#include "srcnn/tensor_io.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <vector>

#ifndef SRCNN_PROJECT_ROOT
#error "SRCNN_PROJECT_ROOT must name the repository root"
#endif

namespace {

namespace fs = std::filesystem;

struct VectorCase {
    const char* directory;
    int input_height;
    int input_width;
    bool same_padding;
    std::array<const char*, 3> frozen_checksums;
};

constexpr std::array<VectorCase, 5> kCases = {{
    {"fixed_seed", 13, 17, true,
     {"6807b738e4c115fe", "413ce02698d01ce4", "394f13880e5e1b3a"}},
    {"fixed_seed_valid", 13, 17, false,
     {"c7aeb2508084c20f", "c70eec41d9fa2bef", "fa0c68d6f00d2f52"}},
    {"cosim_33x29", 33, 29, true,
     {"c32162a66186e6e9", "330d13e1afb69123", "948b2c751d85293b"}},
    {"cosim_33x29_valid", 33, 29, false,
     {"246393d72a02da1f", "74e751d9171f98e7", "a4a0d63fb2d9ded6"}},
    {"naive_15x13", 15, 13, true,
     {"c744ff7bdb4694f5", "facab21684224805", "669f44f305b34c92"}},
}};

std::size_t element_count(const srcnn_hls::LayerShape& shape) {
    return static_cast<std::size_t>(shape.channels) *
           static_cast<std::size_t>(shape.height) *
           static_cast<std::size_t>(shape.width);
}

std::vector<std::size_t> as_shape(const srcnn_hls::LayerShape& shape) {
    return {static_cast<std::size_t>(shape.channels),
            static_cast<std::size_t>(shape.height),
            static_cast<std::size_t>(shape.width)};
}

srcnn::TensorFile load_parameter(const fs::path& model_directory,
                                 const char* filename,
                                 const char* layout,
                                 std::vector<std::size_t> shape) {
    return srcnn::load_tensor_file(model_directory / filename, layout, shape);
}

long double rational_value(srcnn_hls::config::PositiveRational value) {
    return static_cast<long double>(value.numerator) /
           static_cast<long double>(value.denominator);
}

void require_declared_range(const char* vector_name, const char* tensor_name,
                            const std::vector<float>& values,
                            long double declared_abs_max) {
    for (std::size_t index = 0; index < values.size(); ++index) {
        const long double value = static_cast<long double>(values[index]);
        if (std::isfinite(value) && std::fabs(value) <= declared_abs_max) continue;
        std::ostringstream message;
        message << vector_name << '/' << tensor_name << " element " << index
                << " exceeds configured |value| <= "
                << static_cast<double>(declared_abs_max) << " (got "
                << values[index] << ')';
        throw std::runtime_error(message.str());
    }
}

std::uint32_t float_bits(float value) {
    std::uint32_t bits = 0;
    static_assert(sizeof(bits) == sizeof(value), "binary32 is required");
    std::memcpy(&bits, &value, sizeof(bits));
    return bits;
}

void require_bitwise_layer(const char* vector_name, const char* layer_name,
                           const char* frozen_checksum,
                           const srcnn_hls::LayerShape& shape,
                           const std::vector<float>& actual,
                           const std::vector<float>& expected) {
    if (actual.size() != expected.size()) {
        throw std::runtime_error(std::string(vector_name) + "/" + layer_name +
                                 ": element-count mismatch");
    }

    const std::string expected_checksum = srcnn::fnv1a64_hex(expected);
    if (expected_checksum != frozen_checksum) {
        throw std::runtime_error(std::string(vector_name) + "/" + layer_name +
                                 ": committed dump no longer matches frozen checksum " +
                                 frozen_checksum + " (got " + expected_checksum + ")");
    }

    const std::string actual_checksum = srcnn::fnv1a64_hex(actual);
    if (actual_checksum == frozen_checksum &&
        std::memcmp(actual.data(), expected.data(),
                    actual.size() * sizeof(float)) == 0) {
        return;
    }

    for (std::size_t index = 0; index < actual.size(); ++index) {
        if (float_bits(actual[index]) == float_bits(expected[index])) continue;
        const std::size_t plane =
            static_cast<std::size_t>(shape.height) * shape.width;
        const std::size_t channel = index / plane;
        const std::size_t within_plane = index % plane;
        const std::size_t row = within_plane / shape.width;
        const std::size_t column = within_plane % shape.width;
        std::ostringstream message;
        message << vector_name << '/' << layer_name
                << ": float path is not bitwise identical at (c,h,w)=("
                << channel << ',' << row << ',' << column << "), expected_bits=0x"
                << std::hex << std::setw(8) << std::setfill('0')
                << float_bits(expected[index]) << ", actual_bits=0x" << std::setw(8)
                << float_bits(actual[index]) << std::dec
                << ", expected_checksum=" << frozen_checksum
                << ", actual_checksum=" << actual_checksum;
        throw std::runtime_error(message.str());
    }

    throw std::runtime_error(std::string(vector_name) + "/" + layer_name +
                             ": checksum mismatch without an element mismatch");
}

void print_gap(const char* vector_name, const char* layer_name,
               long double mac_bound, long double preactivation_bound,
               double observed_abs_max) {
    std::cout << "  " << std::left << std::setw(22) << vector_name << std::setw(7)
              << layer_name << std::right << std::scientific
              << std::setprecision(6) << " mac_bound="
              << static_cast<double>(mac_bound) << " preact_bound="
              << static_cast<double>(preactivation_bound)
              << " observed_abs_max=" << observed_abs_max << " gap=";
    if (observed_abs_max == 0.0) {
        std::cout << "inf (no observed nonzero value)\n";
    } else {
        const long double gap = preactivation_bound / observed_abs_max;
        std::cout << static_cast<double>(gap) << "x\n";
    }
}

void run_case(const fs::path& vector_root, const VectorCase& test_case,
              std::array<double, 3>* aggregate_abs_max) {
    const fs::path directory = vector_root / test_case.directory;
    const fs::path model_directory = directory / "model";
    const fs::path dump_directory = directory / "dumps";

    srcnn_hls::NetworkShape shape;
    if (!srcnn_hls::make_network_shape(test_case.input_height,
                                       test_case.input_width,
                                       test_case.same_padding, &shape)) {
        throw std::runtime_error(std::string(test_case.directory) +
                                 ": HLS shape validation failed");
    }

    const auto input = srcnn::load_tensor_file(
        dump_directory / "input.tensor", "CHW",
        {1U, static_cast<std::size_t>(test_case.input_height),
         static_cast<std::size_t>(test_case.input_width)});
    const auto conv1_weights = load_parameter(
        model_directory, "conv1_weights.tensor", "OIHW", {64, 1, 9, 9});
    const auto conv1_bias =
        load_parameter(model_directory, "conv1_bias.tensor", "O", {64});
    const auto conv2_weights = load_parameter(
        model_directory, "conv2_weights.tensor", "OIHW", {32, 64, 1, 1});
    const auto conv2_bias =
        load_parameter(model_directory, "conv2_bias.tensor", "O", {32});
    const auto conv3_weights = load_parameter(
        model_directory, "conv3_weights.tensor", "OIHW", {1, 32, 5, 5});
    const auto conv3_bias =
        load_parameter(model_directory, "conv3_bias.tensor", "O", {1});

    require_declared_range(test_case.directory, "input", input.data,
                           rational_value(srcnn_hls::config::kInputAbsMax));
    require_declared_range(
        test_case.directory, "conv1_weights", conv1_weights.data,
        rational_value(srcnn_hls::config::kConv1WeightAbsMax));
    require_declared_range(
        test_case.directory, "conv2_weights", conv2_weights.data,
        rational_value(srcnn_hls::config::kConv2WeightAbsMax));
    require_declared_range(
        test_case.directory, "conv3_weights", conv3_weights.data,
        rational_value(srcnn_hls::config::kConv3WeightAbsMax));
    require_declared_range(test_case.directory, "conv1_bias", conv1_bias.data,
                           rational_value(srcnn_hls::config::kConv1BiasAbsMax));
    require_declared_range(test_case.directory, "conv2_bias", conv2_bias.data,
                           rational_value(srcnn_hls::config::kConv2BiasAbsMax));
    require_declared_range(test_case.directory, "conv3_bias", conv3_bias.data,
                           rational_value(srcnn_hls::config::kConv3BiasAbsMax));

    std::vector<float> diagnostic_conv1(element_count(shape.conv1));
    std::vector<float> diagnostic_conv2(element_count(shape.conv2));
    std::vector<float> diagnostic_conv3(element_count(shape.conv3));
    srcnn_hls::AccumulatorObservations observations{};
    if (!srcnn_hls::run_srcnn_natural(
            input.data.data(), conv1_weights.data.data(), conv1_bias.data.data(),
            conv2_weights.data.data(), conv2_bias.data.data(),
            conv3_weights.data.data(), conv3_bias.data.data(),
            diagnostic_conv1.data(), diagnostic_conv2.data(),
            diagnostic_conv3.data(),
            test_case.input_height, test_case.input_width,
            test_case.same_padding, &observations)) {
        throw std::runtime_error(std::string(test_case.directory) +
                                 ": HLS float execution failed");
    }

    const long double conv1_declared_output =
        static_cast<long double>(
            srcnn_hls::numeric::Conv1Sizing::kOutputAbsMaxRaw) /
        srcnn_hls::numeric::kDataScale;
    const long double conv2_declared_output =
        static_cast<long double>(
            srcnn_hls::numeric::Conv2Sizing::kOutputAbsMaxRaw) /
        srcnn_hls::numeric::kDataScale;
    require_declared_range(test_case.directory, "conv1_output",
                           diagnostic_conv1, conv1_declared_output);
    require_declared_range(test_case.directory, "conv2_output",
                           diagnostic_conv2, conv2_declared_output);

    const float poison = std::numeric_limits<float>::quiet_NaN();
    std::vector<float> top_conv1(element_count(shape.conv1), poison);
    std::vector<float> top_conv2(element_count(shape.conv2), poison);
    std::vector<float> top_conv3(element_count(shape.conv3), poison);
    if (srcnn_hls::srcnn_hls_top(
            input.data.data(), conv1_weights.data.data(), conv1_bias.data.data(),
            conv2_weights.data.data(), conv2_bias.data.data(),
            conv3_weights.data.data(), conv3_bias.data.data(),
            top_conv1.data(), top_conv2.data(), top_conv3.data(),
            test_case.input_height, test_case.input_width,
            test_case.same_padding ? 1 : 0) != 0) {
        throw std::runtime_error(std::string(test_case.directory) +
                                 ": synthesizable top execution failed");
    }

    const auto expected_conv1 = srcnn::load_tensor_file(
        dump_directory / "conv1.tensor", "CHW", as_shape(shape.conv1));
    const auto expected_conv2 = srcnn::load_tensor_file(
        dump_directory / "conv2.tensor", "CHW", as_shape(shape.conv2));
    const auto expected_conv3 = srcnn::load_tensor_file(
        dump_directory / "conv3.tensor", "CHW", as_shape(shape.conv3));
    const auto expected_output = srcnn::load_tensor_file(
        dump_directory / "output.tensor", "CHW", as_shape(shape.conv3));

    require_bitwise_layer(test_case.directory, "diagnostic_conv1",
                          test_case.frozen_checksums[0], shape.conv1,
                          diagnostic_conv1, expected_conv1.data);
    require_bitwise_layer(test_case.directory, "diagnostic_conv2",
                          test_case.frozen_checksums[1], shape.conv2,
                          diagnostic_conv2, expected_conv2.data);
    require_bitwise_layer(test_case.directory, "diagnostic_conv3",
                          test_case.frozen_checksums[2], shape.conv3,
                          diagnostic_conv3, expected_conv3.data);

    require_bitwise_layer(test_case.directory, "conv1",
                          test_case.frozen_checksums[0], shape.conv1,
                          top_conv1, expected_conv1.data);
    require_bitwise_layer(test_case.directory, "conv2",
                          test_case.frozen_checksums[1], shape.conv2,
                          top_conv2, expected_conv2.data);
    require_bitwise_layer(test_case.directory, "conv3",
                          test_case.frozen_checksums[2], shape.conv3,
                          top_conv3, expected_conv3.data);
    require_bitwise_layer(test_case.directory, "output",
                          test_case.frozen_checksums[2], shape.conv3,
                          top_conv3, expected_output.data);

    for (std::size_t layer = 0; layer < aggregate_abs_max->size(); ++layer) {
        (*aggregate_abs_max)[layer] =
            std::max((*aggregate_abs_max)[layer],
                     observations.preactivation_abs_max[layer]);
    }

    std::cout << "PASS " << test_case.directory << " (conv1/conv2/conv3 bitwise)\n";
    print_gap(test_case.directory, "conv1",
              srcnn_hls::numeric::Conv1Sizing::mac_bound(),
              srcnn_hls::numeric::Conv1Sizing::preactivation_bound(),
              observations.preactivation_abs_max[0]);
    print_gap(test_case.directory, "conv2",
              srcnn_hls::numeric::Conv2Sizing::mac_bound(),
              srcnn_hls::numeric::Conv2Sizing::preactivation_bound(),
              observations.preactivation_abs_max[1]);
    print_gap(test_case.directory, "conv3",
              srcnn_hls::numeric::Conv3Sizing::mac_bound(),
              srcnn_hls::numeric::Conv3Sizing::preactivation_bound(),
              observations.preactivation_abs_max[2]);
}

}  // namespace

int main() {
    static_assert(SRCNN_HLS_FIXED_POINT == 0,
                  "this executable is the float compatibility gate");
    static_assert(std::is_same<srcnn_hls::numeric::data_t, float>::value,
                  "float gate requires data_t=float");
    static_assert(std::is_same<srcnn_hls::numeric::conv1_acc_t, float>::value &&
                      std::is_same<srcnn_hls::numeric::conv2_acc_t, float>::value &&
                      std::is_same<srcnn_hls::numeric::conv3_acc_t, float>::value,
                  "float gate requires every accumulator alias to be binary32");

    try {
        const fs::path vector_root = fs::path(SRCNN_PROJECT_ROOT) / "vectors";
        std::array<double, 3> aggregate_abs_max = {0.0, 0.0, 0.0};
        for (const auto& test_case : kCases) {
            run_case(vector_root, test_case, &aggregate_abs_max);
        }

        std::cout << "Aggregate worst-case / observed pre-activation gaps\n";
        print_gap("all-five-vectors", "conv1",
                  srcnn_hls::numeric::Conv1Sizing::mac_bound(),
                  srcnn_hls::numeric::Conv1Sizing::preactivation_bound(),
                  aggregate_abs_max[0]);
        print_gap("all-five-vectors", "conv2",
                  srcnn_hls::numeric::Conv2Sizing::mac_bound(),
                  srcnn_hls::numeric::Conv2Sizing::preactivation_bound(),
                  aggregate_abs_max[1]);
        print_gap("all-five-vectors", "conv3",
                  srcnn_hls::numeric::Conv3Sizing::mac_bound(),
                  srcnn_hls::numeric::Conv3Sizing::preactivation_bound(),
                  aggregate_abs_max[2]);
        std::cout << "PASS: all 5 frozen vector sets are bitwise identical\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
