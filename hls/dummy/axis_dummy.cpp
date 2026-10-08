#include "axis_dummy.hpp"

namespace srcnn_hls {
namespace axis_dummy {

extern "C" void axis_dummy_top(axis_stream_t& input, axis_stream_t& output,
                                int length) {
#pragma HLS INTERFACE axis port=input
#pragma HLS INTERFACE axis port=output
#pragma HLS INTERFACE s_axilite port=length bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control

    if (length <= 0) return;

    for (int index = 0; index < length; ++index) {
#pragma HLS PIPELINE II=1
        const axis_word_t input_word = input.read();
        axis_word_t output_word;
        output_word.data = input_word.data + 1;
        output_word.keep = 0xF;
        output_word.strb = 0xF;
        output_word.last = index + 1 == length;
        output.write(output_word);
    }
}

}  // namespace axis_dummy
}  // namespace srcnn_hls
