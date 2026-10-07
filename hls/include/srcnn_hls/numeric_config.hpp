#pragma once

#include "srcnn_hls/project_config.hpp"

#include <cstdint>
#include <limits>

#ifndef SRCNN_HLS_FIXED_POINT
#define SRCNN_HLS_FIXED_POINT 0
#endif

#if SRCNN_HLS_FIXED_POINT
// The open-source Xilinx simulation headers predate libc++'s inline namespace
// for std::complex and otherwise collide with Apple Clang. This suppresses only
// their unused std::complex specializations on macOS. Vitis uses its own vendor
// headers and does not take this compatibility branch.
#if defined(__APPLE__) && !defined(__SYNTHESIS__)
#ifndef __AP_INT_SPECIAL_H__
#define __AP_INT_SPECIAL_H__
#endif
#ifndef __AP_FIXED_SPECIAL_H__
#define __AP_FIXED_SPECIAL_H__
#endif
#endif
#include <ap_fixed.h>
#endif

namespace srcnn_hls {
namespace numeric {

constexpr int kDataFractionBits =
    config::kDataTotalBits - config::kDataIntegerBits;
constexpr int kAccumulatorFractionBits = 2 * kDataFractionBits;

static_assert(config::kDataTotalBits > 1, "data_t needs sign and value bits");
static_assert(config::kDataIntegerBits >= 1,
              "P2.1 requires a signed data_t with at least one integer bit");
static_assert(kDataFractionBits >= 0, "data_t fractional width cannot be negative");
static_assert(config::kDataTotalBits < 63,
              "P2.1 constexpr raw-bound arithmetic uses uint64_t");
static_assert(kDataFractionBits < 31,
              "P2.1 constexpr scale must fit comfortably in uint64_t");

constexpr std::uint64_t pow2_u64(int exponent) {
    return exponent >= 0 && exponent < 64 ? (1ULL << exponent) : 0ULL;
}

constexpr std::uint64_t ceil_div_u64(std::uint64_t numerator,
                                     std::uint64_t denominator) {
    return numerator / denominator + (numerator % denominator == 0 ? 0ULL : 1ULL);
}

constexpr int ceil_log2_u64(std::uint64_t value) {
    if (value <= 1ULL) return 0;
    int bits = 0;
    std::uint64_t remaining = value - 1ULL;
    // Fixed bound keeps the header synthesizable; no recursion or unbounded
    // loop is allowed in code seen by the HLS frontend.
    for (int bit = 0; bit < 64; ++bit) {
        if (remaining != 0ULL) ++bits;
        remaining >>= 1U;
    }
    return bits;
}

constexpr std::uint64_t kDataScale = pow2_u64(kDataFractionBits);
constexpr std::uint64_t kDataPositiveMaxRaw =
    pow2_u64(config::kDataTotalBits - 1) - 1ULL;

constexpr bool rational_conversion_fits(config::PositiveRational bound) {
    return bound.denominator != 0 &&
           bound.numerator <=
               std::numeric_limits<std::uint64_t>::max() / kDataScale;
}

constexpr std::uint64_t rational_to_raw(config::PositiveRational bound) {
    return ceil_div_u64(bound.numerator * kDataScale, bound.denominator);
}

static_assert(config::kInputAbsMax.denominator != 0,
              "input range denominator cannot be zero");
static_assert(config::kConv1WeightAbsMax.denominator != 0 &&
                  config::kConv2WeightAbsMax.denominator != 0 &&
                  config::kConv3WeightAbsMax.denominator != 0,
              "weight range denominator cannot be zero");
static_assert(config::kConv1BiasAbsMax.denominator != 0 &&
                  config::kConv2BiasAbsMax.denominator != 0 &&
                  config::kConv3BiasAbsMax.denominator != 0,
              "bias range denominator cannot be zero");
static_assert(rational_conversion_fits(config::kInputAbsMax) &&
                  rational_conversion_fits(config::kConv1WeightAbsMax) &&
                  rational_conversion_fits(config::kConv2WeightAbsMax) &&
                  rational_conversion_fits(config::kConv3WeightAbsMax) &&
                  rational_conversion_fits(config::kConv1BiasAbsMax) &&
                  rational_conversion_fits(config::kConv2BiasAbsMax) &&
                  rational_conversion_fits(config::kConv3BiasAbsMax),
              "dynamic-range rational overflows raw-code conversion");

constexpr std::uint64_t kInputAbsMaxRaw =
    rational_to_raw(config::kInputAbsMax);
constexpr std::uint64_t kConv1WeightAbsMaxRaw =
    rational_to_raw(config::kConv1WeightAbsMax);
constexpr std::uint64_t kConv2WeightAbsMaxRaw =
    rational_to_raw(config::kConv2WeightAbsMax);
constexpr std::uint64_t kConv3WeightAbsMaxRaw =
    rational_to_raw(config::kConv3WeightAbsMax);
constexpr std::uint64_t kConv1BiasAbsMaxRaw =
    rational_to_raw(config::kConv1BiasAbsMax);
constexpr std::uint64_t kConv2BiasAbsMaxRaw =
    rational_to_raw(config::kConv2BiasAbsMax);
constexpr std::uint64_t kConv3BiasAbsMaxRaw =
    rational_to_raw(config::kConv3BiasAbsMax);

static_assert(kInputAbsMaxRaw <= kDataPositiveMaxRaw,
              "declared input range does not fit data_t");
static_assert(kConv1WeightAbsMaxRaw <= kDataPositiveMaxRaw &&
                  kConv2WeightAbsMaxRaw <= kDataPositiveMaxRaw &&
                  kConv3WeightAbsMaxRaw <= kDataPositiveMaxRaw,
              "declared weight range does not fit data_t");
static_assert(kConv1BiasAbsMaxRaw <= kDataPositiveMaxRaw &&
                  kConv2BiasAbsMaxRaw <= kDataPositiveMaxRaw &&
                  kConv3BiasAbsMaxRaw <= kDataPositiveMaxRaw,
              "declared bias range does not fit data_t");

template <std::uint64_t MacTerms, std::uint64_t InputAbsMaxRaw,
          std::uint64_t WeightAbsMaxRaw, std::uint64_t BiasAbsMaxRaw,
          bool OverrideEnabled, int OverrideIntegerBits>
struct AccumulatorSizing {
    static_assert(MacTerms > 0, "a convolution must contain at least one MAC term");
    static_assert(InputAbsMaxRaw == 0 ||
                      MacTerms <= std::numeric_limits<std::uint64_t>::max() /
                                      InputAbsMaxRaw,
                  "MAC bound overflows uint64_t at terms*input");
    static constexpr std::uint64_t kTermsTimesInput =
        MacTerms * InputAbsMaxRaw;
    static_assert(WeightAbsMaxRaw == 0 ||
                      kTermsTimesInput <=
                          std::numeric_limits<std::uint64_t>::max() /
                              WeightAbsMaxRaw,
                  "MAC bound overflows uint64_t at *weight");
    static constexpr std::uint64_t kMacBoundRaw =
        kTermsTimesInput * WeightAbsMaxRaw;
    static_assert(BiasAbsMaxRaw == 0 ||
                      kDataScale <= std::numeric_limits<std::uint64_t>::max() /
                                        BiasAbsMaxRaw,
                  "bias alignment overflows uint64_t");
    static constexpr std::uint64_t kBiasBoundRaw =
        BiasAbsMaxRaw * kDataScale;
    static_assert(kMacBoundRaw <=
                      std::numeric_limits<std::uint64_t>::max() - kBiasBoundRaw,
                  "pre-activation bound overflows uint64_t");
    static constexpr std::uint64_t kPreactivationBoundRaw =
        kMacBoundRaw + kBiasBoundRaw;
    static_assert(kPreactivationBoundRaw <
                      std::numeric_limits<std::uint64_t>::max(),
                  "pre-activation bound leaves no room for endpoint guard");

    // Raw accumulator scale is 2^(Fx+Fw). +1 protects the inclusive positive
    // endpoint: signed ap_fixed max is 2^(W-1)-1 raw units. This is the integer
    // equivalent of ceil(log2(bound))+1, corrected for exact powers of two.
    static constexpr int kRawMagnitudeBits =
        ceil_log2_u64(kPreactivationBoundRaw + 1ULL);
    static constexpr int kUnclampedDerivedIntegerBits =
        1 + kRawMagnitudeBits - kAccumulatorFractionBits;
    static constexpr int kDerivedIntegerBits =
        kUnclampedDerivedIntegerBits < 1 ? 1 : kUnclampedDerivedIntegerBits;
    static constexpr int kSelectedIntegerBits =
        OverrideEnabled ? OverrideIntegerBits : kDerivedIntegerBits;
    static constexpr int kSelectedTotalBits =
        kSelectedIntegerBits + kAccumulatorFractionBits;
    static constexpr bool kOverrideEnabled = OverrideEnabled;
    static constexpr bool kOverrideTightens =
        OverrideEnabled && OverrideIntegerBits < kDerivedIntegerBits;

    static_assert(!OverrideEnabled || kSelectedTotalBits > 0,
                  "enabled accumulator override produces a non-positive width");

    // Conservative conversion from product-scale accumulator units back to
    // data_t units. Ceiling is safe for AP_RND_CONV; final clipping models
    // data_t's AP_SAT policy.
    static constexpr std::uint64_t kUnclampedOutputAbsMaxRaw =
        ceil_div_u64(kPreactivationBoundRaw, kDataScale);
    static constexpr bool kWouldSaturateData =
        kUnclampedOutputAbsMaxRaw > kDataPositiveMaxRaw;
    static constexpr std::uint64_t kOutputAbsMaxRaw =
        kWouldSaturateData ? kDataPositiveMaxRaw : kUnclampedOutputAbsMaxRaw;

#ifndef __SYNTHESIS__
    static constexpr long double mac_bound() {
        return static_cast<long double>(kMacBoundRaw) /
               static_cast<long double>(kDataScale * kDataScale);
    }
    static constexpr long double preactivation_bound() {
        return static_cast<long double>(kPreactivationBoundRaw) /
               static_cast<long double>(kDataScale * kDataScale);
    }
#endif
};

using Conv1Sizing = AccumulatorSizing<
    config::kConv1MacTerms, kInputAbsMaxRaw, kConv1WeightAbsMaxRaw,
    kConv1BiasAbsMaxRaw, config::kConv1AccumulatorOverride.enabled,
    config::kConv1AccumulatorOverride.integer_bits>;

using Conv2Sizing = AccumulatorSizing<
    config::kConv2MacTerms, Conv1Sizing::kOutputAbsMaxRaw,
    kConv2WeightAbsMaxRaw, kConv2BiasAbsMaxRaw,
    config::kConv2AccumulatorOverride.enabled,
    config::kConv2AccumulatorOverride.integer_bits>;

using Conv3Sizing = AccumulatorSizing<
    config::kConv3MacTerms, Conv2Sizing::kOutputAbsMaxRaw,
    kConv3WeightAbsMaxRaw, kConv3BiasAbsMaxRaw,
    config::kConv3AccumulatorOverride.enabled,
    config::kConv3AccumulatorOverride.integer_bits>;

static_assert(config::kAllowWorstCaseDataSaturation ||
                  (!Conv1Sizing::kWouldSaturateData &&
                   !Conv2Sizing::kWouldSaturateData &&
                   !Conv3Sizing::kWouldSaturateData),
              "declared worst-case chain exceeds data_t; widen data_t or explicitly allow saturation");

#if SRCNN_HLS_FIXED_POINT
// All four requested ap_fixed template parameters are explicit. AP_SAT is a
// defensive anti-wrap policy, not an automatic event counter and not assumed
// resource-free; explicit saturation diagnostics belong to P2.2.
typedef ap_fixed<config::kDataTotalBits, config::kDataIntegerBits,
                 AP_RND_CONV, AP_SAT>
    data_t;
typedef ap_fixed<Conv1Sizing::kSelectedTotalBits,
                 Conv1Sizing::kSelectedIntegerBits, AP_TRN, AP_SAT>
    conv1_acc_t;
typedef ap_fixed<Conv2Sizing::kSelectedTotalBits,
                 Conv2Sizing::kSelectedIntegerBits, AP_TRN, AP_SAT>
    conv2_acc_t;
typedef ap_fixed<Conv3Sizing::kSelectedTotalBits,
                 Conv3Sizing::kSelectedIntegerBits, AP_TRN, AP_SAT>
    conv3_acc_t;
#else
// Float compatibility mode intentionally uses binary32 for both data and every
// layer accumulator. This is the P2.1 bitwise gate against the frozen P1 dumps.
typedef float data_t;
typedef float conv1_acc_t;
typedef float conv2_acc_t;
typedef float conv3_acc_t;
#endif

}  // namespace numeric
}  // namespace srcnn_hls
