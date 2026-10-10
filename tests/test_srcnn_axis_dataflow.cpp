#include "srcnn_hls/axis_dataflow.hpp"
#include "srcnn_hls/project_config.hpp"
#include "srcnn_hls/srcnn_hls.hpp"

#include <cstddef>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

// Keep the normal host regression as the default, while allowing Vitis RTL
// co-simulation to isolate one call (or one restart pattern) per component.
// This macro changes only the testbench; it is not referenced by the HLS DUT.
#ifndef SRCNN_AXIS_DATAFLOW_TEST_CASE
#define SRCNN_AXIS_DATAFLOW_TEST_CASE 0
#endif

#ifndef SRCNN_AXIS_DATAFLOW_USE_FIXED_13X17_TOP
#define SRCNN_AXIS_DATAFLOW_USE_FIXED_13X17_TOP 0
#endif

static_assert(SRCNN_AXIS_DATAFLOW_TEST_CASE >= 0 &&
                  SRCNN_AXIS_DATAFLOW_TEST_CASE <= 5,
              "SRCNN_AXIS_DATAFLOW_TEST_CASE must be in [0, 5]");
static_assert(!SRCNN_AXIS_DATAFLOW_USE_FIXED_13X17_TOP ||
                  SRCNN_AXIS_DATAFLOW_TEST_CASE == 3,
              "fixed 13x17 top requires test case 3");

namespace {

using srcnn_hls::axis_dataflow::axis_stream_t;
using srcnn_hls::axis_dataflow::axis_word_t;
using srcnn_hls::numeric::data_t;

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

template <typename T>
bool exact_equal(const T& lhs, const T& rhs) {
    return lhs == rhs;
}

bool exact_equal(const float& lhs, const float& rhs) {
    return std::memcmp(&lhs, &rhs, sizeof(float)) == 0;
}

void append(std::vector<data_t>* destination,
            const std::vector<data_t>& source) {
    destination->insert(destination->end(), source.begin(), source.end());
}

void run_case(const char* name, int height, int width) {
    const std::size_t pixel_count =
        static_cast<std::size_t>(height) * static_cast<std::size_t>(width);

    const auto input =
#if SRCNN_HLS_OFFICIAL_Q20_12
        deterministic_values<data_t>(pixel_count, 9, 0, 16);
#else
        deterministic_values<data_t>(pixel_count, 9, -4, 16);
#endif
    const auto conv1_weights = deterministic_values<data_t>(
        srcnn_hls::axis_dataflow::kConv1WeightsCount, 7, -3, 32);
    const auto conv1_bias = deterministic_values<data_t>(
        srcnn_hls::axis_dataflow::kConv1BiasCount, 5, -2, 16);
    const auto conv2_weights = deterministic_values<data_t>(
        srcnn_hls::axis_dataflow::kConv2WeightsCount, 7, -3, 64);
    const auto conv2_bias = deterministic_values<data_t>(
        srcnn_hls::axis_dataflow::kConv2BiasCount, 5, -2, 32);
    const auto conv3_weights = deterministic_values<data_t>(
        srcnn_hls::axis_dataflow::kConv3WeightsCount, 7, -3, 64);
    const auto conv3_bias = deterministic_values<data_t>(
#if SRCNN_HLS_OFFICIAL_Q20_12
        srcnn_hls::axis_dataflow::kConv3BiasCount, 3, -1, 64);
#else
        srcnn_hls::axis_dataflow::kConv3BiasCount, 3, -1, 32);
#endif

    std::vector<data_t> model;
    model.reserve(srcnn_hls::axis_dataflow::kModelElementCount);
    append(&model, conv1_weights);
    append(&model, conv1_bias);
    append(&model, conv2_weights);
    append(&model, conv2_bias);
    append(&model, conv3_weights);
    append(&model, conv3_bias);
    if (model.size() !=
        static_cast<std::size_t>(
            srcnn_hls::axis_dataflow::kModelElementCount)) {
        throw std::runtime_error(std::string(name) + ": model layout error");
    }

    std::vector<data_t> expected_conv1(
        pixel_count * srcnn_hls::config::kConv1OutChannels);
    std::vector<data_t> expected_conv2(
        pixel_count * srcnn_hls::config::kConv2OutChannels);
    std::vector<data_t> expected_output(pixel_count);
    if (srcnn_hls::srcnn_hls_line_buffer_replicate_oc4_top(
            input.data(), conv1_weights.data(), conv1_bias.data(),
            conv2_weights.data(), conv2_bias.data(), conv3_weights.data(),
            conv3_bias.data(), expected_conv1.data(), expected_conv2.data(),
            expected_output.data(), height, width) != 0) {
        throw std::runtime_error(std::string(name) +
                                 ": OC4 reference execution failed");
    }

    axis_stream_t input_stream;
    axis_stream_t output_stream;
    for (std::size_t index = 0; index < pixel_count; ++index) {
        axis_word_t word;
        word.data = srcnn_hls::axis_dataflow::encode_data_bits(input[index]);
        word.keep = 0xF;
        word.strb = 0xF;
        word.last = index + 1 == pixel_count;
        input_stream.write(word);
    }

#if SRCNN_AXIS_DATAFLOW_USE_FIXED_13X17_TOP
    if (height != 13 || width != 17) {
        throw std::runtime_error(std::string(name) +
                                 ": fixed top requires 13x17");
    }
    srcnn_axis_dataflow_cosim_13x17_top(input_stream, output_stream,
                                        model.data());
#else
    srcnn_axis_dataflow_cosim_top(input_stream, output_stream, model.data(),
                                  height, width);
#endif
    if (!input_stream.empty()) {
        throw std::runtime_error(std::string(name) +
                                 ": input stream was not fully consumed");
    }
    if (output_stream.size() != pixel_count) {
        throw std::runtime_error(std::string(name) +
                                 ": unexpected output word count");
    }

    for (std::size_t index = 0; index < pixel_count; ++index) {
        const axis_word_t word = output_stream.read();
        if (word.keep != 0xF || word.strb != 0xF ||
            word.last != (index + 1 == pixel_count)) {
            throw std::runtime_error(std::string(name) +
                                     ": invalid AXIS sideband at index " +
                                     std::to_string(index));
        }
#ifdef SRCNN_AXIS_DATAFLOW_HOST_SIM
        const std::uint32_t output_bits = word.data;
#else
        const std::uint32_t output_bits = word.data.to_uint();
#endif
        const data_t actual =
            srcnn_hls::axis_dataflow::decode_data_bits(output_bits);
        if (!exact_equal(actual, expected_output[index])) {
            throw std::runtime_error(
                std::string(name) + ": first output mismatch at index " +
                std::to_string(index) + ", expected=" +
                std::to_string(static_cast<double>(expected_output[index])) +
                ", actual=" +
                std::to_string(static_cast<double>(actual)));
        }
    }

    std::cout << "PASS: " << name << " (" << pixel_count
              << " AXIS words)\n";
}

}  // namespace

int main() {
    try {
#if SRCNN_AXIS_DATAFLOW_TEST_CASE == 1
        run_case("axis_dataflow_1x1", 1, 1);
#elif SRCNN_AXIS_DATAFLOW_TEST_CASE == 2
        run_case("axis_dataflow_5x7", 5, 7);
#elif SRCNN_AXIS_DATAFLOW_TEST_CASE == 3
        run_case("axis_dataflow_13x17", 13, 17);
#elif SRCNN_AXIS_DATAFLOW_TEST_CASE == 4
        run_case("axis_dataflow_1x1_restart_1", 1, 1);
        run_case("axis_dataflow_1x1_restart_2", 1, 1);
#elif SRCNN_AXIS_DATAFLOW_TEST_CASE == 5
        run_case("axis_dataflow_1x1_transition", 1, 1);
        run_case("axis_dataflow_5x7_transition", 5, 7);
#else
        run_case("axis_dataflow_1x1", 1, 1);
        run_case("axis_dataflow_5x7", 5, 7);
        run_case("axis_dataflow_13x17", 13, 17);
#endif
        std::cout << "PASS: AXIS/DATAFLOW final output exactly matches OC4\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
