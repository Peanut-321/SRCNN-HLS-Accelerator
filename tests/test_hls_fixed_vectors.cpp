#include "srcnn_hls/numeric_config.hpp"
#include "srcnn_hls/project_config.hpp"
#include "srcnn_hls/srcnn_hls.hpp"

#include "srcnn/tensor_io.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

#ifndef SRCNN_PROJECT_ROOT
#error "SRCNN_PROJECT_ROOT must name the repository root"
#endif

namespace {

namespace fs = std::filesystem;
using data_t = srcnn_hls::numeric::data_t;

struct VectorCase {
    const char* directory;
    int height;
    int width;
    srcnn_hls::PaddingMode padding_mode;
};

constexpr std::array<VectorCase, 5> kCases = {{
    {"fixed_seed", 13, 17, srcnn_hls::PaddingMode::kZeroSame},
    {"fixed_seed_valid", 13, 17, srcnn_hls::PaddingMode::kValid},
    {"cosim_33x29", 33, 29, srcnn_hls::PaddingMode::kZeroSame},
    {"cosim_33x29_valid", 33, 29, srcnn_hls::PaddingMode::kValid},
    {"naive_15x13", 15, 13, srcnn_hls::PaddingMode::kZeroSame},
}};

struct Metrics {
    std::size_t count = 0;
    std::size_t zero_flip_count = 0;
    std::size_t worst_index = 0;
    double max_abs = 0.0;
    double max_relative = 0.0;
    double mae = 0.0;
    double rmse = 0.0;
    double relative_l2 = 0.0;
    double psnr_r1 = std::numeric_limits<double>::infinity();
    double abs_error_p50 = 0.0;
    double abs_error_p95 = 0.0;
    double abs_error_p99 = 0.0;
};

double nearest_rank(std::vector<double>* sorted_values, double quantile) {
    std::sort(sorted_values->begin(), sorted_values->end());
    const std::size_t rank = static_cast<std::size_t>(
        std::ceil(quantile * static_cast<double>(sorted_values->size())));
    return (*sorted_values)[std::max<std::size_t>(1, rank) - 1];
}

std::size_t element_count(const srcnn_hls::LayerShape& shape) {
    return static_cast<std::size_t>(shape.channels) * shape.height * shape.width;
}

std::vector<std::size_t> tensor_shape(const srcnn_hls::LayerShape& shape) {
    return {static_cast<std::size_t>(shape.channels),
            static_cast<std::size_t>(shape.height),
            static_cast<std::size_t>(shape.width)};
}

srcnn::TensorFile load_parameter(const fs::path& model_directory,
                                 const char* filename, const char* layout,
                                 std::vector<std::size_t> shape) {
    return srcnn::load_tensor_file(model_directory / filename, layout, shape);
}

std::vector<data_t> quantize(const std::vector<float>& source,
                             std::size_t* input_saturation_count) {
    const double scale = static_cast<double>(srcnn_hls::numeric::kDataScale);
    const double maximum =
        static_cast<double>(srcnn_hls::numeric::kDataPositiveMaxRaw) / scale;
    const double minimum =
        -static_cast<double>(srcnn_hls::numeric::pow2_u64(
            srcnn_hls::config::kDataTotalBits - 1)) /
        scale;
    std::vector<data_t> result;
    result.reserve(source.size());
    for (float value : source) {
        if (!std::isfinite(value)) {
            throw std::runtime_error("non-finite source value before quantization");
        }
        if (value < minimum || value > maximum) ++*input_saturation_count;
        result.push_back(data_t(value));
    }
    return result;
}

Metrics compare(const std::vector<data_t>& actual,
                const std::vector<float>& reference) {
    if (actual.size() != reference.size() || actual.empty()) {
        throw std::runtime_error("fixed/reference element-count mismatch");
    }
    Metrics result;
    result.count = actual.size();
    long double sum_abs = 0.0L;
    long double sum_square = 0.0L;
    long double reference_square = 0.0L;
    std::vector<double> absolute_errors;
    absolute_errors.reserve(actual.size());
    for (std::size_t index = 0; index < actual.size(); ++index) {
        const double got = static_cast<double>(actual[index]);
        const double expected = static_cast<double>(reference[index]);
        if (!std::isfinite(got) || !std::isfinite(expected)) {
            throw std::runtime_error("non-finite value during metric calculation");
        }
        const double difference = got - expected;
        const double absolute = std::fabs(difference);
        absolute_errors.push_back(absolute);
        if (absolute > result.max_abs) {
            result.max_abs = absolute;
            result.worst_index = index;
        }
        if (expected != 0.0) {
            result.max_relative =
                std::max(result.max_relative, absolute / std::fabs(expected));
        } else if (got != 0.0) {
            ++result.zero_flip_count;
        }
        sum_abs += absolute;
        sum_square += static_cast<long double>(difference) * difference;
        reference_square += static_cast<long double>(expected) * expected;
    }
    result.mae = static_cast<double>(sum_abs / result.count);
    const long double mse = sum_square / result.count;
    result.rmse = std::sqrt(static_cast<double>(mse));
    result.relative_l2 =
        reference_square == 0.0L
            ? (sum_square == 0.0L ? 0.0
                                  : std::numeric_limits<double>::infinity())
            : std::sqrt(static_cast<double>(sum_square / reference_square));
    if (mse > 0.0L) {
        result.psnr_r1 = 10.0 * std::log10(1.0 / static_cast<double>(mse));
    }
    result.abs_error_p50 = nearest_rank(&absolute_errors, 0.50);
    result.abs_error_p95 = nearest_rank(&absolute_errors, 0.95);
    result.abs_error_p99 = nearest_rank(&absolute_errors, 0.99);
    return result;
}

void print_metrics(const char* vector_name, const char* layer_name,
                   const srcnn_hls::LayerShape& shape, const Metrics& metrics) {
    const std::size_t plane = static_cast<std::size_t>(shape.height) * shape.width;
    const std::size_t channel = metrics.worst_index / plane;
    const std::size_t within_plane = metrics.worst_index % plane;
    const std::size_t row = within_plane / shape.width;
    const std::size_t column = within_plane % shape.width;
    std::cout << std::setprecision(10) << "METRIC," << vector_name << ','
              << layer_name << ",count=" << metrics.count
              << ",max_abs=" << metrics.max_abs
              << ",max_relative=" << metrics.max_relative
              << ",mae=" << metrics.mae << ",rmse=" << metrics.rmse
              << ",relative_l2=" << metrics.relative_l2
              << ",psnr_r1_db=" << metrics.psnr_r1
              << ",abs_error_p50=" << metrics.abs_error_p50
              << ",abs_error_p95=" << metrics.abs_error_p95
              << ",abs_error_p99=" << metrics.abs_error_p99
              << ",zero_flips=" << metrics.zero_flip_count
              << ",worst_chw=" << channel << ':' << row << ':' << column
              << '\n';
}

void run_case(const fs::path& vector_root, const VectorCase& test_case) {
    const fs::path root = vector_root / test_case.directory;
    const fs::path model = root / "model";
    const fs::path dumps = root / "dumps";
    srcnn_hls::NetworkShape shape{};
    if (!srcnn_hls::make_network_shape(test_case.height, test_case.width,
                                       test_case.padding_mode, &shape)) {
        throw std::runtime_error(std::string(test_case.directory) +
                                 ": shape construction failed");
    }

    const auto input_file = srcnn::load_tensor_file(
        dumps / "input.tensor", "CHW", tensor_shape(shape.input));
    const auto conv1_weights_file = load_parameter(
        model, "conv1_weights.tensor", "OIHW",
        {srcnn_hls::config::kConv1OutChannels,
         srcnn_hls::config::kConv1InChannels,
         srcnn_hls::config::kConv1KernelHeight,
         srcnn_hls::config::kConv1KernelWidth});
    const auto conv1_bias_file = load_parameter(
        model, "conv1_bias.tensor", "O",
        {srcnn_hls::config::kConv1OutChannels});
    const auto conv2_weights_file = load_parameter(
        model, "conv2_weights.tensor", "OIHW",
        {srcnn_hls::config::kConv2OutChannels,
         srcnn_hls::config::kConv2InChannels,
         srcnn_hls::config::kConv2KernelHeight,
         srcnn_hls::config::kConv2KernelWidth});
    const auto conv2_bias_file = load_parameter(
        model, "conv2_bias.tensor", "O",
        {srcnn_hls::config::kConv2OutChannels});
    const auto conv3_weights_file = load_parameter(
        model, "conv3_weights.tensor", "OIHW",
        {srcnn_hls::config::kConv3OutChannels,
         srcnn_hls::config::kConv3InChannels,
         srcnn_hls::config::kConv3KernelHeight,
         srcnn_hls::config::kConv3KernelWidth});
    const auto conv3_bias_file = load_parameter(
        model, "conv3_bias.tensor", "O",
        {srcnn_hls::config::kConv3OutChannels});

    std::size_t source_saturations = 0;
    const auto input = quantize(input_file.data, &source_saturations);
    const auto conv1_weights =
        quantize(conv1_weights_file.data, &source_saturations);
    const auto conv1_bias = quantize(conv1_bias_file.data, &source_saturations);
    const auto conv2_weights =
        quantize(conv2_weights_file.data, &source_saturations);
    const auto conv2_bias = quantize(conv2_bias_file.data, &source_saturations);
    const auto conv3_weights =
        quantize(conv3_weights_file.data, &source_saturations);
    const auto conv3_bias = quantize(conv3_bias_file.data, &source_saturations);
    std::vector<data_t> conv1_output(element_count(shape.conv1));
    std::vector<data_t> conv2_output(element_count(shape.conv2));
    std::vector<data_t> conv3_output(element_count(shape.conv3));
    srcnn_hls::AccumulatorObservations observations{};
    if (!srcnn_hls::run_srcnn_natural(
            input.data(), conv1_weights.data(), conv1_bias.data(),
            conv2_weights.data(), conv2_bias.data(), conv3_weights.data(),
            conv3_bias.data(), conv1_output.data(), conv2_output.data(),
            conv3_output.data(), test_case.height, test_case.width,
            test_case.padding_mode, &observations)) {
        throw std::runtime_error(std::string(test_case.directory) +
                                 ": fixed execution failed");
    }

    const auto ref1 = srcnn::load_tensor_file(
        dumps / "conv1.tensor", "CHW", tensor_shape(shape.conv1));
    const auto ref2 = srcnn::load_tensor_file(
        dumps / "conv2.tensor", "CHW", tensor_shape(shape.conv2));
    const auto ref3 = srcnn::load_tensor_file(
        dumps / "conv3.tensor", "CHW", tensor_shape(shape.conv3));
    print_metrics(test_case.directory, "conv1", shape.conv1,
                  compare(conv1_output, ref1.data));
    print_metrics(test_case.directory, "conv2", shape.conv2,
                  compare(conv2_output, ref2.data));
    print_metrics(test_case.directory, "conv3", shape.conv3,
                  compare(conv3_output, ref3.data));
    std::cout << "SATURATION," << test_case.directory
              << ",source=" << source_saturations
              << ",conv1_narrow="
              << observations.narrowing_saturation_count[0]
              << ",conv2_narrow="
              << observations.narrowing_saturation_count[1]
              << ",conv3_narrow="
              << observations.narrowing_saturation_count[2]
              << ",preactivation_abs_max="
              << observations.preactivation_abs_max[0] << ':'
              << observations.preactivation_abs_max[1] << ':'
              << observations.preactivation_abs_max[2] << '\n';
    if (source_saturations != 0 ||
        observations.narrowing_saturation_count[0] != 0 ||
        observations.narrowing_saturation_count[1] != 0 ||
        observations.narrowing_saturation_count[2] != 0) {
        throw std::runtime_error(std::string(test_case.directory) +
                                 ": saturation detected");
    }
}

}  // namespace

int main() {
    static_assert(SRCNN_HLS_FIXED_POINT == 1,
                  "fixed vector harness requires ap_fixed types");
    try {
        const fs::path vector_root = fs::path(SRCNN_PROJECT_ROOT) / "vectors";
        for (const auto& test_case : kCases) run_case(vector_root, test_case);
        std::cout << "PASS: P2.2a fixed-vs-float metrics for all five random vector sets\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
