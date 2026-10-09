#pragma once

#include "srcnn_hls/numeric_config.hpp"

#include <cstddef>
#include <cstdint>

#ifdef SRCNN_AXIS_DATAFLOW_HOST_SIM

#include <queue>
#include <stdexcept>

namespace srcnn_hls {
namespace axis_dataflow {

struct axis_word_t {
    std::uint32_t data = 0;
    std::uint8_t keep = 0;
    std::uint8_t strb = 0;
    bool last = false;
};

template <typename T>
class stream_t {
   public:
    stream_t() {}
    explicit stream_t(const char*) {}

    void write(const T& value) { values_.push(value); }

    T read() {
        if (values_.empty()) {
            throw std::underflow_error("read from empty HLS stream");
        }
        const T value = values_.front();
        values_.pop();
        return value;
    }

    bool empty() const { return values_.empty(); }
    std::size_t size() const { return values_.size(); }

   private:
    std::queue<T> values_;
};

using axis_stream_t = stream_t<axis_word_t>;
using data_stream_t = stream_t<numeric::data_t>;

#else

#include <ap_axi_sdata.h>
#include <hls_stream.h>

namespace srcnn_hls {
namespace axis_dataflow {

using axis_word_t = ap_axiu<32, 0, 0, 0>;
using axis_stream_t = hls::stream<axis_word_t>;
using data_stream_t = hls::stream<numeric::data_t>;

#endif

// Runtime model buffer layout. Parameters retain the frozen OIHW/O ordering,
// concatenated into one 32-bit-element array so deployment needs only one
// model pointer instead of six independent AXI masters.
constexpr int kConv1WeightsOffset = 0;
constexpr int kConv1WeightsCount = 64 * 1 * 9 * 9;
constexpr int kConv1BiasOffset = kConv1WeightsOffset + kConv1WeightsCount;
constexpr int kConv1BiasCount = 64;
constexpr int kConv2WeightsOffset = kConv1BiasOffset + kConv1BiasCount;
constexpr int kConv2WeightsCount = 32 * 64 * 1 * 1;
constexpr int kConv2BiasOffset = kConv2WeightsOffset + kConv2WeightsCount;
constexpr int kConv2BiasCount = 32;
constexpr int kConv3WeightsOffset = kConv2BiasOffset + kConv2BiasCount;
constexpr int kConv3WeightsCount = 1 * 32 * 5 * 5;
constexpr int kConv3BiasOffset = kConv3WeightsOffset + kConv3WeightsCount;
constexpr int kConv3BiasCount = 1;
constexpr int kModelElementCount = kConv3BiasOffset + kConv3BiasCount;

static_assert(kModelElementCount == 8129,
              "unexpected SRCNN runtime model size");

std::uint32_t encode_data_bits(numeric::data_t value);
numeric::data_t decode_data_bits(std::uint32_t bits);

// Dynamic dimensions exist only to keep the Mac/Vitis C-sim regression small.
// The synthesizable deployment top below fixes both dimensions to 255.
void run_srcnn_axis_dataflow(axis_stream_t& input, axis_stream_t& output,
                             const numeric::data_t* model, int height,
                             int width);

}  // namespace axis_dataflow
}  // namespace srcnn_hls

// Deployment interface: one 255x255 frame in, one 255x255 frame out. Each AXIS
// beat carries exactly one data_t bit pattern. The model pointer addresses the
// contiguous layout above in PS DDR.
extern "C" void srcnn_axis_dataflow_top(
    srcnn_hls::axis_dataflow::axis_stream_t& input,
    srcnn_hls::axis_dataflow::axis_stream_t& output,
    const srcnn_hls::numeric::data_t* model);

// Small-frame RTL co-simulation wrapper. It is not the deployment IP and is
// kept separate so the exported top retains a fixed 255x255 contract.
extern "C" void srcnn_axis_dataflow_cosim_top(
    srcnn_hls::axis_dataflow::axis_stream_t& input,
    srcnn_hls::axis_dataflow::axis_stream_t& output,
    const srcnn_hls::numeric::data_t* model, int height, int width);
