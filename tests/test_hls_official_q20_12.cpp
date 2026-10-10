#include "srcnn_hls/numeric_config.hpp"
#include "srcnn_hls/axis_dataflow.hpp"
#include <cstdint>
#include <iostream>
#include <stdexcept>

using namespace srcnn_hls;
static_assert(config::kOfficialQ20_12,"compile with SRCNN_HLS_OFFICIAL_Q20_12=1");
static_assert(config::kDataTotalBits==32 && config::kDataIntegerBits==20,"Q20.12 data contract");
static_assert(numeric::kDataFractionBits==12 && numeric::kAccumulatorFractionBits==24,"fractional counts");
static_assert(numeric::Conv1Sizing::kSelectedTotalBits==31 && numeric::Conv1Sizing::kSelectedIntegerBits==7,"Conv1 sizing");
static_assert(numeric::Conv2Sizing::kSelectedTotalBits==37 && numeric::Conv2Sizing::kSelectedIntegerBits==13,"Conv2 sizing");
static_assert(numeric::Conv3Sizing::kSelectedTotalBits==44 && numeric::Conv3Sizing::kSelectedIntegerBits==20,"Conv3 sizing");
static_assert(!config::kAllowWorstCaseDataSaturation,"keep saturation guard enabled");
static_assert(!numeric::Conv1Sizing::kOverrideEnabled && !numeric::Conv2Sizing::kOverrideEnabled &&
              !numeric::Conv3Sizing::kOverrideEnabled,"derive accumulators without overrides");
static_assert(!numeric::Conv1Sizing::kWouldSaturateData && !numeric::Conv2Sizing::kWouldSaturateData &&
              !numeric::Conv3Sizing::kWouldSaturateData,"declared chain must fit");

int main() {
    const int halves[]={1,3,5,-1,-3,-5};
    const std::int32_t expected[]={0,2,2,0,-2,-2};
    for(int i=0;i<6;++i) {
        const numeric::data_t value(static_cast<double>(halves[i])/8192);
        const auto bits=axis_dataflow::encode_data_bits(value);
        if(bits!=static_cast<std::uint32_t>(expected[i]) || axis_dataflow::decode_data_bits(bits)!=value)
            throw std::runtime_error("signed convergent rounding/AXIS codec");
    }
    const numeric::data_t negative(-0.125);
    if(axis_dataflow::encode_data_bits(negative)!=static_cast<std::uint32_t>(-512))
        throw std::runtime_error("raw Q20.12 scale");
    if(numeric::data_t(1e20).range(31,0).to_uint()!=0x7fffffffU ||
       numeric::data_t(-1e20).range(31,0).to_uint()!=0x80000000U)
        throw std::runtime_error("data_t saturation endpoints");
    std::cout<<"PASS official Q20.12: data 32/20/12, accumulators 31/37/44, guards enabled, codec/rounding/saturation\n";
}
