#include "srcnn_hls/axis_dataflow.hpp"

#include "srcnn_hls/arithmetic.hpp"
#include "srcnn_hls/project_config.hpp"

namespace srcnn_hls {
namespace axis_dataflow {
namespace {

constexpr int kConv1Lanes = 4;
constexpr int kConv1Groups = config::kConv1OutChannels / kConv1Lanes;
constexpr int kConv1HistoryRows = config::kConv1KernelHeight - 1;
constexpr int kConv1PaddedWidth =
    config::kMaxInputWidth + 2 * config::kConv1SamePadWidth;
constexpr int kConv3HistoryRows = config::kConv3KernelHeight - 1;
constexpr int kConv3PaddedWidth =
    config::kMaxInputWidth + 2 * config::kConv3SamePadWidth;

static_assert(config::kConv1OutChannels % kConv1Lanes == 0,
              "Conv1 OC4 requires 64 output channels");
static_assert(config::kStrideHeight == 1 && config::kStrideWidth == 1,
              "streaming dataflow path requires unit stride");

int clamp_index(int index, int extent) {
    if (index < 0) return 0;
    if (index >= extent) return extent - 1;
    return index;
}

std::uint32_t axis_word_bits(const axis_word_t& word) {
#ifdef SRCNN_AXIS_DATAFLOW_HOST_SIM
    return word.data;
#else
    return word.data.to_uint();
#endif
}

void axis_to_scalar(axis_stream_t& input, data_stream_t& pixels, int height,
                    int width) {
#pragma HLS INLINE off
    const int count = height * width;
    for (int index = 0; index < count; ++index) {
#pragma HLS PIPELINE II=1
        const axis_word_t word = input.read();
        pixels.write(decode_data_bits(axis_word_bits(word)));
    }
}

void scalar_to_axis(data_stream_t& pixels, axis_stream_t& output, int height,
                    int width) {
#pragma HLS INLINE off
    const int count = height * width;
    for (int index = 0; index < count; ++index) {
#pragma HLS PIPELINE II=1
        axis_word_t word;
        word.data = encode_data_bits(pixels.read());
        word.keep = 0xF;
        word.strb = 0xF;
        word.last = index + 1 == count;
        output.write(word);
    }
}

void conv1_process_padded_row(
    const numeric::data_t row[config::kMaxInputWidth], int width,
    int padded_row,
    numeric::data_t line_buffer[kConv1HistoryRows][kConv1PaddedWidth],
    numeric::data_t
        window[config::kConv1KernelHeight][config::kConv1KernelWidth],
    const numeric::data_t
        weights[kConv1Lanes][kConv1Groups][config::kConv1KernelHeight]
               [config::kConv1KernelWidth],
    const numeric::data_t bias[kConv1Lanes][kConv1Groups],
    data_stream_t& output) {
#pragma HLS INLINE off
    const int padded_width = width + 2 * config::kConv1SamePadWidth;

    for (int padded_column = 0; padded_column < padded_width;
         ++padded_column) {
        const int source_column = clamp_index(
            padded_column - config::kConv1SamePadWidth, width);
        const numeric::data_t sample = row[source_column];

        const numeric::data_t delayed_1 =
            line_buffer[0][padded_column];
        const numeric::data_t delayed_2 =
            line_buffer[1][padded_column];
        const numeric::data_t delayed_3 =
            line_buffer[2][padded_column];
        const numeric::data_t delayed_4 =
            line_buffer[3][padded_column];
        const numeric::data_t delayed_5 =
            line_buffer[4][padded_column];
        const numeric::data_t delayed_6 =
            line_buffer[5][padded_column];
        const numeric::data_t delayed_7 =
            line_buffer[6][padded_column];
        const numeric::data_t delayed_8 =
            line_buffer[7][padded_column];

        line_buffer[0][padded_column] = sample;
        line_buffer[1][padded_column] = delayed_1;
        line_buffer[2][padded_column] = delayed_2;
        line_buffer[3][padded_column] = delayed_3;
        line_buffer[4][padded_column] = delayed_4;
        line_buffer[5][padded_column] = delayed_5;
        line_buffer[6][padded_column] = delayed_6;
        line_buffer[7][padded_column] = delayed_7;

        const numeric::data_t vertical_taps[config::kConv1KernelHeight] = {
            delayed_8, delayed_7, delayed_6, delayed_5, delayed_4,
            delayed_3, delayed_2, delayed_1, sample};

        for (int kernel_row = 0;
             kernel_row < config::kConv1KernelHeight; ++kernel_row) {
            for (int kernel_column = 0;
                 kernel_column + 1 < config::kConv1KernelWidth;
                 ++kernel_column) {
                window[kernel_row][kernel_column] =
                    window[kernel_row][kernel_column + 1];
            }
            window[kernel_row][config::kConv1KernelWidth - 1] =
                vertical_taps[kernel_row];
        }

        if (padded_row + 1 < config::kConv1KernelHeight ||
            padded_column + 1 < config::kConv1KernelWidth) {
            continue;
        }

        for (int group = 0; group < kConv1Groups; ++group) {
            numeric::conv1_acc_t sums[kConv1Lanes];
#pragma HLS ARRAY_PARTITION variable=sums complete dim=1
            for (int lane = 0; lane < kConv1Lanes; ++lane) {
#pragma HLS UNROLL
                sums[lane] =
                    arithmetic::begin_with_frozen_bias_order<
                        numeric::conv1_acc_t>(bias[lane][group]);
            }

            for (int kernel_row = 0;
                 kernel_row < config::kConv1KernelHeight; ++kernel_row) {
                for (int kernel_column = 0;
                     kernel_column < config::kConv1KernelWidth;
                     ++kernel_column) {
                    const numeric::data_t window_value =
                        window[kernel_row][kernel_column];
                    for (int lane = 0; lane < kConv1Lanes; ++lane) {
#pragma HLS UNROLL
                        arithmetic::accumulate_product(
                            sums[lane],
                            weights[lane][group][kernel_row][kernel_column],
                            window_value);
                    }
                }
            }

            for (int lane = 0; lane < kConv1Lanes; ++lane) {
#pragma HLS UNROLL
                output.write(
                    arithmetic::activate_and_narrow<numeric::data_t>(
                        sums[lane], true));
            }
        }
    }
}

void conv1_stream(
    data_stream_t& input, data_stream_t& output,
    const numeric::data_t
        weights[kConv1Lanes][kConv1Groups][config::kConv1KernelHeight]
               [config::kConv1KernelWidth],
    const numeric::data_t bias[kConv1Lanes][kConv1Groups], int height,
    int width) {
#pragma HLS INLINE off
    numeric::data_t row[config::kMaxInputWidth];
    numeric::data_t line_buffer[kConv1HistoryRows][kConv1PaddedWidth];
    numeric::data_t
        window[config::kConv1KernelHeight][config::kConv1KernelWidth];
#pragma HLS ARRAY_PARTITION variable=weights complete dim=1
#pragma HLS ARRAY_PARTITION variable=bias complete dim=1

    for (int bank = 0; bank < kConv1HistoryRows; ++bank) {
        for (int column = 0; column < kConv1PaddedWidth; ++column) {
            line_buffer[bank][column] = static_cast<numeric::data_t>(0);
        }
    }
    for (int kernel_row = 0; kernel_row < config::kConv1KernelHeight;
         ++kernel_row) {
        for (int kernel_column = 0;
             kernel_column < config::kConv1KernelWidth; ++kernel_column) {
            window[kernel_row][kernel_column] =
                static_cast<numeric::data_t>(0);
        }
    }

    int padded_row = 0;
    for (int source_row = 0; source_row < height; ++source_row) {
        for (int column = 0; column < width; ++column) {
            row[column] = input.read();
        }

        const int repetitions =
            source_row == 0 ? config::kConv1SamePadHeight + 1 : 1;
        for (int repeat = 0; repeat < repetitions; ++repeat) {
            conv1_process_padded_row(row, width, padded_row, line_buffer,
                                     window, weights, bias, output);
            ++padded_row;
        }
    }

    for (int repeat = 0; repeat < config::kConv1SamePadHeight; ++repeat) {
        conv1_process_padded_row(row, width, padded_row, line_buffer, window,
                                 weights, bias, output);
        ++padded_row;
    }
}

void conv2_stream(
    data_stream_t& input, data_stream_t& output,
    const numeric::data_t
        weights[config::kConv2OutChannels][config::kConv2InChannels],
    const numeric::data_t bias[config::kConv2OutChannels], int height,
    int width) {
#pragma HLS INLINE off
    const int pixel_count = height * width;
    for (int pixel = 0; pixel < pixel_count; ++pixel) {
        numeric::conv2_acc_t sums[config::kConv2OutChannels];
        for (int output_channel = 0;
             output_channel < config::kConv2OutChannels; ++output_channel) {
            sums[output_channel] =
                arithmetic::begin_with_frozen_bias_order<
                    numeric::conv2_acc_t>(bias[output_channel]);
        }

        for (int input_channel = 0;
             input_channel < config::kConv2InChannels; ++input_channel) {
            const numeric::data_t input_value = input.read();
            for (int output_channel = 0;
                 output_channel < config::kConv2OutChannels;
                 ++output_channel) {
                arithmetic::accumulate_product(
                    sums[output_channel],
                    weights[output_channel][input_channel], input_value);
            }
        }

        for (int output_channel = 0;
             output_channel < config::kConv2OutChannels; ++output_channel) {
            output.write(arithmetic::activate_and_narrow<numeric::data_t>(
                sums[output_channel], true));
        }
    }
}

void conv3_process_padded_row(
    const numeric::data_t
        row[config::kConv3InChannels][config::kMaxInputWidth],
    int width, int padded_row,
    numeric::data_t
        line_buffer[kConv3HistoryRows][config::kConv3InChannels]
                   [kConv3PaddedWidth],
    numeric::data_t
        window[config::kConv3InChannels][config::kConv3KernelHeight]
              [config::kConv3KernelWidth],
    const numeric::data_t
        weights[config::kConv3InChannels][config::kConv3KernelHeight]
               [config::kConv3KernelWidth],
    numeric::data_t bias, data_stream_t& output) {
#pragma HLS INLINE off
    const int padded_width = width + 2 * config::kConv3SamePadWidth;

    for (int padded_column = 0; padded_column < padded_width;
         ++padded_column) {
        const int source_column = clamp_index(
            padded_column - config::kConv3SamePadWidth, width);

        for (int input_channel = 0;
             input_channel < config::kConv3InChannels; ++input_channel) {
            const numeric::data_t sample =
                row[input_channel][source_column];
            const numeric::data_t delayed_1 =
                line_buffer[0][input_channel][padded_column];
            const numeric::data_t delayed_2 =
                line_buffer[1][input_channel][padded_column];
            const numeric::data_t delayed_3 =
                line_buffer[2][input_channel][padded_column];
            const numeric::data_t delayed_4 =
                line_buffer[3][input_channel][padded_column];

            line_buffer[0][input_channel][padded_column] = sample;
            line_buffer[1][input_channel][padded_column] = delayed_1;
            line_buffer[2][input_channel][padded_column] = delayed_2;
            line_buffer[3][input_channel][padded_column] = delayed_3;

            const numeric::data_t
                vertical_taps[config::kConv3KernelHeight] = {
                    delayed_4, delayed_3, delayed_2, delayed_1, sample};
            for (int kernel_row = 0;
                 kernel_row < config::kConv3KernelHeight; ++kernel_row) {
                for (int kernel_column = 0;
                     kernel_column + 1 < config::kConv3KernelWidth;
                     ++kernel_column) {
                    window[input_channel][kernel_row][kernel_column] =
                        window[input_channel][kernel_row][kernel_column + 1];
                }
                window[input_channel][kernel_row]
                      [config::kConv3KernelWidth - 1] =
                    vertical_taps[kernel_row];
            }
        }

        if (padded_row + 1 < config::kConv3KernelHeight ||
            padded_column + 1 < config::kConv3KernelWidth) {
            continue;
        }

        numeric::conv3_acc_t sum =
            arithmetic::begin_with_frozen_bias_order<numeric::conv3_acc_t>(
                bias);
        for (int input_channel = 0;
             input_channel < config::kConv3InChannels; ++input_channel) {
            for (int kernel_row = 0;
                 kernel_row < config::kConv3KernelHeight; ++kernel_row) {
                for (int kernel_column = 0;
                     kernel_column < config::kConv3KernelWidth;
                     ++kernel_column) {
                    arithmetic::accumulate_product(
                        sum,
                        weights[input_channel][kernel_row][kernel_column],
                        window[input_channel][kernel_row][kernel_column]);
                }
            }
        }
        output.write(arithmetic::activate_and_narrow<numeric::data_t>(sum,
                                                                       false));
    }
}

void conv3_stream(
    data_stream_t& input, data_stream_t& output,
    const numeric::data_t
        weights[config::kConv3InChannels][config::kConv3KernelHeight]
               [config::kConv3KernelWidth],
    numeric::data_t bias, int height, int width) {
#pragma HLS INLINE off
    numeric::data_t
        row[config::kConv3InChannels][config::kMaxInputWidth];
    numeric::data_t
        line_buffer[kConv3HistoryRows][config::kConv3InChannels]
                   [kConv3PaddedWidth];
    numeric::data_t
        window[config::kConv3InChannels][config::kConv3KernelHeight]
              [config::kConv3KernelWidth];
    for (int bank = 0; bank < kConv3HistoryRows; ++bank) {
        for (int input_channel = 0;
             input_channel < config::kConv3InChannels; ++input_channel) {
            for (int column = 0; column < kConv3PaddedWidth; ++column) {
                line_buffer[bank][input_channel][column] =
                    static_cast<numeric::data_t>(0);
            }
        }
    }
    for (int input_channel = 0;
         input_channel < config::kConv3InChannels; ++input_channel) {
        for (int kernel_row = 0;
             kernel_row < config::kConv3KernelHeight; ++kernel_row) {
            for (int kernel_column = 0;
                 kernel_column < config::kConv3KernelWidth;
                 ++kernel_column) {
                window[input_channel][kernel_row][kernel_column] =
                    static_cast<numeric::data_t>(0);
            }
        }
    }

    int padded_row = 0;
    for (int source_row = 0; source_row < height; ++source_row) {
        for (int column = 0; column < width; ++column) {
            for (int input_channel = 0;
                 input_channel < config::kConv3InChannels;
                 ++input_channel) {
                row[input_channel][column] = input.read();
            }
        }

        const int repetitions =
            source_row == 0 ? config::kConv3SamePadHeight + 1 : 1;
        for (int repeat = 0; repeat < repetitions; ++repeat) {
            conv3_process_padded_row(row, width, padded_row, line_buffer,
                                     window, weights, bias, output);
            ++padded_row;
        }
    }

    for (int repeat = 0; repeat < config::kConv3SamePadHeight; ++repeat) {
        conv3_process_padded_row(row, width, padded_row, line_buffer, window,
                                 weights, bias, output);
        ++padded_row;
    }
}

void load_runtime_model(
    const numeric::data_t* model,
    numeric::data_t
        conv1_weights[kConv1Lanes][kConv1Groups]
                     [config::kConv1KernelHeight]
                     [config::kConv1KernelWidth],
    numeric::data_t conv1_bias[kConv1Lanes][kConv1Groups],
    numeric::data_t
        conv2_weights[config::kConv2OutChannels]
                     [config::kConv2InChannels],
    numeric::data_t conv2_bias[config::kConv2OutChannels],
    numeric::data_t
        conv3_weights[config::kConv3InChannels]
                     [config::kConv3KernelHeight]
                     [config::kConv3KernelWidth],
    numeric::data_t* conv3_bias) {
#pragma HLS INLINE off
    for (int output_channel = 0;
         output_channel < config::kConv1OutChannels; ++output_channel) {
        const int lane = output_channel % kConv1Lanes;
        const int group = output_channel / kConv1Lanes;
        for (int kernel_row = 0;
             kernel_row < config::kConv1KernelHeight; ++kernel_row) {
            for (int kernel_column = 0;
                 kernel_column < config::kConv1KernelWidth;
                 ++kernel_column) {
#pragma HLS PIPELINE II=1
                const int source_index =
                    (output_channel * config::kConv1KernelHeight +
                     kernel_row) *
                        config::kConv1KernelWidth +
                    kernel_column;
                conv1_weights[lane][group][kernel_row][kernel_column] =
                    model[kConv1WeightsOffset + source_index];
            }
        }
    }
    for (int output_channel = 0;
         output_channel < config::kConv1OutChannels; ++output_channel) {
#pragma HLS PIPELINE II=1
        const int lane = output_channel % kConv1Lanes;
        const int group = output_channel / kConv1Lanes;
        conv1_bias[lane][group] =
            model[kConv1BiasOffset + output_channel];
    }

    for (int output_channel = 0;
         output_channel < config::kConv2OutChannels; ++output_channel) {
        for (int input_channel = 0;
             input_channel < config::kConv2InChannels; ++input_channel) {
#pragma HLS PIPELINE II=1
            conv2_weights[output_channel][input_channel] =
                model[kConv2WeightsOffset +
                      output_channel * config::kConv2InChannels +
                      input_channel];
        }
    }
    for (int output_channel = 0;
         output_channel < config::kConv2OutChannels; ++output_channel) {
#pragma HLS PIPELINE II=1
        conv2_bias[output_channel] =
            model[kConv2BiasOffset + output_channel];
    }

    for (int input_channel = 0;
         input_channel < config::kConv3InChannels; ++input_channel) {
        for (int kernel_row = 0;
             kernel_row < config::kConv3KernelHeight; ++kernel_row) {
            for (int kernel_column = 0;
                 kernel_column < config::kConv3KernelWidth;
                 ++kernel_column) {
#pragma HLS PIPELINE II=1
                const int source_index =
                    (input_channel * config::kConv3KernelHeight +
                     kernel_row) *
                        config::kConv3KernelWidth +
                    kernel_column;
                conv3_weights[input_channel][kernel_row][kernel_column] =
                    model[kConv3WeightsOffset + source_index];
            }
        }
    }
    *conv3_bias = model[kConv3BiasOffset];
}

void run_streaming_core(
    axis_stream_t& input, axis_stream_t& output,
    const numeric::data_t
        conv1_weights[kConv1Lanes][kConv1Groups]
                     [config::kConv1KernelHeight]
                     [config::kConv1KernelWidth],
    const numeric::data_t conv1_bias[kConv1Lanes][kConv1Groups],
    const numeric::data_t
        conv2_weights[config::kConv2OutChannels]
                     [config::kConv2InChannels],
    const numeric::data_t conv2_bias[config::kConv2OutChannels],
    const numeric::data_t
        conv3_weights[config::kConv3InChannels]
                     [config::kConv3KernelHeight]
                     [config::kConv3KernelWidth],
    numeric::data_t conv3_bias, int height, int width) {
#pragma HLS INLINE off
    data_stream_t input_pixels("input_pixels");
    data_stream_t conv1_features("conv1_features");
    data_stream_t conv2_features("conv2_features");
    data_stream_t output_pixels("output_pixels");
#pragma HLS STREAM variable=input_pixels depth=64
#pragma HLS STREAM variable=conv1_features depth=128
#pragma HLS STREAM variable=conv2_features depth=64
#pragma HLS STREAM variable=output_pixels depth=64
#pragma HLS DATAFLOW

    axis_to_scalar(input, input_pixels, height, width);
    conv1_stream(input_pixels, conv1_features, conv1_weights, conv1_bias,
                 height, width);
    conv2_stream(conv1_features, conv2_features, conv2_weights, conv2_bias,
                 height, width);
    conv3_stream(conv2_features, output_pixels, conv3_weights, conv3_bias,
                 height, width);
    scalar_to_axis(output_pixels, output, height, width);
}

}  // namespace

std::uint32_t encode_data_bits(numeric::data_t value) {
#if SRCNN_HLS_FIXED_POINT
    ap_uint<32> bits = value.range(31, 0);
    return bits.to_uint();
#else
    union FloatBits {
        float value;
        std::uint32_t bits;
    } encoded;
    encoded.value = value;
    return encoded.bits;
#endif
}

numeric::data_t decode_data_bits(std::uint32_t bits) {
#if SRCNN_HLS_FIXED_POINT
    numeric::data_t value = 0;
    value.range(31, 0) = bits;
    return value;
#else
    union FloatBits {
        float value;
        std::uint32_t bits;
    } decoded;
    decoded.bits = bits;
    return decoded.value;
#endif
}

void run_srcnn_axis_dataflow(axis_stream_t& input, axis_stream_t& output,
                             const numeric::data_t* model, int height,
                             int width) {
    numeric::data_t
        conv1_weights[kConv1Lanes][kConv1Groups]
                     [config::kConv1KernelHeight]
                     [config::kConv1KernelWidth];
    numeric::data_t conv1_bias[kConv1Lanes][kConv1Groups];
    numeric::data_t
        conv2_weights[config::kConv2OutChannels]
                     [config::kConv2InChannels];
    numeric::data_t conv2_bias[config::kConv2OutChannels];
    numeric::data_t
        conv3_weights[config::kConv3InChannels]
                     [config::kConv3KernelHeight]
                     [config::kConv3KernelWidth];
    numeric::data_t conv3_bias;
#pragma HLS ARRAY_PARTITION variable=conv1_weights complete dim=1
#pragma HLS ARRAY_PARTITION variable=conv1_bias complete dim=1

    load_runtime_model(model, conv1_weights, conv1_bias, conv2_weights,
                       conv2_bias, conv3_weights, &conv3_bias);
    run_streaming_core(input, output, conv1_weights, conv1_bias, conv2_weights,
                       conv2_bias, conv3_weights, conv3_bias, height, width);
}

}  // namespace axis_dataflow
}  // namespace srcnn_hls

extern "C" void srcnn_axis_dataflow_top(
    srcnn_hls::axis_dataflow::axis_stream_t& input,
    srcnn_hls::axis_dataflow::axis_stream_t& output,
    const srcnn_hls::numeric::data_t* model) {
// AXIS depth sizes the Vitis RTL co-simulation verification adapter. It does
// not instantiate a full-frame FIFO in the synthesized deployment datapath.
#pragma HLS INTERFACE mode=axis port=input depth=65025
#pragma HLS INTERFACE mode=axis port=output depth=65025
#pragma HLS INTERFACE mode=m_axi port=model offset=slave bundle=model_mem depth=8129
#pragma HLS INTERFACE mode=s_axilite port=model bundle=control
#pragma HLS INTERFACE mode=s_axilite port=return bundle=control

    srcnn_hls::axis_dataflow::run_srcnn_axis_dataflow(
        input, output, model, srcnn_hls::config::kDeploymentInputHeight,
        srcnn_hls::config::kDeploymentInputWidth);
}

extern "C" void srcnn_axis_dataflow_cosim_top(
    srcnn_hls::axis_dataflow::axis_stream_t& input,
    srcnn_hls::axis_dataflow::axis_stream_t& output,
    const srcnn_hls::numeric::data_t* model, int height, int width) {
// Use the deployment maximum so every legal small-frame regression fits in
// the RTL co-simulation verification adapter.
#pragma HLS INTERFACE mode=axis port=input depth=65025
#pragma HLS INTERFACE mode=axis port=output depth=65025
#pragma HLS INTERFACE mode=m_axi port=model offset=slave bundle=model_mem depth=8129
#pragma HLS INTERFACE mode=s_axilite port=model bundle=control
#pragma HLS INTERFACE mode=s_axilite port=height bundle=control
#pragma HLS INTERFACE mode=s_axilite port=width bundle=control
#pragma HLS INTERFACE mode=s_axilite port=return bundle=control

    srcnn_hls::axis_dataflow::run_srcnn_axis_dataflow(
        input, output, model, height, width);
}
