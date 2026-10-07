#include "srcnn_hls/numeric_config.hpp"
#include "srcnn_hls/project_config.hpp"
#include "srcnn_hls/srcnn_hls.hpp"

#include <algorithm>
#include <iostream>
#include <type_traits>
#include <vector>

namespace {

std::size_t element_count(const srcnn_hls::LayerShape& shape) {
    return static_cast<std::size_t>(shape.channels) *
           static_cast<std::size_t>(shape.height) *
           static_cast<std::size_t>(shape.width);
}

template <typename Sizing>
void print_sizing(const char* layer) {
    std::cout << layer << ": mac_bound="
              << static_cast<double>(Sizing::mac_bound())
              << " preactivation_bound="
              << static_cast<double>(Sizing::preactivation_bound())
              << " derived_I=" << Sizing::kDerivedIntegerBits
              << " selected_I=" << Sizing::kSelectedIntegerBits
              << " selected_W=" << Sizing::kSelectedTotalBits
              << " override=" << (Sizing::kOverrideEnabled ? "on" : "off")
              << '\n';
}

using ExactPowerSizing = srcnn_hls::numeric::AccumulatorSizing<
    64, srcnn_hls::numeric::kDataScale, srcnn_hls::numeric::kDataScale, 0,
    false, 0>;
using UnitNoBiasSizing = srcnn_hls::numeric::AccumulatorSizing<
    1, srcnn_hls::numeric::kDataScale, srcnn_hls::numeric::kDataScale, 0,
    false, 0>;
using UnitWithBiasSizing = srcnn_hls::numeric::AccumulatorSizing<
    1, srcnn_hls::numeric::kDataScale, srcnn_hls::numeric::kDataScale,
    srcnn_hls::numeric::kDataScale, false, 0>;
using ZeroSizing =
    srcnn_hls::numeric::AccumulatorSizing<1, 0, 0, 0, false, 0>;
using OverrideSizing = srcnn_hls::numeric::AccumulatorSizing<
    64, srcnn_hls::numeric::kDataScale, srcnn_hls::numeric::kDataScale, 0,
    true, 9>;

static_assert(ExactPowerSizing::kDerivedIntegerBits == 8,
              "an exact positive power-of-two bound needs an endpoint guard");
static_assert(UnitWithBiasSizing::kDerivedIntegerBits ==
                  UnitNoBiasSizing::kDerivedIntegerBits + 1,
              "bias must participate in accumulator-width derivation");
static_assert(ZeroSizing::kDerivedIntegerBits == 1,
              "zero bound must still produce a legal signed accumulator");
static_assert(OverrideSizing::kOverrideEnabled &&
                  OverrideSizing::kSelectedIntegerBits == 9 &&
                  OverrideSizing::kDerivedIntegerBits == 8,
              "explicit accumulator override channel is not functioning");

template <typename Data>
bool all_equal(const std::vector<Data>& values, double expected) {
    for (const auto value : values) {
        if (static_cast<double>(value) != expected) return false;
    }
    return true;
}

template <typename Data>
bool only_first_equals(const std::vector<Data>& values, double first) {
    if (values.empty() || static_cast<double>(values[0]) != first) return false;
    for (std::size_t index = 1; index < values.size(); ++index) {
        if (static_cast<double>(values[index]) != 0.0) return false;
    }
    return true;
}

}  // namespace

int main() {
    static_assert(SRCNN_HLS_FIXED_POINT == 1,
                  "fixed smoke test must instantiate ap_fixed types");
    static_assert(!std::is_same<srcnn_hls::numeric::data_t, float>::value,
                  "fixed smoke test unexpectedly selected float");
    static_assert(srcnn_hls::numeric::data_t::width ==
                          srcnn_hls::config::kDataTotalBits &&
                      srcnn_hls::numeric::data_t::iwidth ==
                          srcnn_hls::config::kDataIntegerBits &&
                      srcnn_hls::numeric::data_t::qmode == AP_RND_CONV &&
                      srcnn_hls::numeric::data_t::omode == AP_SAT,
                  "data_t did not preserve all four explicit template parameters");
    static_assert(srcnn_hls::numeric::conv1_acc_t::width ==
                          srcnn_hls::numeric::Conv1Sizing::kSelectedTotalBits &&
                      srcnn_hls::numeric::conv1_acc_t::iwidth ==
                          srcnn_hls::numeric::Conv1Sizing::kSelectedIntegerBits &&
                      srcnn_hls::numeric::conv1_acc_t::qmode == AP_TRN &&
                      srcnn_hls::numeric::conv1_acc_t::omode == AP_SAT &&
                      srcnn_hls::numeric::conv2_acc_t::width ==
                          srcnn_hls::numeric::Conv2Sizing::kSelectedTotalBits &&
                      srcnn_hls::numeric::conv2_acc_t::iwidth ==
                          srcnn_hls::numeric::Conv2Sizing::kSelectedIntegerBits &&
                      srcnn_hls::numeric::conv2_acc_t::qmode == AP_TRN &&
                      srcnn_hls::numeric::conv2_acc_t::omode == AP_SAT &&
                      srcnn_hls::numeric::conv3_acc_t::width ==
                          srcnn_hls::numeric::Conv3Sizing::kSelectedTotalBits &&
                      srcnn_hls::numeric::conv3_acc_t::iwidth ==
                          srcnn_hls::numeric::Conv3Sizing::kSelectedIntegerBits &&
                      srcnn_hls::numeric::conv3_acc_t::qmode == AP_TRN &&
                      srcnn_hls::numeric::conv3_acc_t::omode == AP_SAT,
                  "accumulator aliases did not preserve derived W/I/TRN/SAT");
    static_assert(srcnn_hls::config::kConv1MacTerms == 81 &&
                      srcnn_hls::config::kConv2MacTerms == 64 &&
                      srcnn_hls::config::kConv3MacTerms == 800,
                  "MAC term counts must remain topology-derived");
    static_assert(
        srcnn_hls::numeric::Conv1Sizing::kSelectedIntegerBits ==
                srcnn_hls::numeric::Conv1Sizing::kDerivedIntegerBits &&
            srcnn_hls::numeric::Conv2Sizing::kSelectedIntegerBits ==
                srcnn_hls::numeric::Conv2Sizing::kDerivedIntegerBits &&
            srcnn_hls::numeric::Conv3Sizing::kSelectedIntegerBits ==
                srcnn_hls::numeric::Conv3Sizing::kDerivedIntegerBits,
        "P2.1 defaults must use the derived worst-case widths");

    srcnn_hls::NetworkShape shape;
    if (!srcnn_hls::make_network_shape(1, 1, true, &shape)) {
        std::cerr << "fixed smoke: shape construction failed\n";
        return 1;
    }

    using srcnn_hls::numeric::data_t;
    std::vector<data_t> input(1, data_t(0));
    std::vector<data_t> conv1_weights(
        srcnn_hls::config::kConv1OutChannels *
            srcnn_hls::config::kConv1InChannels *
            srcnn_hls::config::kConv1KernelHeight *
            srcnn_hls::config::kConv1KernelWidth,
        data_t(0));
    std::vector<data_t> conv1_bias(srcnn_hls::config::kConv1OutChannels,
                                   data_t(0));
    std::vector<data_t> conv2_weights(
        srcnn_hls::config::kConv2OutChannels *
            srcnn_hls::config::kConv2InChannels,
        data_t(0));
    std::vector<data_t> conv2_bias(srcnn_hls::config::kConv2OutChannels,
                                   data_t(0));
    std::vector<data_t> conv3_weights(
        srcnn_hls::config::kConv3OutChannels *
            srcnn_hls::config::kConv3InChannels *
            srcnn_hls::config::kConv3KernelHeight *
            srcnn_hls::config::kConv3KernelWidth,
        data_t(0));
    std::vector<data_t> conv3_bias(srcnn_hls::config::kConv3OutChannels,
                                   data_t(0));
    std::vector<data_t> conv1_output(element_count(shape.conv1), data_t(1));
    std::vector<data_t> conv2_output(element_count(shape.conv2), data_t(1));
    std::vector<data_t> conv3_output(element_count(shape.conv3), data_t(1));
    srcnn_hls::AccumulatorObservations observations{};

    const bool ok = srcnn_hls::run_srcnn_natural(
        input.data(), conv1_weights.data(), conv1_bias.data(),
        conv2_weights.data(), conv2_bias.data(), conv3_weights.data(),
        conv3_bias.data(), conv1_output.data(), conv2_output.data(),
        conv3_output.data(), 1, 1, true, &observations);
    if (!ok) {
        std::cerr << "fixed smoke: execution failed\n";
        return 1;
    }
    if (!all_equal(conv1_output, 0.0) || !all_equal(conv2_output, 0.0) ||
        !all_equal(conv3_output, 0.0)) {
        std::cerr << "fixed smoke: diagnostic zero path mismatch\n";
        return 1;
    }
    std::fill(conv1_output.begin(), conv1_output.end(), data_t(1));
    std::fill(conv2_output.begin(), conv2_output.end(), data_t(1));
    std::fill(conv3_output.begin(), conv3_output.end(), data_t(1));
    if (srcnn_hls::srcnn_hls_top(
            input.data(), conv1_weights.data(), conv1_bias.data(),
            conv2_weights.data(), conv2_bias.data(), conv3_weights.data(),
            conv3_bias.data(), conv1_output.data(), conv2_output.data(),
            conv3_output.data(), 1, 1, 1) != 0) {
        std::cerr << "fixed smoke: synthesizable top execution failed\n";
        return 1;
    }
    if (!all_equal(conv1_output, 0.0) || !all_equal(conv2_output, 0.0) ||
        !all_equal(conv3_output, 0.0)) {
        std::cerr << "fixed smoke: top zero path mismatch\n";
        return 1;
    }

    // One sparse, exactly representable path exercises multiplication, bias,
    // negative ReLU suppression, data narrowing, and Conv3's signed no-clamp
    // output without becoming the P2.2 statistical error harness.
    input[0] = data_t(0.5);
    const int conv1_centre =
        (srcnn_hls::config::kConv1KernelHeight / 2) *
            srcnn_hls::config::kConv1KernelWidth +
        srcnn_hls::config::kConv1KernelWidth / 2;
    conv1_weights[conv1_centre] = data_t(0.5);
    conv1_bias[0] = data_t(-0.125);
    conv1_weights[srcnn_hls::config::kConv1MacTerms + conv1_centre] =
        data_t(-0.5);
    conv2_weights[0] = data_t(0.5);
    conv2_weights[srcnn_hls::config::kConv2InChannels] = data_t(-0.5);
    const int conv3_centre =
        (srcnn_hls::config::kConv3KernelHeight / 2) *
            srcnn_hls::config::kConv3KernelWidth +
        srcnn_hls::config::kConv3KernelWidth / 2;
    conv3_weights[conv3_centre] = data_t(-0.5);
    conv3_bias[0] = data_t(0.015625);
    std::fill(conv1_output.begin(), conv1_output.end(), data_t(1));
    std::fill(conv2_output.begin(), conv2_output.end(), data_t(1));
    std::fill(conv3_output.begin(), conv3_output.end(), data_t(1));
    if (!srcnn_hls::run_srcnn_natural(
            input.data(), conv1_weights.data(), conv1_bias.data(),
            conv2_weights.data(), conv2_bias.data(), conv3_weights.data(),
            conv3_bias.data(), conv1_output.data(), conv2_output.data(),
            conv3_output.data(), 1, 1, true, &observations) ||
        !only_first_equals(conv1_output, 0.125) ||
        !only_first_equals(conv2_output, 0.0625) ||
        !only_first_equals(conv3_output, -0.015625)) {
        std::cerr << "fixed smoke: diagnostic sparse arithmetic mismatch\n";
        return 1;
    }
    std::fill(conv1_output.begin(), conv1_output.end(), data_t(1));
    std::fill(conv2_output.begin(), conv2_output.end(), data_t(1));
    std::fill(conv3_output.begin(), conv3_output.end(), data_t(1));
    if (srcnn_hls::srcnn_hls_top(
            input.data(), conv1_weights.data(), conv1_bias.data(),
            conv2_weights.data(), conv2_bias.data(), conv3_weights.data(),
            conv3_bias.data(), conv1_output.data(), conv2_output.data(),
            conv3_output.data(), 1, 1, 1) != 0 ||
        !only_first_equals(conv1_output, 0.125) ||
        !only_first_equals(conv2_output, 0.0625) ||
        !only_first_equals(conv3_output, -0.015625)) {
        std::cerr << "fixed smoke: top sparse arithmetic mismatch\n";
        return 1;
    }

    std::cout << "data_t: W=" << srcnn_hls::config::kDataTotalBits
              << " I=" << srcnn_hls::config::kDataIntegerBits
              << " F=" << srcnn_hls::numeric::kDataFractionBits << '\n';
    print_sizing<srcnn_hls::numeric::Conv1Sizing>("conv1_acc_t");
    print_sizing<srcnn_hls::numeric::Conv2Sizing>("conv2_acc_t");
    print_sizing<srcnn_hls::numeric::Conv3Sizing>("conv3_acc_t");
    std::cout << "PASS: fixed types, width regressions, zero and sparse smoke paths\n";
    return 0;
}
