#include "srcnn.h"

namespace {

// Kept in static storage so the approximately 25 MiB of intermediate feature
// maps do not overflow the host stack during C simulation.
static ftmap_t conv1_output[N1][H][W];
static ftmap_t conv2_output[N2][H][W];

inline ftmap_t relu(ftmap_t value) {
    return value > 0.0F ? value : 0.0F;
}

inline int replicate_index(int index, int extent) {
    if (index < 0) return 0;
    if (index >= extent) return extent - 1;
    return index;
}

void conv2(ftmap_t input_ftmap[N1][H][W],
           param_t weights[N2][N1][F2][F2],
           param_t biases[N2],
           ftmap_t output_ftmap[N2][H][W]) {
    for (int output_channel = 0; output_channel < N2; ++output_channel) {
        for (int output_row = 0; output_row < H; ++output_row) {
            for (int output_col = 0; output_col < W; ++output_col) {
                ftmap_t accumulator = biases[output_channel];

                for (int input_channel = 0; input_channel < N1; ++input_channel) {
                    accumulator += weights[output_channel][input_channel][0][0] *
                                   input_ftmap[input_channel]
                                              [output_row][output_col];
                }

                output_ftmap[output_channel][output_row][output_col] =
                    relu(accumulator);
            }
        }
    }
}

void conv3(ftmap_t input_ftmap[N2][H][W],
           param_t weights[N3][N2][F3][F3],
           param_t biases[N3],
           ftmap_t output_ftmap[N3][H][W]) {
    const int padding = F3 / 2;

    for (int output_channel = 0; output_channel < N3; ++output_channel) {
        for (int output_row = 0; output_row < H; ++output_row) {
            for (int output_col = 0; output_col < W; ++output_col) {
                ftmap_t accumulator = biases[output_channel];

                for (int input_channel = 0; input_channel < N2; ++input_channel) {
                    for (int kernel_row = 0; kernel_row < F3; ++kernel_row) {
                        const int input_row = replicate_index(
                            output_row + kernel_row - padding, H);

                        for (int kernel_col = 0; kernel_col < F3; ++kernel_col) {
                            const int input_col = replicate_index(
                                output_col + kernel_col - padding, W);

                            accumulator +=
                                weights[output_channel][input_channel]
                                       [kernel_row][kernel_col] *
                                input_ftmap[input_channel][input_row][input_col];
                        }
                    }
                }

                // Conv3 has no activation or output clamp.
                output_ftmap[output_channel][output_row][output_col] = accumulator;
            }
        }
    }
}

}  // namespace

void srcnn(ftmap_t input_ftmap[N0][H][W],
           param_t conv1_weights[N1][N0][F1][F1],
           param_t conv1_biases[N1],
           param_t conv2_weights[N2][N1][F2][F2],
           param_t conv2_biases[N2],
           param_t conv3_weights[N3][N2][F3][F3],
           param_t conv3_biases[N3],
           ftmap_t output_ftmap[N3][H][W]) {
    conv1(input_ftmap, conv1_weights, conv1_biases, conv1_output);
    conv2(conv1_output, conv2_weights, conv2_biases, conv2_output);
    conv3(conv2_output, conv3_weights, conv3_biases, output_ftmap);
}
