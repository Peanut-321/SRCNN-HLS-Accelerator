#include "srcnn_hls/project_config.hpp"
#include "srcnn_hls/srcnn_hls.hpp"

#include <cmath>
#include <iostream>
#include <vector>

namespace {

using srcnn_hls::numeric::data_t;

std::size_t elements(const srcnn_hls::LayerShape& shape) {
    return static_cast<std::size_t>(shape.channels) * shape.height * shape.width;
}

double run_one(srcnn_hls::PaddingMode mode) {
    srcnn_hls::NetworkShape shape{};
    if (!srcnn_hls::make_network_shape(1, 1, mode, &shape)) return -1.0;

    std::vector<data_t> input(1, data_t(1));
    std::vector<data_t> conv1_weights(
        srcnn_hls::config::kConv1OutChannels *
            srcnn_hls::config::kConv1MacTerms,
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
            srcnn_hls::config::kConv3MacTerms,
        data_t(0));
    std::vector<data_t> conv3_bias(srcnn_hls::config::kConv3OutChannels,
                                   data_t(0));

    for (int k = 0; k < srcnn_hls::config::kConv1MacTerms; ++k) {
        conv1_weights[k] = data_t(1);
    }
    conv2_weights[0] = data_t(1);
    const int conv3_centre =
        (srcnn_hls::config::kConv3KernelHeight / 2) *
            srcnn_hls::config::kConv3KernelWidth +
        srcnn_hls::config::kConv3KernelWidth / 2;
    conv3_weights[conv3_centre] = data_t(1);

    std::vector<data_t> conv1_output(elements(shape.conv1), data_t(0));
    std::vector<data_t> conv2_output(elements(shape.conv2), data_t(0));
    std::vector<data_t> conv3_output(elements(shape.conv3), data_t(0));
    srcnn_hls::AccumulatorObservations observations{};
    if (!srcnn_hls::run_srcnn_natural(
            input.data(), conv1_weights.data(), conv1_bias.data(),
            conv2_weights.data(), conv2_bias.data(), conv3_weights.data(),
            conv3_bias.data(), conv1_output.data(), conv2_output.data(),
            conv3_output.data(), 1, 1, mode, &observations)) {
        return -1.0;
    }
    return static_cast<double>(conv3_output[0]);
}

}  // namespace

int main() {
    static_assert(srcnn_hls::config::kDeploymentInputHeight == 255 &&
                      srcnn_hls::config::kDeploymentInputWidth == 255,
                  "course deployment geometry must remain 255x255");
    srcnn_hls::NetworkShape deployment_shape{};
    if (!srcnn_hls::make_network_shape(
            srcnn_hls::config::kDeploymentInputHeight,
            srcnn_hls::config::kDeploymentInputWidth,
            srcnn_hls::PaddingMode::kReplicateSame, &deployment_shape) ||
        deployment_shape.conv1.height != 255 ||
        deployment_shape.conv1.width != 255 ||
        deployment_shape.conv2.height != 255 ||
        deployment_shape.conv2.width != 255 ||
        deployment_shape.conv3.height != 255 ||
        deployment_shape.conv3.width != 255) {
        std::cerr << "deployment shape contract mismatch\n";
        return 1;
    }
    const double zero_same = run_one(srcnn_hls::PaddingMode::kZeroSame);
    const double replicate = run_one(srcnn_hls::PaddingMode::kReplicateSame);
    if (std::fabs(zero_same - 1.0) > 0.0 ||
        std::fabs(replicate - 81.0) > 0.0) {
        std::cerr << "padding mode mismatch: zero_same=" << zero_same
                  << " replicate=" << replicate << '\n';
        return 1;
    }
    if (srcnn_hls::srcnn_hls_top(nullptr, nullptr, nullptr, nullptr, nullptr,
                                 nullptr, nullptr, nullptr, nullptr, nullptr,
                                 1, 1, 99) != -1) {
        std::cerr << "invalid padding mode was not rejected\n";
        return 1;
    }
    std::cout << "PASS: zero-same corner=1, replicate-edge corner=81\n";
    return 0;
}
