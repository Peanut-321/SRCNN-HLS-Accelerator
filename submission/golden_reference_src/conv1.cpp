#include "srcnn.h"

namespace {

inline ftmap_t relu(ftmap_t value) {
    return value > 0.0F ? value : 0.0F;
}

inline int replicate_index(int index, int extent) {
    if (index < 0) return 0;
    if (index >= extent) return extent - 1;
    return index;
}

}  // namespace

void conv1(ftmap_t input_ftmap[N0][H][W],
           param_t conv1_weights[N1][N0][F1][F1],
           param_t conv1_biases[N1],
           ftmap_t output_ftmap[N1][H][W]) {
    const int padding = F1 / 2;

    for (int output_channel = 0; output_channel < N1; ++output_channel) {
        for (int output_row = 0; output_row < H; ++output_row) {
            for (int output_col = 0; output_col < W; ++output_col) {
                ftmap_t accumulator = conv1_biases[output_channel];

                for (int input_channel = 0; input_channel < N0; ++input_channel) {
                    for (int kernel_row = 0; kernel_row < F1; ++kernel_row) {
                        const int input_row = replicate_index(
                            output_row + kernel_row - padding, H);

                        for (int kernel_col = 0; kernel_col < F1; ++kernel_col) {
                            const int input_col = replicate_index(
                                output_col + kernel_col - padding, W);

                            accumulator +=
                                conv1_weights[output_channel][input_channel]
                                             [kernel_row][kernel_col] *
                                input_ftmap[input_channel][input_row][input_col];
                        }
                    }
                }

                output_ftmap[output_channel][output_row][output_col] =
                    relu(accumulator);
            }
        }
    }
}
