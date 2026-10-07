#pragma once

#include <cstddef>
#include <initializer_list>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace srcnn {

inline std::size_t checked_element_count(const std::vector<std::size_t>& shape) {
    if (shape.empty()) {
        throw std::invalid_argument("tensor shape must not be empty");
    }
    std::size_t count = 1;
    for (const auto extent : shape) {
        if (extent == 0) {
            throw std::invalid_argument("tensor dimensions must be positive");
        }
        if (count > static_cast<std::size_t>(-1) / extent) {
            throw std::overflow_error("tensor element count overflow");
        }
        count *= extent;
    }
    return count;
}

struct Tensor {
    std::size_t channels{};
    std::size_t height{};
    std::size_t width{};
    std::vector<float> data;

    Tensor() = default;
    Tensor(std::size_t c, std::size_t h, std::size_t w, float value = 0.0F)
        : channels(c), height(h), width(w),
          data(checked_element_count({c, h, w}), value) {}

    std::vector<std::size_t> shape() const { return {channels, height, width}; }
    std::size_t size() const { return data.size(); }

    std::size_t offset(std::size_t c, std::size_t h, std::size_t w) const {
        if (c >= channels || h >= height || w >= width) {
            throw std::out_of_range("CHW tensor index out of range");
        }
        return (c * height + h) * width + w;
    }

    float& operator()(std::size_t c, std::size_t h, std::size_t w) {
        return data[offset(c, h, w)];
    }
    const float& operator()(std::size_t c, std::size_t h, std::size_t w) const {
        return data[offset(c, h, w)];
    }
};

}  // namespace srcnn

