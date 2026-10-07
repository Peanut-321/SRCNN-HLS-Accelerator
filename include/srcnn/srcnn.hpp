#pragma once

#include "srcnn/tensor.hpp"

#include <cstddef>
#include <filesystem>
#include <string>
#include <vector>

// Toolchain fingerprint recorded into generated vector manifests. The field
// values are injected as compile definitions by CMake (see CMakeLists.txt);
// these fallbacks keep a non-CMake build compiling.
#ifndef SRCNN_COMPILER_ID
#define SRCNN_COMPILER_ID "unknown"
#endif
#ifndef SRCNN_COMPILER_VERSION
#define SRCNN_COMPILER_VERSION "unknown"
#endif
#ifndef SRCNN_TARGET_ARCH
#define SRCNN_TARGET_ARCH "unknown"
#endif
#ifndef SRCNN_OPT_LEVEL
#define SRCNN_OPT_LEVEL "unknown"
#endif
#ifndef SRCNN_FP_CONTRACT
#define SRCNN_FP_CONTRACT "unknown"
#endif

namespace srcnn {

inline std::string toolchain_manifest() {
    return std::string("compiler ") + SRCNN_COMPILER_ID + " " +
           SRCNN_COMPILER_VERSION + "\narch " + SRCNN_TARGET_ARCH +
           "\nopt " + SRCNN_OPT_LEVEL + "\nfp_contract " + SRCNN_FP_CONTRACT;
}

enum class Activation { None, ReLU };

struct Conv2DConfig {
    std::size_t in_channels{};
    std::size_t out_channels{};
    std::size_t kernel_h{};
    std::size_t kernel_w{};
    std::size_t stride_h{1};
    std::size_t stride_w{1};
    std::size_t pad_h{};
    std::size_t pad_w{};
    Activation activation{Activation::None};
};

struct Conv2DLayer {
    Conv2DConfig config;
    std::vector<float> weights;  // OIHW
    std::vector<float> bias;     // O

    Conv2DLayer(Conv2DConfig config, std::vector<float> weights,
                std::vector<float> bias);

    std::size_t weight_offset(std::size_t o, std::size_t i,
                              std::size_t kh, std::size_t kw) const;
};

Tensor conv2d(const Tensor& input, const Conv2DLayer& layer);
Conv2DLayer load_layer(const std::filesystem::path& weights_path,
                       const std::filesystem::path& bias_path,
                       const Conv2DConfig& config);

struct SRCNNOutputs {
    Tensor conv1;
    Tensor conv2;
    Tensor conv3;
};

class SRCNN {
public:
    SRCNN(Conv2DLayer conv1, Conv2DLayer conv2, Conv2DLayer conv3);

    static SRCNN load(const std::filesystem::path& model_directory,
                      bool same_padding = true);
    static std::vector<Conv2DConfig> standard_configs(bool same_padding = true);

    const Conv2DLayer& layer(std::size_t index) const;
    Tensor run_layer(std::size_t index, const Tensor& input) const;
    SRCNNOutputs run(const Tensor& input) const;
    SRCNNOutputs run_and_dump(const Tensor& input,
                              const std::filesystem::path& output_directory) const;

private:
    std::vector<Conv2DLayer> layers_;
};

}  // namespace srcnn

