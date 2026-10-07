#include "srcnn/srcnn.hpp"
#include "srcnn/tensor_io.hpp"

#include <exception>
#include <filesystem>
#include <iostream>
#include <string>

namespace {
void usage(const char* program) {
    std::cerr << "Usage: " << program
              << " --input FILE --model-dir DIR --output-dir DIR [--padding same|valid]\n";
}
}  // namespace

int main(int argc, char** argv) {
    try {
        std::filesystem::path input_path, model_dir, output_dir;
        bool same_padding = true;
        for (int i = 1; i < argc; ++i) {
            const std::string argument = argv[i];
            if ((argument == "--input" || argument == "--model-dir" ||
                 argument == "--output-dir" || argument == "--padding") && i + 1 >= argc) {
                throw std::invalid_argument("missing value after " + argument);
            }
            if (argument == "--input") input_path = argv[++i];
            else if (argument == "--model-dir") model_dir = argv[++i];
            else if (argument == "--output-dir") output_dir = argv[++i];
            else if (argument == "--padding") {
                const std::string mode = argv[++i];
                if (mode == "same") same_padding = true;
                else if (mode == "valid") same_padding = false;
                else throw std::invalid_argument("padding must be 'same' or 'valid'");
            } else if (argument == "--help") {
                usage(argv[0]);
                return 0;
            } else {
                throw std::invalid_argument("unknown argument: " + argument);
            }
        }
        if (input_path.empty() || model_dir.empty() || output_dir.empty()) {
            usage(argv[0]);
            return 2;
        }
        const auto input = srcnn::load_chw(input_path);
        const auto model = srcnn::SRCNN::load(model_dir, same_padding);
        const auto output = model.run_and_dump(input, output_dir);
        std::cout << "conv1 [" << output.conv1.channels << ',' << output.conv1.height
                  << ',' << output.conv1.width << "] checksum="
                  << srcnn::fnv1a64_hex(output.conv1.data) << '\n';
        std::cout << "conv2 [" << output.conv2.channels << ',' << output.conv2.height
                  << ',' << output.conv2.width << "] checksum="
                  << srcnn::fnv1a64_hex(output.conv2.data) << '\n';
        std::cout << "conv3 [" << output.conv3.channels << ',' << output.conv3.height
                  << ',' << output.conv3.width << "] checksum="
                  << srcnn::fnv1a64_hex(output.conv3.data) << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "srcnn_run: " << error.what() << '\n';
        return 1;
    }
}

