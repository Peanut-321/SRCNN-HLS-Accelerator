#pragma once

#include <cstdint>

namespace srcnn_hls {
namespace config {

// -----------------------------------------------------------------------------
// Fixed channel/kernel topology (source: course project specification; not TBD).
// -----------------------------------------------------------------------------
constexpr int kConv1InChannels = 1;
constexpr int kConv1OutChannels = 64;
constexpr int kConv1KernelHeight = 9;
constexpr int kConv1KernelWidth = 9;

constexpr int kConv2InChannels = 64;
constexpr int kConv2OutChannels = 32;
constexpr int kConv2KernelHeight = 1;
constexpr int kConv2KernelWidth = 1;

constexpr int kConv3InChannels = 32;
constexpr int kConv3OutChannels = 1;
constexpr int kConv3KernelHeight = 5;
constexpr int kConv3KernelWidth = 5;

// Course deployment contract: stride one and same-size replicate-edge padding
// with radii 4/0/2. The P1 regression vectors additionally retain explicit
// zero-same and valid modes; those modes are tests, not deployment semantics.
constexpr int kStrideHeight = 1;
constexpr int kStrideWidth = 1;
constexpr int kConv1SamePadHeight = 4;
constexpr int kConv1SamePadWidth = 4;
constexpr int kConv2SamePadHeight = 0;
constexpr int kConv2SamePadWidth = 0;
constexpr int kConv3SamePadHeight = 2;
constexpr int kConv3SamePadWidth = 2;

static_assert(kStrideHeight > 0 && kStrideWidth > 0,
              "convolution strides must be positive");

// Derived from topology. These are deliberately not repeated as magic numbers
// in the accumulator type declarations.
constexpr int kConv1MacTerms =
    kConv1InChannels * kConv1KernelHeight * kConv1KernelWidth;
constexpr int kConv2MacTerms =
    kConv2InChannels * kConv2KernelHeight * kConv2KernelWidth;
constexpr int kConv3MacTerms =
    kConv3InChannels * kConv3KernelHeight * kConv3KernelWidth;

static_assert(kConv1MacTerms == 81, "Conv1 topology changed unexpectedly");
static_assert(kConv2MacTerms == 64, "Conv2 topology changed unexpectedly");
static_assert(kConv3MacTerms == 800, "Conv3 topology changed unexpectedly");
static_assert(kConv1OutChannels == kConv2InChannels &&
                  kConv2OutChannels == kConv3InChannels,
              "adjacent SRCNN channel counts must match");

// -----------------------------------------------------------------------------
// Structural parameters. Keep every architecture input in this file so the
// arithmetic policy does not move when csynth forces a loop/buffer redesign.
// -----------------------------------------------------------------------------

// The Golden starter fixes the already-bicubic-upsampled network input to one
// 255x255 frame. Smaller dimensions remain legal for host regression tests.
constexpr int kMaxInputHeight = 255;
constexpr int kMaxInputWidth = 255;
constexpr int kDeploymentInputHeight = 255;
constexpr int kDeploymentInputWidth = 255;

// Dependency: P0a's implemented overlay resource budget. P2.1 keeps natural
// serial loops, so all factors remain one. These are placeholders only and are
// not consumed by an UNROLL pragma in this phase.
constexpr int kConv1UnrollFactor = 1;
constexpr int kConv2UnrollFactor = 1;
constexpr int kConv3UnrollFactor = 1;

// Dependency: kernel topology (known). The future line-buffer storage contains
// K-1 previous rows. P2.1 records the derived shape but does not implement the
// line buffer yet.
constexpr int kConv1LineBufferRows = kConv1KernelHeight - 1;
constexpr int kConv2LineBufferRows = kConv2KernelHeight - 1;
constexpr int kConv3LineBufferRows = kConv3KernelHeight - 1;

// Whole deployment frame. This is not a promise that the synthesized design
// stores a full frame on chip; P2.3 may stream or tile after the first csynth.
constexpr int kTileHeight = kMaxInputHeight;
constexpr int kTileWidth = kMaxInputWidth;

// -----------------------------------------------------------------------------
// TBD-derived numeric contract.
// -----------------------------------------------------------------------------

struct PositiveRational {
    std::uint64_t numerator;
    std::uint64_t denominator;
};

// Dependency: official model/input dynamic ranges. The wide Q24.8 placeholder
// is selected only so the all-ones 13x13 valid sanity path and all five random
// regression sets can be represented. P2.2a verifies the mechanism, not the
// deployment quality/resource choice; P2.2b must revisit it with official
// weights and course images.
constexpr int kDataTotalBits = 32;
constexpr int kDataIntegerBits = 24;

// Dependency: input normalization contract. Placeholder is |X| <= 1.
constexpr PositiveRational kInputAbsMax = {1, 1};

// Dependency: official weight files. All three |W|max values are conservative
// placeholders for the committed random vectors, whose weights lie in [-1,1].
constexpr PositiveRational kConv1WeightAbsMax = {1, 1};
constexpr PositiveRational kConv2WeightAbsMax = {1, 1};
constexpr PositiveRational kConv3WeightAbsMax = {1, 1};

// Dependency: official bias files. Placeholders cover the committed random
// vectors; bias is included in the pre-activation accumulator bound.
constexpr PositiveRational kConv1BiasAbsMax = {1, 1};
constexpr PositiveRational kConv2BiasAbsMax = {1, 1};
constexpr PositiveRational kConv3BiasAbsMax = {1, 1};

// A tightened accumulator is an explicit OPT-D action. The enabled bit is
// separate from the value: zero is a legal ap_fixed integer-width value and is
// therefore not used as a sentinel. Default is always the derived worst case.
struct AccumulatorIntegerOverride {
    bool enabled;
    int integer_bits;
};

constexpr AccumulatorIntegerOverride kConv1AccumulatorOverride = {false, 0};
constexpr AccumulatorIntegerOverride kConv2AccumulatorOverride = {false, 0};
constexpr AccumulatorIntegerOverride kConv3AccumulatorOverride = {false, 0};

// P2.1 requires the declared worst-case chain to fit data_t. Set this true only
// as an explicit, documented experiment; P2.2 must then count/diagnose every
// narrowing saturation with a wider shadow value.
constexpr bool kAllowWorstCaseDataSaturation = false;

}  // namespace config
}  // namespace srcnn_hls
