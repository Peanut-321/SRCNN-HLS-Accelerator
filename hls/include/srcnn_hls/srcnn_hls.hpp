#pragma once

#include "srcnn_hls/numeric_config.hpp"

namespace srcnn_hls {

struct LayerShape {
    int channels;
    int height;
    int width;
};

struct NetworkShape {
    LayerShape input;
    LayerShape conv1;
    LayerShape conv2;
    LayerShape conv3;
};

struct AccumulatorObservations {
    double preactivation_abs_max[3];
    unsigned long long narrowing_saturation_count[3];
};

enum class PaddingMode {
    kValid = 0,
    kZeroSame = 1,
    kReplicateSame = 2,
};

bool make_network_shape(int input_height, int input_width, PaddingMode padding_mode,
                        NetworkShape* shape);

// Compatibility overload for the frozen P1 vectors: true means zero-same and
// false means valid. Official course execution must use kReplicateSame.
bool make_network_shape(int input_height, int input_width, bool same_padding,
                        NetworkShape* shape);

#ifndef __SYNTHESIS__
// Host-only P2.1 entry point. It exposes pre-activation maxima for the requested
// worst-case/observed gap report; the synthesizable top below contains no such
// diagnostic output.
bool run_srcnn_natural(
    const numeric::data_t* input, const numeric::data_t* conv1_weights,
    const numeric::data_t* conv1_bias,
    const numeric::data_t* conv2_weights,
    const numeric::data_t* conv2_bias,
    const numeric::data_t* conv3_weights,
    const numeric::data_t* conv3_bias, numeric::data_t* conv1_output,
    numeric::data_t* conv2_output, numeric::data_t* conv3_output,
    int input_height, int input_width, PaddingMode padding_mode,
    AccumulatorObservations* observations);

bool run_srcnn_natural(
    const numeric::data_t* input, const numeric::data_t* conv1_weights,
    const numeric::data_t* conv1_bias,
    const numeric::data_t* conv2_weights,
    const numeric::data_t* conv2_bias,
    const numeric::data_t* conv3_weights,
    const numeric::data_t* conv3_bias, numeric::data_t* conv1_output,
    numeric::data_t* conv2_output, numeric::data_t* conv3_output,
    int input_height, int input_width, bool same_padding,
    AccumulatorObservations* observations);
#endif

// P2.1 synthesizable skeleton. There are deliberately no HLS optimization or
// interface pragmas in this phase; P0/P2.3 will establish the concrete AXI
// contract on the x86 tool machine.
extern "C" int srcnn_hls_top(
    const numeric::data_t* input, const numeric::data_t* conv1_weights,
    const numeric::data_t* conv1_bias,
    const numeric::data_t* conv2_weights,
    const numeric::data_t* conv2_bias,
    const numeric::data_t* conv3_weights,
    const numeric::data_t* conv3_bias, numeric::data_t* conv1_output,
    numeric::data_t* conv2_output, numeric::data_t* conv3_output,
    int input_height, int input_width, int padding_mode);

// Experimental structural checkpoint. Conv1 and Conv3 use rolling row buffers
// plus horizontally shifted windows; Conv2 remains a direct 1x1 reduction.
// It deliberately has no PIPELINE/UNROLL/ARRAY_PARTITION pragmas yet: the first
// Vitis schedule report must establish where those pragmas are justified.
extern "C" int srcnn_hls_line_buffer_top(
    const numeric::data_t* input, const numeric::data_t* conv1_weights,
    const numeric::data_t* conv1_bias,
    const numeric::data_t* conv2_weights,
    const numeric::data_t* conv2_bias,
    const numeric::data_t* conv3_weights,
    const numeric::data_t* conv3_bias, numeric::data_t* conv1_output,
    numeric::data_t* conv2_output, numeric::data_t* conv3_output,
    int input_height, int input_width, int padding_mode);

// MAC-A deployment specialization. It shares the same line-buffer and
// arithmetic implementation but fixes the network to replicate-edge padding at
// compile time. Dynamic height/width remain temporarily exposed so the existing
// 1x1, 13x17, and 33x29 host regressions can verify this specialization before
// the final 255x255 deployment wrapper is frozen.
extern "C" int srcnn_hls_line_buffer_replicate_top(
    const numeric::data_t* input, const numeric::data_t* conv1_weights,
    const numeric::data_t* conv1_bias,
    const numeric::data_t* conv2_weights,
    const numeric::data_t* conv2_bias,
    const numeric::data_t* conv3_weights,
    const numeric::data_t* conv3_bias, numeric::data_t* conv1_output,
    numeric::data_t* conv2_output, numeric::data_t* conv3_output,
    int input_height, int input_width);

// Throughput experiment OC2. Conv1 processes two output channels in parallel
// while preserving each channel's original 81-term accumulation order.
extern "C" int srcnn_hls_line_buffer_replicate_oc2_top(
    const numeric::data_t* input, const numeric::data_t* conv1_weights,
    const numeric::data_t* conv1_bias,
    const numeric::data_t* conv2_weights,
    const numeric::data_t* conv2_bias,
    const numeric::data_t* conv3_weights,
    const numeric::data_t* conv3_bias, numeric::data_t* conv1_output,
    numeric::data_t* conv2_output, numeric::data_t* conv3_output,
    int input_height, int input_width);

// OC2 writeback-address experiment. Arithmetic and two-lane MAC scheduling
// remain unchanged; Conv1 walks CHW output planes with an incremental index.
extern "C" int srcnn_hls_line_buffer_replicate_oc2_writeback_top(
    const numeric::data_t* input, const numeric::data_t* conv1_weights,
    const numeric::data_t* conv1_bias,
    const numeric::data_t* conv2_weights,
    const numeric::data_t* conv2_bias,
    const numeric::data_t* conv3_weights,
    const numeric::data_t* conv3_bias, numeric::data_t* conv1_output,
    numeric::data_t* conv2_output, numeric::data_t* conv3_output,
    int input_height, int input_width);

}  // namespace srcnn_hls
