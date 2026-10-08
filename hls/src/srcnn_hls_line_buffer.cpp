#include "srcnn_hls/srcnn_hls.hpp"

#include "srcnn_hls/arithmetic.hpp"
#include "srcnn_hls/project_config.hpp"

namespace srcnn_hls {
namespace {

int chw_offset(int channel, int row, int column, int height, int width) {
    return (channel * height + row) * width + column;
}

int clamp_index(int index, int extent) {
    if (index < 0) return 0;
    if (index >= extent) return extent - 1;
    return index;
}

// Conv1 is deliberately specialized instead of sharing the generic circular
// row-bank implementation below. Its previous `head + kernel_row` bank lookup
// put a runtime bank selector on every window refill. Here each of the eight
// history banks has one fixed delay: bank 0 is one row old and bank 7 is eight
// rows old. A padded raster stream feeds those delays and a 9x9 horizontal
// shift window.
constexpr int kConv1HistoryRows = config::kConv1KernelHeight - 1;
constexpr int kConv1MaxStreamWidth =
    config::kMaxInputWidth + 2 * config::kConv1SamePadWidth;

static_assert(config::kConv1InChannels == 1,
              "specialized Conv1 path requires one input channel");
static_assert(config::kConv1KernelHeight == config::kConv1KernelWidth,
              "specialized Conv1 path requires a square kernel");
static_assert(config::kConv1SamePadHeight == config::kConv1SamePadWidth,
              "specialized Conv1 path requires symmetric padding");

template <bool ReplicateOnly>
numeric::data_t read_conv1_stream_sample(const numeric::data_t* input,
                                         int input_height, int input_width,
                                         int stream_row, int stream_column,
                                         int padding,
                                         PaddingMode padding_mode) {
    int source_row = stream_row - padding;
    int source_column = stream_column - padding;
    const bool in_bounds = source_row >= 0 && source_row < input_height &&
                           source_column >= 0 && source_column < input_width;

    if (!in_bounds) {
        // ReplicateOnly is a compile-time deployment choice. The specialized
        // top therefore contains no runtime padding-mode selection here, while
        // the existing generic top retains its original behaviour.
        if (!ReplicateOnly &&
            padding_mode != PaddingMode::kReplicateSame) {
            return static_cast<numeric::data_t>(0);
        }
        source_row = clamp_index(source_row, input_height);
        source_column = clamp_index(source_column, input_width);
    }

    return input[chw_offset(0, source_row, source_column, input_height,
                            input_width)];
}

template <bool ReplicateOnly, int OutputLanes>
void conv1_static_line_buffer(const numeric::data_t* input,
                              const numeric::data_t* weights,
                              const numeric::data_t* bias,
                              numeric::data_t* output, int input_height,
                              int input_width, int output_height,
                              int output_width, int padding,
                              PaddingMode padding_mode) {
    static_assert(config::kStrideHeight == 1 && config::kStrideWidth == 1,
                  "streaming Conv1 requires unit stride");
    static_assert(OutputLanes > 0,
                  "Conv1 output-channel lane count must be positive");
    static_assert(config::kConv1OutChannels % OutputLanes == 0,
                  "Conv1 output channels must divide evenly into lanes");

    constexpr int kOutputChannelGroups =
        config::kConv1OutChannels / OutputLanes;

    // Eight fixed row delays replace the old nine-bank circular buffer. The
    // stream includes the same-padding halo, hence the small +8 width bound.
    numeric::data_t line_buffer[kConv1HistoryRows][kConv1MaxStreamWidth];
    numeric::data_t
        window[config::kConv1KernelHeight][config::kConv1KernelWidth];

    // Bank weights by output lane so every unrolled lane has an independent
    // read port. Each lane still accumulates its own 81 products in the frozen
    // kernel-row/kernel-column order; only different output channels execute
    // in parallel.
    numeric::data_t
        weights_by_lane[OutputLanes][kOutputChannelGroups]
                       [config::kConv1KernelHeight]
                       [config::kConv1KernelWidth];
    numeric::data_t bias_by_lane[OutputLanes][kOutputChannelGroups];
#pragma HLS ARRAY_PARTITION variable=weights_by_lane complete dim=1
#pragma HLS ARRAY_PARTITION variable=bias_by_lane complete dim=1

    for (int group = 0; group < kOutputChannelGroups; ++group) {
        for (int lane = 0; lane < OutputLanes; ++lane) {
            const int output_channel = group * OutputLanes + lane;
            bias_by_lane[lane][group] = bias[output_channel];
            for (int kernel_row = 0;
                 kernel_row < config::kConv1KernelHeight; ++kernel_row) {
                for (int kernel_column = 0;
                     kernel_column < config::kConv1KernelWidth;
                     ++kernel_column) {
                    const int weight_index =
                        (output_channel * config::kConv1KernelHeight +
                         kernel_row) *
                            config::kConv1KernelWidth +
                        kernel_column;
                    weights_by_lane[lane][group][kernel_row][kernel_column] =
                        weights[weight_index];
                }
            }
        }
    }

    // The first eight raster rows read delay cells before every bank has
    // received real stream data. Explicit initialization makes those warm-up
    // reads defined in C simulation and synthesis.
    for (int bank = 0; bank < kConv1HistoryRows; ++bank) {
        for (int column = 0; column < kConv1MaxStreamWidth; ++column) {
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

    const int stream_height = input_height + 2 * padding;
    const int stream_width = input_width + 2 * padding;

    for (int stream_row = 0; stream_row < stream_height; ++stream_row) {
        for (int stream_column = 0; stream_column < stream_width;
             ++stream_column) {
            const numeric::data_t sample =
                read_conv1_stream_sample<ReplicateOnly>(
                    input, input_height, input_width, stream_row,
                    stream_column, padding, padding_mode);

            // Read all old values before updating any bank. These explicit
            // fixed-bank accesses prevent synthesis from rebuilding the old
            // runtime circular-bank multiplexer.
            const numeric::data_t delayed_1 =
                line_buffer[0][stream_column];
            const numeric::data_t delayed_2 =
                line_buffer[1][stream_column];
            const numeric::data_t delayed_3 =
                line_buffer[2][stream_column];
            const numeric::data_t delayed_4 =
                line_buffer[3][stream_column];
            const numeric::data_t delayed_5 =
                line_buffer[4][stream_column];
            const numeric::data_t delayed_6 =
                line_buffer[5][stream_column];
            const numeric::data_t delayed_7 =
                line_buffer[6][stream_column];
            const numeric::data_t delayed_8 =
                line_buffer[7][stream_column];

            line_buffer[0][stream_column] = sample;
            line_buffer[1][stream_column] = delayed_1;
            line_buffer[2][stream_column] = delayed_2;
            line_buffer[3][stream_column] = delayed_3;
            line_buffer[4][stream_column] = delayed_4;
            line_buffer[5][stream_column] = delayed_5;
            line_buffer[6][stream_column] = delayed_6;
            line_buffer[7][stream_column] = delayed_7;

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

            // The first valid 9x9 window ends at raster coordinate (8, 8).
            if (stream_row + 1 < config::kConv1KernelHeight ||
                stream_column + 1 < config::kConv1KernelWidth) {
                continue;
            }

            const int output_row =
                stream_row - (config::kConv1KernelHeight - 1);
            const int output_column =
                stream_column - (config::kConv1KernelWidth - 1);

            for (int group = 0; group < kOutputChannelGroups; ++group) {
                numeric::conv1_acc_t sums[OutputLanes];
#pragma HLS ARRAY_PARTITION variable=sums complete dim=1
                for (int lane = 0; lane < OutputLanes; ++lane) {
#pragma HLS UNROLL
                    sums[lane] = arithmetic::begin_with_frozen_bias_order<
                        numeric::conv1_acc_t>(bias_by_lane[lane][group]);
                }
                for (int kernel_row = 0;
                     kernel_row < config::kConv1KernelHeight; ++kernel_row) {
                    for (int kernel_column = 0;
                         kernel_column < config::kConv1KernelWidth;
                         ++kernel_column) {
                        // The frozen natural implementation skips out-of-frame
                        // zero-padding terms instead of multiplying by zero.
                        // Preserve that detail for bitwise float equivalence.
                        if (!ReplicateOnly &&
                            padding_mode == PaddingMode::kZeroSame) {
                            const int source_row =
                                output_row + kernel_row - padding;
                            const int source_column =
                                output_column + kernel_column - padding;
                            if (source_row < 0 || source_row >= input_height ||
                                source_column < 0 ||
                                source_column >= input_width) {
                                continue;
                            }
                        }
                        const numeric::data_t sample =
                            window[kernel_row][kernel_column];
                        for (int lane = 0; lane < OutputLanes; ++lane) {
#pragma HLS UNROLL
                            arithmetic::accumulate_product(
                                sums[lane],
                                weights_by_lane[lane][group][kernel_row]
                                               [kernel_column],
                                sample);
                        }
                    }
                }
                for (int lane = 0; lane < OutputLanes; ++lane) {
                    const int output_channel = group * OutputLanes + lane;
                    output[chw_offset(output_channel, output_row,
                                      output_column, output_height,
                                      output_width)] =
                        arithmetic::activate_and_narrow<numeric::data_t>(
                            sums[lane], true);
                }
            }
        }
    }
}

template <int InputChannels, int KernelSize>
void load_row(const numeric::data_t* input, int input_height, int input_width,
              int source_row, PaddingMode padding_mode,
              numeric::data_t row_buffer[InputChannels]
                                        [config::kMaxInputWidth],
              bool* row_is_valid) {
    int resolved_row = source_row;
    *row_is_valid = source_row >= 0 && source_row < input_height;
    if (!*row_is_valid && padding_mode == PaddingMode::kReplicateSame) {
        resolved_row = clamp_index(source_row, input_height);
        *row_is_valid = true;
    }

    for (int input_channel = 0; input_channel < InputChannels;
         ++input_channel) {
        for (int input_column = 0; input_column < input_width;
             ++input_column) {
            if (*row_is_valid) {
                row_buffer[input_channel][input_column] =
                    input[chw_offset(input_channel, resolved_row, input_column,
                                     input_height, input_width)];
            } else {
                row_buffer[input_channel][input_column] =
                    static_cast<numeric::data_t>(0);
            }
        }
    }
}

template <int InputChannels, int KernelSize>
void load_window_column(
    numeric::data_t line_buffer[KernelSize][InputChannels]
                                       [config::kMaxInputWidth],
    const bool row_is_valid[KernelSize], int head, int input_width,
    int source_column, PaddingMode padding_mode, int window_column,
    numeric::data_t window[InputChannels][KernelSize][KernelSize],
    bool window_is_valid[KernelSize][KernelSize]) {
    int resolved_column = source_column;
    bool column_is_valid =
        source_column >= 0 && source_column < input_width;
    if (!column_is_valid && padding_mode == PaddingMode::kReplicateSame) {
        resolved_column = clamp_index(source_column, input_width);
        column_is_valid = true;
    }

    for (int kernel_row = 0; kernel_row < KernelSize; ++kernel_row) {
        int bank = head + kernel_row;
        if (bank >= KernelSize) bank -= KernelSize;
        window_is_valid[kernel_row][window_column] =
            row_is_valid[bank] && column_is_valid;
        for (int input_channel = 0; input_channel < InputChannels;
             ++input_channel) {
            window[input_channel][kernel_row][window_column] =
                window_is_valid[kernel_row][window_column]
                    ? line_buffer[bank][input_channel][resolved_column]
                    : static_cast<numeric::data_t>(0);
        }
    }
}

template <typename Accumulator, int InputChannels, int OutputChannels,
          int KernelSize>
void conv2d_line_buffer(const numeric::data_t* input,
                        const numeric::data_t* weights,
                        const numeric::data_t* bias,
                        numeric::data_t* output, int input_height,
                        int input_width, int output_height, int output_width,
                        int padding, PaddingMode padding_mode, bool relu) {
    static_assert(config::kStrideHeight == 1 && config::kStrideWidth == 1,
                  "rolling line buffer currently requires unit stride");

    // Row bank is the leading dimension so one complete bank can be passed to
    // load_row without pretending a strided [channel][bank] slice is
    // contiguous. This layout also makes the circular-bank ownership explicit.
    numeric::data_t
        line_buffer[KernelSize][InputChannels][config::kMaxInputWidth];
    numeric::data_t window[InputChannels][KernelSize][KernelSize];
    bool row_is_valid[KernelSize];
    bool window_is_valid[KernelSize][KernelSize];

    int head = 0;
    for (int kernel_row = 0; kernel_row < KernelSize; ++kernel_row) {
        load_row<InputChannels, KernelSize>(
            input, input_height, input_width, kernel_row - padding,
            padding_mode, line_buffer[kernel_row],
            &row_is_valid[kernel_row]);
    }

    for (int output_row = 0; output_row < output_height; ++output_row) {
        for (int kernel_column = 0; kernel_column < KernelSize;
             ++kernel_column) {
            load_window_column<InputChannels, KernelSize>(
                line_buffer, row_is_valid, head, input_width,
                kernel_column - padding, padding_mode, kernel_column, window,
                window_is_valid);
        }

        for (int output_column = 0; output_column < output_width;
             ++output_column) {
            for (int output_channel = 0; output_channel < OutputChannels;
                 ++output_channel) {
                Accumulator sum =
                    arithmetic::begin_with_frozen_bias_order<Accumulator>(
                        bias[output_channel]);
                for (int input_channel = 0; input_channel < InputChannels;
                     ++input_channel) {
                    for (int kernel_row = 0; kernel_row < KernelSize;
                         ++kernel_row) {
                        for (int kernel_column = 0;
                             kernel_column < KernelSize; ++kernel_column) {
                            // The natural baseline skips zero-padding terms.
                            // Keeping the same skip preserves binary32 MAC
                            // order and signed-zero behaviour exactly.
                            if (!window_is_valid[kernel_row][kernel_column]) {
                                continue;
                            }
                            const int weight_index =
                                (((output_channel * InputChannels +
                                   input_channel) *
                                      KernelSize +
                                  kernel_row) *
                                     KernelSize +
                                 kernel_column);
                            arithmetic::accumulate_product(
                                sum, weights[weight_index],
                                window[input_channel][kernel_row]
                                      [kernel_column]);
                        }
                    }
                }
                output[chw_offset(output_channel, output_row, output_column,
                                  output_height, output_width)] =
                    arithmetic::activate_and_narrow<numeric::data_t>(sum,
                                                                      relu);
            }

            if (output_column + 1 < output_width) {
                for (int input_channel = 0; input_channel < InputChannels;
                     ++input_channel) {
                    for (int kernel_row = 0; kernel_row < KernelSize;
                         ++kernel_row) {
                        for (int kernel_column = 0;
                             kernel_column + 1 < KernelSize;
                             ++kernel_column) {
                            window[input_channel][kernel_row][kernel_column] =
                                window[input_channel][kernel_row]
                                      [kernel_column + 1];
                        }
                    }
                }
                for (int kernel_row = 0; kernel_row < KernelSize;
                     ++kernel_row) {
                    for (int kernel_column = 0;
                         kernel_column + 1 < KernelSize; ++kernel_column) {
                        window_is_valid[kernel_row][kernel_column] =
                            window_is_valid[kernel_row][kernel_column + 1];
                    }
                }
                load_window_column<InputChannels, KernelSize>(
                    line_buffer, row_is_valid, head, input_width,
                    output_column + KernelSize - padding, padding_mode,
                    KernelSize - 1, window, window_is_valid);
            }
        }

        if (output_row + 1 < output_height) {
            const int next_source_row = output_row + KernelSize - padding;
            load_row<InputChannels, KernelSize>(
                input, input_height, input_width, next_source_row,
                padding_mode, line_buffer[head], &row_is_valid[head]);
            ++head;
            if (head == KernelSize) head = 0;
        }
    }
}

template <typename Accumulator, int InputChannels, int OutputChannels>
void conv2d_pointwise(const numeric::data_t* input,
                      const numeric::data_t* weights,
                      const numeric::data_t* bias, numeric::data_t* output,
                      int height, int width, bool relu) {
    for (int output_row = 0; output_row < height; ++output_row) {
        for (int output_column = 0; output_column < width; ++output_column) {
            for (int output_channel = 0; output_channel < OutputChannels;
                 ++output_channel) {
                Accumulator sum =
                    arithmetic::begin_with_frozen_bias_order<Accumulator>(
                        bias[output_channel]);
                for (int input_channel = 0; input_channel < InputChannels;
                     ++input_channel) {
                    arithmetic::accumulate_product(
                        sum,
                        weights[output_channel * InputChannels +
                                input_channel],
                        input[chw_offset(input_channel, output_row,
                                         output_column, height, width)]);
                }
                output[chw_offset(output_channel, output_row, output_column,
                                  height, width)] =
                    arithmetic::activate_and_narrow<numeric::data_t>(sum,
                                                                      relu);
            }
        }
    }
}

template <bool ReplicateOnly, int Conv1OutputLanes>
bool run_line_buffer_impl(
    const numeric::data_t* input, const numeric::data_t* conv1_weights,
    const numeric::data_t* conv1_bias,
    const numeric::data_t* conv2_weights,
    const numeric::data_t* conv2_bias,
    const numeric::data_t* conv3_weights,
    const numeric::data_t* conv3_bias, numeric::data_t* conv1_output,
    numeric::data_t* conv2_output, numeric::data_t* conv3_output,
    int input_height, int input_width, PaddingMode padding_mode) {
    if (ReplicateOnly &&
        padding_mode != PaddingMode::kReplicateSame) {
        return false;
    }

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
    const int conv1_padding =
        same_padding ? config::kConv1SamePadHeight : 0;
    const int conv3_padding =
        same_padding ? config::kConv3SamePadHeight : 0;

    conv1_static_line_buffer<ReplicateOnly, Conv1OutputLanes>(
        input, conv1_weights, conv1_bias, conv1_output, shape.input.height,
        shape.input.width, shape.conv1.height, shape.conv1.width,
        conv1_padding, padding_mode);
    conv2d_pointwise<numeric::conv2_acc_t, config::kConv2InChannels,
                     config::kConv2OutChannels>(
        conv1_output, conv2_weights, conv2_bias, conv2_output,
        shape.conv1.height, shape.conv1.width, true);
    conv2d_line_buffer<numeric::conv3_acc_t, config::kConv3InChannels,
                       config::kConv3OutChannels,
                       config::kConv3KernelHeight>(
        conv2_output, conv3_weights, conv3_bias, conv3_output,
        shape.conv2.height, shape.conv2.width, shape.conv3.height,
        shape.conv3.width, conv3_padding, padding_mode, false);
    return true;
}

}  // namespace

extern "C" int srcnn_hls_line_buffer_top(
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
    return run_line_buffer_impl<false, 1>(
               input, conv1_weights, conv1_bias, conv2_weights, conv2_bias,
               conv3_weights, conv3_bias, conv1_output, conv2_output,
               conv3_output, input_height, input_width,
               static_cast<PaddingMode>(padding_mode))
               ? 0
               : -1;
}

extern "C" int srcnn_hls_line_buffer_replicate_top(
    const numeric::data_t* input, const numeric::data_t* conv1_weights,
    const numeric::data_t* conv1_bias,
    const numeric::data_t* conv2_weights,
    const numeric::data_t* conv2_bias,
    const numeric::data_t* conv3_weights,
    const numeric::data_t* conv3_bias, numeric::data_t* conv1_output,
    numeric::data_t* conv2_output, numeric::data_t* conv3_output,
    int input_height, int input_width) {
    return run_line_buffer_impl<true, 1>(
               input, conv1_weights, conv1_bias, conv2_weights, conv2_bias,
               conv3_weights, conv3_bias, conv1_output, conv2_output,
               conv3_output, input_height, input_width,
               PaddingMode::kReplicateSame)
               ? 0
               : -1;
}

extern "C" int srcnn_hls_line_buffer_replicate_oc2_top(
    const numeric::data_t* input, const numeric::data_t* conv1_weights,
    const numeric::data_t* conv1_bias,
    const numeric::data_t* conv2_weights,
    const numeric::data_t* conv2_bias,
    const numeric::data_t* conv3_weights,
    const numeric::data_t* conv3_bias, numeric::data_t* conv1_output,
    numeric::data_t* conv2_output, numeric::data_t* conv3_output,
    int input_height, int input_width) {
    return run_line_buffer_impl<true, 2>(
               input, conv1_weights, conv1_bias, conv2_weights, conv2_bias,
               conv3_weights, conv3_bias, conv1_output, conv2_output,
               conv3_output, input_height, input_width,
               PaddingMode::kReplicateSame)
               ? 0
               : -1;
}

}  // namespace srcnn_hls
