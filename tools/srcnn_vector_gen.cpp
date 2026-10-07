#include "srcnn/srcnn.hpp"
#include "srcnn/tensor_io.hpp"

#include <cstdint>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <random>
#include <string>
#include <vector>

namespace {
float next_value(std::mt19937& generator, int magnitude) {
    const auto span = static_cast<std::uint32_t>(2 * magnitude + 1);
    const auto integer = static_cast<int>(generator() % span) - magnitude;
    return static_cast<float>(integer) / static_cast<float>(magnitude);
}

std::vector<float> random_values(std::mt19937& generator, std::size_t count,
                                 int magnitude = 1000) {
    std::vector<float> values(count);
    for (auto& value : values) value = next_value(generator, magnitude);
    return values;
}
}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc < 2 || argc > 6) {
            std::cerr << "Usage: " << argv[0]
                      << " OUTPUT_DIR [same|valid] [HEIGHT] [WIDTH] [SEED]\n";
            return 2;
        }
        const std::filesystem::path root = argv[1];
        const std::string padding = argc >= 3 ? argv[2] : "same";
        if (padding != "same" && padding != "valid") {
            throw std::invalid_argument("padding must be 'same' or 'valid'");
        }
        const bool same_padding = padding == "same";
        const auto height = static_cast<std::size_t>(argc >= 4 ? std::stoull(argv[3]) : 13);
        const auto width = static_cast<std::size_t>(argc >= 5 ? std::stoull(argv[4]) : 17);
        const auto seed = static_cast<std::uint32_t>(argc >= 6 ? std::stoull(argv[5]) : 0x5EED1234U);
        if (!same_padding && (height < 13 || width < 13)) {
            throw std::invalid_argument("valid three-layer SRCNN requires height and width >= 13");
        }

        std::mt19937 generator(seed);
        srcnn::Tensor input(1, height, width);
        input.data = random_values(generator, input.size());
        const auto configs = srcnn::SRCNN::standard_configs(same_padding);
        std::vector<srcnn::Conv2DLayer> layers;
        const auto model_dir = root / "model";
        std::filesystem::create_directories(model_dir);
        for (std::size_t i = 0; i < configs.size(); ++i) {
            const auto& config = configs[i];
            const auto weight_shape = std::vector<std::size_t>{
                config.out_channels, config.in_channels, config.kernel_h, config.kernel_w};
            auto weights = random_values(generator, srcnn::checked_element_count(weight_shape), 100);
            auto bias = random_values(generator, config.out_channels, 100);
            const auto prefix = "conv" + std::to_string(i + 1);
            srcnn::save_tensor_file(model_dir / (prefix + "_weights.tensor"),
                                    {prefix + "_weights", "OIHW", weight_shape, weights});
            srcnn::save_tensor_file(model_dir / (prefix + "_bias.tensor"),
                                    {prefix + "_bias", "O", {config.out_channels}, bias});
            layers.emplace_back(config, std::move(weights), std::move(bias));
        }
        srcnn::SRCNN model(std::move(layers[0]), std::move(layers[1]), std::move(layers[2]));
        model.run_and_dump(input, root / "dumps");

        std::ofstream manifest(root / "manifest.txt");
        if (!manifest) throw std::runtime_error("cannot write manifest");
        manifest << "SRCNN_VECTOR_SET_V1\nseed " << seed
                 << "\ndtype float32\ninput_layout CHW\nweight_layout OIHW\n"
                 << "operation cross_correlation\nstride 1 1\npadding " << padding
                 << "\ninput_shape 1 " << height << ' ' << width << '\n'
                 << srcnn::toolchain_manifest() << '\n';
        std::cout << "Generated deterministic vector set in " << root << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "srcnn_vector_gen: " << error.what() << '\n';
        return 1;
    }
}
