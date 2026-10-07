#pragma once

#include "srcnn/tensor.hpp"

#include <filesystem>
#include <string>
#include <vector>

namespace srcnn {

struct TensorFile {
    std::string name;
    std::string layout;
    std::vector<std::size_t> shape;
    std::vector<float> data;
};

void save_tensor_file(const std::filesystem::path& path, const TensorFile& tensor);
TensorFile load_tensor_file(const std::filesystem::path& path,
                            const std::string& expected_layout,
                            const std::vector<std::size_t>& expected_shape);

void save_chw(const std::filesystem::path& path, const std::string& name,
              const Tensor& tensor);
Tensor load_chw(const std::filesystem::path& path,
                const std::vector<std::size_t>& expected_shape = {});

std::string fnv1a64_hex(const std::vector<float>& values);

}  // namespace srcnn

