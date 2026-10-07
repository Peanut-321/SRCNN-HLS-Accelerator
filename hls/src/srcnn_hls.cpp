#include "srcnn_hls/srcnn_hls.hpp"

#include "srcnn_hls/arithmetic.hpp"
#include "srcnn_hls/project_config.hpp"

#ifndef __SYNTHESIS__
#include <cmath>
#endif

namespace srcnn_hls {
namespace {

int output_extent(int input, int kernel, int padding, int stride) {
    const int padded_extent = input + 2 * padding;
    if (stride <= 0 || padded_extent < kernel) return 0;
    return (padded_extent - kernel) / stride + 1;
}

int chw_offset(int channel, int row, int column, int height, int width) {
    return (channel * height + row) * width + column;
}

int oihw_offset(int output_channel, int input_channel, int kernel_row,
                int kernel_column, int input_channels, int kernel_height,
                int kernel_width) {
    return (((output_channel * input_channels + input_channel) * kernel_height +
             kernel_row) *
                kernel_width +
            kernel_column);
}

struct NullObserver {
    template <typename Accumulator>
    void observe(int, const Accumulator&, bool) const {}
};

#ifndef __SYNTHESIS__
struct MaxAbsObserver {
    AccumulatorObservations* observations;

    template <typename Accumulator>
    void observe(int layer, const Accumulator& value, bool relu) const {
        if (observations == 0) return;
        const double converted = static_cast<double>(value);
        const double magnitude = std::fabs(converted);
        if (magnitude > observations->preactivation_abs_max[layer]) {
            observations->preactivation_abs_max[layer] = magnitude;
        }
        const double narrowed_input = relu && converted < 0.0 ? 0.0 : converted;
        const double data_scale = static_cast<double>(numeric::kDataScale);
        const double data_max =
            static_cast<double>(numeric::kDataPositiveMaxRaw) / data_scale;
        const double data_min =
            -static_cast<double>(numeric::pow2_u64(
                config::kDataTotalBits - 1)) /
            data_scale;
        if (narrowed_input < data_min || narrowed_input > data_max) {
            ++observations->narrowing_saturation_count[layer];
        }
    }
};
#endif

int clamp_index(int index, int extent) {
    if (index < 0) return 0;
    if (index >= extent) return extent - 1;
    return index;
}

template <typename Accumulator, typename Observer>
void conv2d_natural(const numeric::data_t* input,
                    const numeric::data_t* weights,
                    const numeric::data_t* bias,
                    numeric::data_t* output, int input_channels,
                    int input_height, int input_width, int output_channels,
                    int kernel_height, int kernel_width, int pad_height,
                    int pad_width, PaddingMode padding_mode, bool relu,
                    int layer_index,
                    const Observer& observer) {
    const int output_height = output_extent(input_height, kernel_height,
                                            pad_height, config::kStrideHeight);
    const int output_width = output_extent(input_width, kernel_width,
                                           pad_width, config::kStrideWidth);

    // Natural P1 loop order. P2.1 intentionally contains no optimization pragma.
    for (int output_channel = 0; output_channel < output_channels;
         ++output_channel) {
        for (int output_row = 0; output_row < output_height; ++output_row) {
            for (int output_column = 0; output_column < output_width;
                 ++output_column) {
                Accumulator sum =
                    arithmetic::begin_with_frozen_bias_order<Accumulator>(
                        bias[output_channel]);
                for (int input_channel = 0; input_channel < input_channels;
                     ++input_channel) {
                    for (int kernel_row = 0; kernel_row < kernel_height;
                         ++kernel_row) {
                        int input_row =
                            output_row * config::kStrideHeight + kernel_row -
                            pad_height;
                        if (input_row < 0 || input_row >= input_height) {
                            if (padding_mode == PaddingMode::kReplicateSame) {
                                input_row = clamp_index(input_row, input_height);
                            } else {
                                continue;
                            }
                        }
                        for (int kernel_column = 0; kernel_column < kernel_width;
                             ++kernel_column) {
                            int input_column =
                                output_column * config::kStrideWidth +
                                kernel_column - pad_width;
                            if (input_column < 0 || input_column >= input_width) {
                                if (padding_mode == PaddingMode::kReplicateSame) {
                                    input_column =
                                        clamp_index(input_column, input_width);
                                } else {
                                    continue;
                                }
                            }
                            const int weight_index = oihw_offset(
                                output_channel, input_channel, kernel_row,
                                kernel_column, input_channels, kernel_height,
                                kernel_width);
                            const int input_index = chw_offset(
                                input_channel, input_row, input_column,
                                input_height, input_width);
                            arithmetic::accumulate_product(
                                sum, weights[weight_index], input[input_index]);
                        }
                    }
                }
                observer.observe(layer_index, sum, relu);
                const int output_index = chw_offset(
                    output_channel, output_row, output_column, output_height,
                    output_width);
                output[output_index] =
                    arithmetic::activate_and_narrow<numeric::data_t>(sum, relu);
            }
        }
    }
}

template <typename Observer>
bool run_impl(const numeric::data_t* input,
              const numeric::data_t* conv1_weights,
              const numeric::data_t* conv1_bias,
              const numeric::data_t* conv2_weights,
              const numeric::data_t* conv2_bias,
              const numeric::data_t* conv3_weights,
              const numeric::data_t* conv3_bias,
              numeric::data_t* conv1_output,
              numeric::data_t* conv2_output,
              numeric::data_t* conv3_output, int input_height,
              int input_width, PaddingMode padding_mode,
              const Observer& observer) {
    NetworkShape shape;
    if (!make_network_shape(input_height, input_width, padding_mode, &shape)) {
        return false;
    }
    if (input == 0 || conv1_weights == 0 || conv1_bias == 0 ||
        conv2_weights == 0 || conv2_bias == 0 || conv3_weights == 0 ||
        conv3_bias == 0 || conv1_output == 0 || conv2_output == 0 ||
        conv3_output == 0) {
        return false;
    }

    const bool same_padding = padding_mode != PaddingMode::kValid;
    const int conv1_pad_h = same_padding ? config::kConv1SamePadHeight : 0;
    const int conv1_pad_w = same_padding ? config::kConv1SamePadWidth : 0;
    const int conv2_pad_h = same_padding ? config::kConv2SamePadHeight : 0;
    const int conv2_pad_w = same_padding ? config::kConv2SamePadWidth : 0;
    const int conv3_pad_h = same_padding ? config::kConv3SamePadHeight : 0;
    const int conv3_pad_w = same_padding ? config::kConv3SamePadWidth : 0;

    conv2d_natural<numeric::conv1_acc_t>(
        input, conv1_weights, conv1_bias, conv1_output,
        config::kConv1InChannels, shape.input.height, shape.input.width,
        config::kConv1OutChannels, config::kConv1KernelHeight,
        config::kConv1KernelWidth, conv1_pad_h, conv1_pad_w, padding_mode,
        true, 0,
        observer);
    conv2d_natural<numeric::conv2_acc_t>(
        conv1_output, conv2_weights, conv2_bias, conv2_output,
        config::kConv2InChannels, shape.conv1.height, shape.conv1.width,
        config::kConv2OutChannels, config::kConv2KernelHeight,
        config::kConv2KernelWidth, conv2_pad_h, conv2_pad_w, padding_mode,
        true, 1,
        observer);
    conv2d_natural<numeric::conv3_acc_t>(
        conv2_output, conv3_weights, conv3_bias, conv3_output,
        config::kConv3InChannels, shape.conv2.height, shape.conv2.width,
        config::kConv3OutChannels, config::kConv3KernelHeight,
        config::kConv3KernelWidth, conv3_pad_h, conv3_pad_w, padding_mode,
        false, 2,
        observer);
    return true;
}

}  // namespace

bool make_network_shape(int input_height, int input_width,
                        PaddingMode padding_mode,
                        NetworkShape* shape) {
    if (shape == 0 || input_height <= 0 || input_width <= 0 ||
        input_height > config::kMaxInputHeight ||
        input_width > config::kMaxInputWidth) {
        return false;
    }
    if (padding_mode != PaddingMode::kValid &&
        padding_mode != PaddingMode::kZeroSame &&
        padding_mode != PaddingMode::kReplicateSame) {
        return false;
    }
    const bool same_padding = padding_mode != PaddingMode::kValid;
    const int conv1_pad_h = same_padding ? config::kConv1SamePadHeight : 0;
    const int conv1_pad_w = same_padding ? config::kConv1SamePadWidth : 0;
    const int conv2_pad_h = same_padding ? config::kConv2SamePadHeight : 0;
    const int conv2_pad_w = same_padding ? config::kConv2SamePadWidth : 0;
    const int conv3_pad_h = same_padding ? config::kConv3SamePadHeight : 0;
    const int conv3_pad_w = same_padding ? config::kConv3SamePadWidth : 0;

    const int conv1_height =
        output_extent(input_height, config::kConv1KernelHeight, conv1_pad_h,
                      config::kStrideHeight);
    const int conv1_width =
        output_extent(input_width, config::kConv1KernelWidth, conv1_pad_w,
                      config::kStrideWidth);
    const int conv2_height =
        output_extent(conv1_height, config::kConv2KernelHeight, conv2_pad_h,
                      config::kStrideHeight);
    const int conv2_width =
        output_extent(conv1_width, config::kConv2KernelWidth, conv2_pad_w,
                      config::kStrideWidth);
    const int conv3_height =
        output_extent(conv2_height, config::kConv3KernelHeight, conv3_pad_h,
                      config::kStrideHeight);
    const int conv3_width =
        output_extent(conv2_width, config::kConv3KernelWidth, conv3_pad_w,
                      config::kStrideWidth);
    if (conv1_height <= 0 || conv1_width <= 0 || conv2_height <= 0 ||
        conv2_width <= 0 || conv3_height <= 0 || conv3_width <= 0) {
        return false;
    }

    shape->input = {config::kConv1InChannels, input_height, input_width};
    shape->conv1 = {config::kConv1OutChannels, conv1_height, conv1_width};
    shape->conv2 = {config::kConv2OutChannels, conv2_height, conv2_width};
    shape->conv3 = {config::kConv3OutChannels, conv3_height, conv3_width};
    return true;
}

bool make_network_shape(int input_height, int input_width, bool same_padding,
                        NetworkShape* shape) {
    return make_network_shape(
        input_height, input_width,
        same_padding ? PaddingMode::kZeroSame : PaddingMode::kValid, shape);
}

#ifndef __SYNTHESIS__
bool run_srcnn_natural(
    const numeric::data_t* input, const numeric::data_t* conv1_weights,
    const numeric::data_t* conv1_bias,
    const numeric::data_t* conv2_weights,
    const numeric::data_t* conv2_bias,
    const numeric::data_t* conv3_weights,
    const numeric::data_t* conv3_bias, numeric::data_t* conv1_output,
    numeric::data_t* conv2_output, numeric::data_t* conv3_output,
    int input_height, int input_width, PaddingMode padding_mode,
    AccumulatorObservations* observations) {
    if (observations != 0) {
        observations->preactivation_abs_max[0] = 0.0;
        observations->preactivation_abs_max[1] = 0.0;
        observations->preactivation_abs_max[2] = 0.0;
        observations->narrowing_saturation_count[0] = 0;
        observations->narrowing_saturation_count[1] = 0;
        observations->narrowing_saturation_count[2] = 0;
    }
    return run_impl(input, conv1_weights, conv1_bias, conv2_weights,
                    conv2_bias, conv3_weights, conv3_bias, conv1_output,
                    conv2_output, conv3_output, input_height, input_width,
                    padding_mode, MaxAbsObserver{observations});
}

bool run_srcnn_natural(
    const numeric::data_t* input, const numeric::data_t* conv1_weights,
    const numeric::data_t* conv1_bias,
    const numeric::data_t* conv2_weights,
    const numeric::data_t* conv2_bias,
    const numeric::data_t* conv3_weights,
    const numeric::data_t* conv3_bias, numeric::data_t* conv1_output,
    numeric::data_t* conv2_output, numeric::data_t* conv3_output,
    int input_height, int input_width, bool same_padding,
    AccumulatorObservations* observations) {
    return run_srcnn_natural(
        input, conv1_weights, conv1_bias, conv2_weights, conv2_bias,
        conv3_weights, conv3_bias, conv1_output, conv2_output, conv3_output,
        input_height, input_width,
        same_padding ? PaddingMode::kZeroSame : PaddingMode::kValid,
        observations);
}
#endif

extern "C" int srcnn_hls_top(
    const numeric::data_t* input, const numeric::data_t* conv1_weights,
    const numeric::data_t* conv1_bias,
    const numeric::data_t* conv2_weights,
    const numeric::data_t* conv2_bias,
    const numeric::data_t* conv3_weights,
    const numeric::data_t* conv3_bias, numeric::data_t* conv1_output,
    numeric::data_t* conv2_output, numeric::data_t* conv3_output,
    int input_height, int input_width, int padding_mode) {
    if (padding_mode < static_cast<int>(PaddingMode::kValid) ||
        padding_mode > static_cast<int>(PaddingMode::kReplicateSame)) {
        return -1;
    }
    return run_impl(input, conv1_weights, conv1_bias, conv2_weights,
                    conv2_bias, conv3_weights, conv3_bias, conv1_output,
                    conv2_output, conv3_output, input_height, input_width,
                    static_cast<PaddingMode>(padding_mode), NullObserver{})
               ? 0
               : -1;
}

}  // namespace srcnn_hls
