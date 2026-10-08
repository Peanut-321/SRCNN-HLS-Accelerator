#pragma once

#ifdef SRCNN_AXIS_DUMMY_HOST_SIM

#include <cstddef>
#include <cstdint>
#include <queue>
#include <stdexcept>

namespace srcnn_hls {
namespace axis_dummy {

struct axis_word_t {
    std::uint32_t data = 0;
    std::uint8_t keep = 0;
    std::uint8_t strb = 0;
    bool last = false;
};

class axis_stream_t {
   public:
    void write(const axis_word_t& word) { words_.push(word); }

    axis_word_t read() {
        if (words_.empty()) {
            throw std::underflow_error("read from empty AXI stream");
        }
        const axis_word_t word = words_.front();
        words_.pop();
        return word;
    }

    bool empty() const { return words_.empty(); }
    std::size_t size() const { return words_.size(); }

   private:
    std::queue<axis_word_t> words_;
};

#else

#include <ap_axi_sdata.h>
#include <hls_stream.h>

namespace srcnn_hls {
namespace axis_dummy {

using axis_word_t = ap_axiu<32, 0, 0, 0>;
using axis_stream_t = hls::stream<axis_word_t>;

#endif

}  // namespace axis_dummy
}  // namespace srcnn_hls

extern "C" void axis_dummy_top(srcnn_hls::axis_dummy::axis_stream_t& input,
                               srcnn_hls::axis_dummy::axis_stream_t& output,
                               int length);
