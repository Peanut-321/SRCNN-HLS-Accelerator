#include "srcnn_hls/axis_dataflow.hpp"
#include <fstream>
#include <iostream>
#include <vector>
#include <stdexcept>
#include <cmath>
using namespace srcnn_hls::axis_dataflow;
using srcnn_hls::numeric::data_t;
std::vector<float> read_floats(const char* name, int count) {
    std::vector<float> values(count);
    std::ifstream file(name, std::ios::binary);
    file.read(reinterpret_cast<char*>(values.data()), count * sizeof(float));
    if (!file || file.peek() != EOF) throw std::runtime_error("invalid float file length");
    return values;
}
void validate_official_profile(const std::vector<float>& pixels,
                               const std::vector<float>& parameters) {
    if (!srcnn_hls::config::kOfficialQ20_12) return;
    for (float value : pixels) {
        if (!std::isfinite(value) || value < 0 || value > 1)
            throw std::runtime_error("official Q20.12 input outside normalized [0,1]");
    }
    const int offsets[] = {0,5184,5248,7296,7328,8128,8129};
    const char* names[] = {"conv1_weights","conv1_bias","conv2_weights",
                           "conv2_bias","conv3_weights","conv3_bias"};
    const srcnn_hls::config::PositiveRational bounds[] = {
        srcnn_hls::config::kConv1WeightAbsMax, srcnn_hls::config::kConv1BiasAbsMax,
        srcnn_hls::config::kConv2WeightAbsMax, srcnn_hls::config::kConv2BiasAbsMax,
        srcnn_hls::config::kConv3WeightAbsMax, srcnn_hls::config::kConv3BiasAbsMax};
    for (int part=0;part<6;++part) {
        const double limit=static_cast<double>(bounds[part].numerator)/bounds[part].denominator;
        for (int i=offsets[part];i<offsets[part+1];++i) {
            if (!std::isfinite(parameters[i]) || std::abs(static_cast<double>(parameters[i])) > limit)
                throw std::runtime_error(std::string("official Q20.12 model range: ")+names[part]);
        }
    }
}
int main(int argc, char** argv) {
    try {
        if (argc != 6) throw std::runtime_error("input_f32 model_f32 output_raw height width");
        const int height = std::stoi(argv[4]), width = std::stoi(argv[5]);
        if (height < 1 || width < 1 || height > 255 || width > 255)
            throw std::runtime_error("dimensions must be in [1,255]");
        const auto pixels = read_floats(argv[1], height * width);
        const auto parameters = read_floats(argv[2], 8129);
        validate_official_profile(pixels,parameters);
        std::vector<data_t> model(8129);
        for (int i=0; i<8129; ++i) model[i] = parameters[i];
        axis_stream_t input, output;
        for (int i=0; i<height*width; ++i) {
            axis_word_t word;
            word.data = encode_data_bits(data_t(pixels[i]));
            word.keep = word.strb = 15;
            word.last = i + 1 == height * width;
            input.write(word);
        }
        if (height == 255 && width == 255) srcnn_axis_dataflow_top(input, output, model.data());
        else srcnn_axis_dataflow_cosim_top(input, output, model.data(), height, width);
        if (!input.empty() || output.size() != size_t(height*width)) throw std::runtime_error("stream counts");
        std::ofstream file(argv[3], std::ios::binary);
        for (int i=0; i<height*width; ++i) {
            const auto word = output.read();
            if (word.keep != 15 || word.strb != 15 || word.last != (i+1 == height*width)) throw std::runtime_error("sidebands");
            const std::uint32_t bits = word.data;
            file.write(reinterpret_cast<const char*>(&bits), sizeof(bits));
        }
        if (!file) throw std::runtime_error("output write");
        std::cout << "PASS HLS host top " << height << "x" << width << " words=" << height*width
                  << " W=" << srcnn_hls::config::kDataTotalBits
                  << " I=" << srcnn_hls::config::kDataIntegerBits
                  << " F=" << srcnn_hls::numeric::kDataFractionBits
                  << " acc=" << srcnn_hls::numeric::Conv1Sizing::kSelectedTotalBits
                  << "/" << srcnn_hls::numeric::Conv2Sizing::kSelectedTotalBits
                  << "/" << srcnn_hls::numeric::Conv3Sizing::kSelectedTotalBits << "\n";
    } catch (const std::exception& error) { std::cerr << error.what() << "\n"; return 1; }
}
