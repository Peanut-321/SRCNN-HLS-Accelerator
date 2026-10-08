#include "axis_dummy.hpp"

extern "C" void axis_dummy_top(
    srcnn_hls::axis_dummy::axis_stream_t& input,
    srcnn_hls::axis_dummy::axis_stream_t& output, int length) {
#pragma HLS INTERFACE mode=axis port=input
#pragma HLS INTERFACE mode=axis port=output
#pragma HLS INTERFACE mode=s_axilite port=length bundle=control
#pragma HLS INTERFACE mode=s_axilite port=return bundle=control

    if (length <= 0) return;

    for (int index = 0; index < length; ++index) {
#pragma HLS PIPELINE II=1
        const srcnn_hls::axis_dummy::axis_word_t input_word = input.read();
        srcnn_hls::axis_dummy::axis_word_t output_word;
        output_word.data = input_word.data + 1;
        output_word.keep = 0xF;
        output_word.strb = 0xF;
        output_word.last = index + 1 == length;
        output.write(output_word);
    }
}
