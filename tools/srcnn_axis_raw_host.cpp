#include "srcnn_hls/axis_dataflow.hpp"
#include <fstream>
#include <iostream>
#include <vector>
#include <stdexcept>
using namespace srcnn_hls::axis_dataflow;
using srcnn_hls::numeric::data_t;
std::vector<float> read_floats(const char* name, int count) {
    std::vector<float> values(count);
    std::ifstream file(name, std::ios::binary);
    file.read(reinterpret_cast<char*>(values.data()), count * sizeof(float));
    if (!file || file.peek() != EOF) throw std::runtime_error("invalid float file length");
    return values;
}
int main(int argc, char** argv) {
    try {
        if (argc != 6) throw std::runtime_error("input_f32 model_f32 output_raw height width");
        const int height = std::stoi(argv[4]), width = std::stoi(argv[5]);
        if (height < 1 || width < 1 || height > 255 || width > 255)
            throw std::runtime_error("dimensions must be in [1,255]");
        const auto pixels = read_floats(argv[1], height * width);
        const auto parameters = read_floats(argv[2], 8129);
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
        std::cout << "PASS current HLS host top " << height << "x" << width << " words=" << height*width << "\n";
    } catch (const std::exception& error) { std::cerr << error.what() << "\n"; return 1; }
}
