#include "srcnn/srcnn.hpp"

#include "srcnn/tensor_io.hpp"

#include <algorithm>
#include <array>
#include <fstream>
#include <limits>
#include <stdexcept>
#include <utility>

namespace srcnn {
namespace {

std::size_t output_extent(std::size_t input, std::size_t kernel,
                          std::size_t stride, std::size_t padding,
                          const char* axis) {
    if (kernel == 0 || stride == 0) {
        throw std::invalid_argument("kernel and stride dimensions must be positive");
    }
    if (padding > (std::numeric_limits<std::size_t>::max() - input) / 2) {
        throw std::overflow_error(std::string(axis) + " padded extent overflow");
    }
    const auto padded = input + 2 * padding;
    if (padded < kernel) {
        throw std::invalid_argument(std::string("input is too small along ") + axis +
                                    ": padded extent " + std::to_string(padded) +
                                    " is smaller than kernel " + std::to_string(kernel));
    }
    return (padded - kernel) / stride + 1;
}

}  // namespace

Conv2DLayer::Conv2DLayer(Conv2DConfig config_value,
                         std::vector<float> weights_value,
                         std::vector<float> bias_value)
    : config(config_value), weights(std::move(weights_value)),
      bias(std::move(bias_value)) {
    if (config.in_channels == 0 || config.out_channels == 0 ||
        config.kernel_h == 0 || config.kernel_w == 0 ||
        config.stride_h == 0 || config.stride_w == 0) {
        throw std::invalid_argument("channel, kernel and stride dimensions must be positive");
    }
    const auto expected_weights = checked_element_count(
        {config.out_channels, config.in_channels, config.kernel_h, config.kernel_w});
    if (weights.size() != expected_weights) {
        throw std::invalid_argument("weight count mismatch: expected " +
                                    std::to_string(expected_weights) + ", got " +
                                    std::to_string(weights.size()));
    }
    if (bias.size() != config.out_channels) {
        throw std::invalid_argument("bias count mismatch: expected " +
                                    std::to_string(config.out_channels) + ", got " +
                                    std::to_string(bias.size()));
    }
}

std::size_t Conv2DLayer::weight_offset(std::size_t o, std::size_t i,
                                       std::size_t kh, std::size_t kw) const {
    if (o >= config.out_channels || i >= config.in_channels ||
        kh >= config.kernel_h || kw >= config.kernel_w) {
        throw std::out_of_range("OIHW weight index out of range");
    }
    return (((o * config.in_channels + i) * config.kernel_h + kh) *
            config.kernel_w + kw);
}

Tensor conv2d(const Tensor& input, const Conv2DLayer& layer) {
    const auto& config = layer.config;
    if (input.channels != config.in_channels) {
        throw std::invalid_argument("input channel mismatch: expected " +
                                    std::to_string(config.in_channels) + ", got " +
                                    std::to_string(input.channels));
    }
    if (input.data.size() != checked_element_count(input.shape())) {
        throw std::invalid_argument("input tensor shape/count mismatch");
    }
    const auto out_h = output_extent(input.height, config.kernel_h,
                                     config.stride_h, config.pad_h, "height");
    const auto out_w = output_extent(input.width, config.kernel_w,
                                     config.stride_w, config.pad_w, "width");
    Tensor output(config.out_channels, out_h, out_w);

    for (std::size_t o = 0; o < config.out_channels; ++o) {
        for (std::size_t oh = 0; oh < out_h; ++oh) {
            for (std::size_t ow = 0; ow < out_w; ++ow) {
                float sum = layer.bias[o];  // Bias is added exactly once.
                for (std::size_t i = 0; i < config.in_channels; ++i) {
                    for (std::size_t kh = 0; kh < config.kernel_h; ++kh) {
                        const auto ih_signed = static_cast<std::ptrdiff_t>(oh * config.stride_h + kh) -
                                               static_cast<std::ptrdiff_t>(config.pad_h);
                        if (ih_signed < 0 || ih_signed >= static_cast<std::ptrdiff_t>(input.height)) {
                            continue;
                        }
                        for (std::size_t kw = 0; kw < config.kernel_w; ++kw) {
                            const auto iw_signed = static_cast<std::ptrdiff_t>(ow * config.stride_w + kw) -
                                                   static_cast<std::ptrdiff_t>(config.pad_w);
                            if (iw_signed < 0 || iw_signed >= static_cast<std::ptrdiff_t>(input.width)) {
                                continue;
                            }
                            sum += layer.weights[layer.weight_offset(o, i, kh, kw)] *
                                   input(i, static_cast<std::size_t>(ih_signed),
                                         static_cast<std::size_t>(iw_signed));
                        }
                    }
                }
                output(o, oh, ow) = config.activation == Activation::ReLU
                                         ? std::max(0.0F, sum)
                                         : sum;
            }
        }
    }
    return output;
}

Conv2DLayer load_layer(const std::filesystem::path& weights_path,
                       const std::filesystem::path& bias_path,
                       const Conv2DConfig& config) {
    const auto weight_shape = std::vector<std::size_t>{
        config.out_channels, config.in_channels, config.kernel_h, config.kernel_w};
    const auto bias_shape = std::vector<std::size_t>{config.out_channels};
    auto weights = load_tensor_file(weights_path, "OIHW", weight_shape);
    auto bias = load_tensor_file(bias_path, "O", bias_shape);
    return Conv2DLayer(config, std::move(weights.data), std::move(bias.data));
}

SRCNN::SRCNN(Conv2DLayer conv1, Conv2DLayer conv2, Conv2DLayer conv3)
    : layers_{std::move(conv1), std::move(conv2), std::move(conv3)} {
    if (layers_[0].config.out_channels != layers_[1].config.in_channels ||
        layers_[1].config.out_channels != layers_[2].config.in_channels) {
        throw std::invalid_argument("adjacent SRCNN layer channel counts do not match");
    }
}

std::vector<Conv2DConfig> SRCNN::standard_configs(bool same_padding) {
    return {
        {1, 64, 9, 9, 1, 1, same_padding ? 4U : 0U,
         same_padding ? 4U : 0U, Activation::ReLU},
        {64, 32, 1, 1, 1, 1, 0, 0, Activation::ReLU},
        {32, 1, 5, 5, 1, 1, same_padding ? 2U : 0U,
         same_padding ? 2U : 0U, Activation::None},
    };
}

SRCNN SRCNN::load(const std::filesystem::path& model_directory,
                  bool same_padding) {
    const auto configs = standard_configs(same_padding);
    std::vector<Conv2DLayer> layers;
    for (std::size_t i = 0; i < configs.size(); ++i) {
        const auto prefix = "conv" + std::to_string(i + 1);
        layers.push_back(load_layer(model_directory / (prefix + "_weights.tensor"),
                                    model_directory / (prefix + "_bias.tensor"),
                                    configs[i]));
    }
    return SRCNN(std::move(layers[0]), std::move(layers[1]), std::move(layers[2]));
}

const Conv2DLayer& SRCNN::layer(std::size_t index) const {
    if (index >= layers_.size()) throw std::out_of_range("SRCNN layer index out of range");
    return layers_[index];
}

Tensor SRCNN::run_layer(std::size_t index, const Tensor& input) const {
    return conv2d(input, layer(index));
}

SRCNNOutputs SRCNN::run(const Tensor& input) const {
    auto conv1 = run_layer(0, input);
    auto conv2 = run_layer(1, conv1);
    auto conv3 = run_layer(2, conv2);
    return {std::move(conv1), std::move(conv2), std::move(conv3)};
}

SRCNNOutputs SRCNN::run_and_dump(
    const Tensor& input, const std::filesystem::path& output_directory) const {
    std::filesystem::create_directories(output_directory);
    save_chw(output_directory / "input.tensor", "input", input);
    auto outputs = run(input);
    save_chw(output_directory / "conv1.tensor", "conv1", outputs.conv1);
    save_chw(output_directory / "conv2.tensor", "conv2", outputs.conv2);
    save_chw(output_directory / "conv3.tensor", "conv3", outputs.conv3);
    save_chw(output_directory / "output.tensor", "output", outputs.conv3);
    std::ofstream manifest(output_directory / "run_manifest.txt");
    if (!manifest) {
        throw std::runtime_error("cannot write run manifest in " + output_directory.string());
    }
    manifest << "SRCNN_RUN_V1\n"
             << "dtype float32\ninput_layout CHW\nweight_layout OIHW\n"
             << "operation cross_correlation\n";
    for (std::size_t i = 0; i < layers_.size(); ++i) {
        const auto& c = layers_[i].config;
        manifest << "conv" << i + 1 << " " << c.in_channels << ' ' << c.out_channels
                 << ' ' << c.kernel_h << ' ' << c.kernel_w << ' ' << c.stride_h
                 << ' ' << c.stride_w << ' ' << c.pad_h << ' ' << c.pad_w << ' '
                 << (c.activation == Activation::ReLU ? "relu" : "none") << '\n';
    }
    manifest << "input_checksum " << fnv1a64_hex(input.data) << '\n'
             << "conv1_checksum " << fnv1a64_hex(outputs.conv1.data) << '\n'
             << "conv2_checksum " << fnv1a64_hex(outputs.conv2.data) << '\n'
             << "conv3_checksum " << fnv1a64_hex(outputs.conv3.data) << '\n'
             << toolchain_manifest() << '\n';
    return outputs;
}

}  // namespace srcnn
