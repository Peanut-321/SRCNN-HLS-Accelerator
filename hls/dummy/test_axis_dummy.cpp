#include "axis_dummy.hpp"

#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using ::axis_dummy_top;
using srcnn_hls::axis_dummy::axis_stream_t;
using srcnn_hls::axis_dummy::axis_word_t;

std::uint32_t word_data(const axis_word_t& word) {
    return static_cast<std::uint32_t>(word.data);
}

unsigned int word_keep(const axis_word_t& word) {
    return static_cast<unsigned int>(word.keep);
}

unsigned int word_strb(const axis_word_t& word) {
    return static_cast<unsigned int>(word.strb);
}

bool word_last(const axis_word_t& word) {
    return static_cast<bool>(word.last);
}

void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

void run_length_case(int length) {
    axis_stream_t input;
    axis_stream_t output;
    std::vector<std::uint32_t> expected(static_cast<std::size_t>(length));

    for (int index = 0; index < length; ++index) {
        axis_word_t word;
        const std::uint32_t value =
            index + 1 == length
                ? UINT32_MAX
                : 0x10203040u + static_cast<std::uint32_t>(index * 17);
        word.data = value;
        word.keep = 0xF;
        word.strb = 0xF;
        word.last = index + 1 == length;
        input.write(word);
        expected[static_cast<std::size_t>(index)] = value + 1u;
    }

    axis_dummy_top(input, output, length);

    require(input.empty(), "dummy did not consume the complete input frame");
    for (int index = 0; index < length; ++index) {
        require(!output.empty(), "dummy produced too few output words");
        const axis_word_t word = output.read();
        require(word_data(word) == expected[static_cast<std::size_t>(index)],
                "output data mismatch at index " + std::to_string(index));
        require(word_keep(word) == 0xF, "TKEEP mismatch");
        require(word_strb(word) == 0xF, "TSTRB mismatch");
        require(word_last(word) == (index + 1 == length),
                "TLAST mismatch at index " + std::to_string(index));
    }
    require(output.empty(), "dummy produced too many output words");
}

void run_empty_case() {
    axis_stream_t input;
    axis_stream_t output;
    axis_dummy_top(input, output, 0);
    require(input.empty() && output.empty(),
            "zero-length transfer must not access either stream");
}

}  // namespace

int main() {
    try {
        run_empty_case();
        run_length_case(1);
        run_length_case(5);
        run_length_case(257);
        std::cout << "PASS: AXI dummy data, length, TKEEP/TSTRB, and TLAST\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
