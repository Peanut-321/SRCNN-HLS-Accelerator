#include "srcnn/srcnn.hpp"
#include "srcnn/tensor_io.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

struct Failure : std::runtime_error { using std::runtime_error::runtime_error; };

void require(bool condition, const std::string& message) {
    if (!condition) throw Failure(message);
}

void near(float actual, float expected, float tolerance, const std::string& where) {
    if (std::fabs(actual - expected) > tolerance) {
        std::ostringstream message;
        message << where << ": expected " << expected << ", got " << actual;
        throw Failure(message.str());
    }
}

void tensor_near(const srcnn::Tensor& actual, const srcnn::Tensor& expected,
                 float tolerance, const std::string& where) {
    require(actual.shape() == expected.shape(), where + ": shape mismatch");
    for (std::size_t i = 0; i < actual.size(); ++i) {
        near(actual.data[i], expected.data[i], tolerance,
             where + " element " + std::to_string(i));
    }
}

template <typename Function>
void throws_with(Function&& function, const std::string& fragment) {
    try {
        function();
    } catch (const std::exception& error) {
        require(std::string(error.what()).find(fragment) != std::string::npos,
                "exception did not contain '" + fragment + "': " + error.what());
        return;
    }
    throw Failure("expected exception containing '" + fragment + "'");
}

srcnn::Conv2DLayer layer(srcnn::Conv2DConfig config, float weight, float bias) {
    const auto count = srcnn::checked_element_count(
        {config.out_channels, config.in_channels, config.kernel_h, config.kernel_w});
    return {config, std::vector<float>(count, weight),
            std::vector<float>(config.out_channels, bias)};
}

srcnn::SRCNN uniform_model(bool same, float weight, float bias) {
    const auto configs = srcnn::SRCNN::standard_configs(same);
    return {layer(configs[0], weight, bias), layer(configs[1], weight, bias),
            layer(configs[2], weight, bias)};
}

srcnn::Tensor independent_oracle(const srcnn::Tensor& input,
                                 const srcnn::Conv2DLayer& convolution) {
    const auto& c = convolution.config;
    require(input.channels == c.in_channels, "oracle channel mismatch");
    require(input.height + 2 * c.pad_h >= c.kernel_h, "oracle invalid height");
    require(input.width + 2 * c.pad_w >= c.kernel_w, "oracle invalid width");
    const auto oh_count = (input.height + 2 * c.pad_h - c.kernel_h) / c.stride_h + 1;
    const auto ow_count = (input.width + 2 * c.pad_w - c.kernel_w) / c.stride_w + 1;
    srcnn::Tensor result(c.out_channels, oh_count, ow_count);
    for (std::size_t o = 0; o < c.out_channels; ++o) {
        for (std::size_t oh = 0; oh < oh_count; ++oh) {
            for (std::size_t ow = 0; ow < ow_count; ++ow) {
                // Accumulate in the same float type, but enumerate the flattened
                // OIHW kernel independently from the production indexing helper.
                float total = convolution.bias.at(o);
                for (std::size_t flat = 0; flat < c.in_channels * c.kernel_h * c.kernel_w; ++flat) {
                    const auto kw = flat % c.kernel_w;
                    const auto kh = (flat / c.kernel_w) % c.kernel_h;
                    const auto i = flat / (c.kernel_h * c.kernel_w);
                    const auto ih = static_cast<long>(oh * c.stride_h + kh) - static_cast<long>(c.pad_h);
                    const auto iw = static_cast<long>(ow * c.stride_w + kw) - static_cast<long>(c.pad_w);
                    if (ih >= 0 && iw >= 0 && ih < static_cast<long>(input.height) &&
                        iw < static_cast<long>(input.width)) {
                        const auto w_index = o * c.in_channels * c.kernel_h * c.kernel_w + flat;
                        const auto x_index = (i * input.height + static_cast<std::size_t>(ih)) *
                                                 input.width + static_cast<std::size_t>(iw);
                        total += convolution.weights.at(w_index) * input.data.at(x_index);
                    }
                }
                result(o, oh, ow) = c.activation == srcnn::Activation::ReLU
                                         ? std::max(0.0F, total) : total;
            }
        }
    }
    return result;
}

void test_zero_input_zero_weights_zero_output() {
    const srcnn::Tensor input(1, 5, 7, 0.0F);
    const auto outputs = uniform_model(true, 0.0F, 0.0F).run(input);
    for (const auto* tensor : {&outputs.conv1, &outputs.conv2, &outputs.conv3}) {
        require(std::all_of(tensor->data.begin(), tensor->data.end(),
                            [](float value) { return value == 0.0F; }),
                "zero case produced nonzero output");
    }
}

void test_zero_input_nonzero_bias_added_once_then_relu() {
    srcnn::Conv2DConfig config{3, 3, 3, 3, 1, 1, 1, 1, srcnn::Activation::ReLU};
    auto convolution = layer(config, 0.0F, 0.0F);
    convolution.bias = {-2.0F, 0.25F, 3.5F};
    const auto output = srcnn::conv2d(srcnn::Tensor(3, 4, 5, 0.0F), convolution);
    for (std::size_t h = 0; h < output.height; ++h) {
        for (std::size_t w = 0; w < output.width; ++w) {
            near(output(0, h, w), 0.0F, 0.0F, "negative bias after ReLU");
            near(output(1, h, w), 0.25F, 0.0F, "bias must be added once");
            near(output(2, h, w), 3.5F, 0.0F, "bias must not scale with channels/kernel");
        }
    }
}

void test_ones_input_ones_weights_hand_calculated() {
    const srcnn::Conv2DConfig config{2, 1, 3, 3, 1, 1, 1, 1, srcnn::Activation::None};
    const auto output = srcnn::conv2d(srcnn::Tensor(2, 3, 4, 1.0F), layer(config, 1.0F, 0.5F));
    near(output(0, 1, 1), 18.5F, 0.0F, "all-ones interior");
    near(output(0, 0, 1), 12.5F, 0.0F, "all-ones top edge");
    near(output(0, 0, 0), 8.5F, 0.0F, "all-ones corner");
}

void test_impulse_kernel_direction_padding_and_spatial_index() {
    srcnn::Tensor input(1, 5, 5, 0.0F);
    input(0, 2, 2) = 1.0F;
    srcnn::Conv2DConfig config{1, 1, 3, 3, 1, 1, 1, 1, srcnn::Activation::None};
    srcnn::Conv2DLayer convolution(config,
        {1, 2, 3, 4, 5, 6, 7, 8, 9}, {0});
    const auto output = srcnn::conv2d(input, convolution);
    // Cross-correlation: output above-left of the impulse sees W[2,2].
    near(output(0, 1, 1), 9.0F, 0.0F, "impulse upper-left response");
    near(output(0, 2, 2), 5.0F, 0.0F, "impulse centre response");
    near(output(0, 3, 3), 1.0F, 0.0F, "impulse lower-right response");
    near(output(0, 0, 0), 0.0F, 0.0F, "outside impulse footprint");
}

void test_single_nonzero_weight_oihw_channel_mapping() {
    srcnn::Tensor input(3, 2, 3, 0.0F);
    input(1, 0, 0) = 2.0F;
    input(1, 0, 1) = 3.0F;
    const srcnn::Conv2DConfig config{3, 2, 1, 1, 1, 1, 0, 0, srcnn::Activation::None};
    std::vector<float> weights(6, 0.0F);
    // OIHW index [o=1][i=1][0][0].
    weights[4] = 7.0F;
    const auto output = srcnn::conv2d(input, {config, weights, {0, 0}});
    near(output(1, 0, 0), 14.0F, 0.0F, "routed output value 0");
    near(output(1, 0, 1), 21.0F, 0.0F, "routed output value 1");
    near(output(0, 0, 0), 0.0F, 0.0F, "wrong output channel remained zero");
}

void test_signed_values_relu_conv1_conv2_and_no_relu_conv3() {
    const auto configs = srcnn::SRCNN::standard_configs(true);
    auto conv1 = layer(configs[0], 0.0F, -0.5F);
    auto conv2 = layer(configs[1], 0.0F, -1.25F);
    auto conv3 = layer(configs[2], 0.0F, -1.75F);
    const srcnn::SRCNN model(std::move(conv1), std::move(conv2), std::move(conv3));
    const auto outputs = model.run(srcnn::Tensor(1, 2, 3, -2.0F));
    require(std::all_of(outputs.conv1.data.begin(), outputs.conv1.data.end(),
                        [](float value) { return value == 0.0F; }),
            "Conv1 negative values must be removed by ReLU");
    require(std::all_of(outputs.conv2.data.begin(), outputs.conv2.data.end(),
                        [](float value) { return value == 0.0F; }),
            "Conv2 negative values must be removed by ReLU");
    require(std::all_of(outputs.conv3.data.begin(), outputs.conv3.data.end(),
                        [](float value) { return value == -1.75F; }),
            "Conv3 negative values must be retained");

    const srcnn::Conv2DConfig linear{1, 1, 1, 1, 1, 1, 0, 0,
                                     srcnn::Activation::None};
    near(srcnn::conv2d(srcnn::Tensor(1, 1, 1, 2.0F),
                       layer(linear, -1.0F, 0.25F))(0, 0, 0),
         -1.75F, 0.0F, "signed multiply and add");
}

void test_center_edge_and_corner_coordinates() {
    const srcnn::Conv2DConfig config{1, 1, 3, 3, 1, 1, 1, 1, srcnn::Activation::None};
    const srcnn::Conv2DLayer convolution(config,
        {0.5F, -1, 2, 3, 4, -5, 6, 7, 8}, {0.125F});
    for (const auto& point : std::vector<std::pair<std::size_t, std::size_t>>{{2, 2}, {0, 2}, {2, 0}, {0, 0}}) {
        srcnn::Tensor input(1, 5, 5, 0.0F);
        input(0, point.first, point.second) = -1.5F;
        tensor_near(srcnn::conv2d(input, convolution), independent_oracle(input, convolution),
                    0.0F, "centre/edge/corner oracle");
    }
}

void test_minimum_legal_sizes_same_and_valid() {
    const srcnn::Conv2DConfig valid_config{1, 1, 3, 5, 1, 1, 0, 0, srcnn::Activation::None};
    const auto valid = srcnn::conv2d(srcnn::Tensor(1, 3, 5, 1.0F),
                                     layer(valid_config, 1.0F, 0.0F));
    require(valid.shape() == std::vector<std::size_t>({1, 1, 1}), "minimal valid shape");
    near(valid(0, 0, 0), 15.0F, 0.0F, "minimal valid value");
    throws_with([&] { srcnn::conv2d(srcnn::Tensor(1, 2, 5), layer(valid_config, 1, 0)); },
                "too small");

    const auto same = uniform_model(true, 0.0F, 0.0F).run(srcnn::Tensor(1, 1, 1));
    require(same.conv3.shape() == std::vector<std::size_t>({1, 1, 1}),
            "same padding must support 1x1 input");
}

void test_full_srcnn_minimum_valid_all_ones_hand_calculated() {
    const auto outputs = uniform_model(false, 1.0F, 0.0F).run(srcnn::Tensor(1, 13, 13, 1.0F));
    require(outputs.conv1.shape() == std::vector<std::size_t>({64, 5, 5}), "Conv1 valid shape");
    require(outputs.conv2.shape() == std::vector<std::size_t>({32, 5, 5}), "Conv2 valid shape");
    require(outputs.conv3.shape() == std::vector<std::size_t>({1, 1, 1}), "Conv3 valid shape");
    near(outputs.conv1(0, 0, 0), 81.0F, 0.0F, "Conv1 hand calculation");
    near(outputs.conv2(0, 0, 0), 5184.0F, 0.0F, "Conv2 hand calculation");
    near(outputs.conv3(0, 0, 0), 4147200.0F, 0.0F, "end-to-end hand calculation");
}

void test_fixed_seed_random_against_independent_oracle() {
    std::mt19937 generator(0x5EED1234U);
    auto random_value = [&]() {
        return static_cast<float>(static_cast<int>(generator() % 2001U) - 1000) / 1000.0F;
    };
    srcnn::Tensor input(2, 4, 6);
    for (auto& value : input.data) value = random_value();
    const srcnn::Conv2DConfig config{2, 3, 3, 2, 2, 1, 1, 1, srcnn::Activation::ReLU};
    std::vector<float> weights(36), bias(3);
    for (auto& value : weights) value = random_value();
    for (auto& value : bias) value = random_value();
    const srcnn::Conv2DLayer convolution(config, weights, bias);
    const auto actual = srcnn::conv2d(input, convolution);
    const auto expected = independent_oracle(input, convolution);
    tensor_near(actual, expected, 0.0F, "fixed-seed random oracle");
    const auto input_checksum = srcnn::fnv1a64_hex(input.data);
    const auto output_checksum = srcnn::fnv1a64_hex(actual.data);
    require(input_checksum == "c696b00d28c2e7c0",
            "fixed-seed input checksum changed: " + input_checksum);
    require(output_checksum == "d16e5a01d984e083",
            "fixed-seed output checksum changed: " + output_checksum);
}

void test_each_layer_runs_independently() {
    const auto configs = srcnn::SRCNN::standard_configs(true);
    auto model = uniform_model(true, 0.0F, 1.0F);
    srcnn::Tensor input(1, 3, 4, 0.0F);
    const auto first = model.run_layer(0, input);
    const auto second = model.run_layer(1, first);
    const auto third = model.run_layer(2, second);
    const auto full = model.run(input);
    tensor_near(first, full.conv1, 0.0F, "independent Conv1");
    tensor_near(second, full.conv2, 0.0F, "independent Conv2");
    tensor_near(third, full.conv3, 0.0F, "independent Conv3");
    (void)configs;
}

void test_tensor_dump_round_trip_and_all_outputs() {
    const auto root = std::filesystem::temp_directory_path() / "srcnn_golden_dump_test";
    std::filesystem::remove_all(root);
    srcnn::Tensor input(1, 2, 3);
    input.data = {-0.0F, 0.25F, -1.5F, 2.0F, 3.125F, -9.0F};
    const auto model = uniform_model(true, 0.0F, 0.0F);
    const auto outputs = model.run_and_dump(input, root);
    tensor_near(srcnn::load_chw(root / "input.tensor", {1, 2, 3}), input, 0.0F, "input round trip");
    tensor_near(srcnn::load_chw(root / "conv1.tensor", outputs.conv1.shape()), outputs.conv1, 0.0F, "Conv1 round trip");
    tensor_near(srcnn::load_chw(root / "conv2.tensor", outputs.conv2.shape()), outputs.conv2, 0.0F, "Conv2 round trip");
    tensor_near(srcnn::load_chw(root / "conv3.tensor", outputs.conv3.shape()), outputs.conv3, 0.0F, "Conv3 round trip");
    tensor_near(srcnn::load_chw(root / "output.tensor", outputs.conv3.shape()), outputs.conv3, 0.0F, "final output round trip");
    std::filesystem::remove_all(root);
}

void test_parameter_constructor_count_validation() {
    const srcnn::Conv2DConfig config{2, 3, 3, 3, 1, 1, 0, 0, srcnn::Activation::None};
    throws_with([&] { srcnn::Conv2DLayer(config, std::vector<float>(53), std::vector<float>(3)); },
                "weight count mismatch");
    throws_with([&] { srcnn::Conv2DLayer(config, std::vector<float>(54), std::vector<float>(2)); },
                "bias count mismatch");
}

void test_file_loader_shape_layout_count_short_extra_and_checksum_validation() {
    const auto root = std::filesystem::temp_directory_path() / "srcnn_loader_test";
    std::filesystem::remove_all(root);
    std::filesystem::create_directories(root);
    const auto valid = root / "valid.tensor";
    srcnn::save_tensor_file(valid, {"w", "OIHW", {1, 1, 1, 2}, {1.0F, 2.0F}});
    throws_with([&] { srcnn::load_tensor_file(valid, "CHW", {1, 1, 1, 2}); }, "layout mismatch");
    throws_with([&] { srcnn::load_tensor_file(valid, "OIHW", {1, 1, 2, 1}); }, "shape mismatch");

    auto write = [&](const std::string& name, const std::string& body) {
        std::ofstream stream(root / name);
        stream << body;
    };
    write("bad_count.tensor", "SRCNN_TENSOR_V1\nname x\ndtype float32\nlayout O\nndim 1\nshape 2\ncount 3\nchecksum_fnv1a64 x\ndata\n1 2 3\n");
    throws_with([&] { srcnn::load_tensor_file(root / "bad_count.tensor", "O", {2}); }, "declared count");
    write("short.tensor", "SRCNN_TENSOR_V1\nname x\ndtype float32\nlayout O\nndim 1\nshape 2\ncount 2\nchecksum_fnv1a64 x\ndata\n1\n");
    throws_with([&] { srcnn::load_tensor_file(root / "short.tensor", "O", {2}); }, "short data");
    write("extra.tensor", "SRCNN_TENSOR_V1\nname x\ndtype float32\nlayout O\nndim 1\nshape 2\ncount 2\nchecksum_fnv1a64 x\ndata\n1 2 3\n");
    throws_with([&] { srcnn::load_tensor_file(root / "extra.tensor", "O", {2}); }, "extra data");
    write("checksum.tensor", "SRCNN_TENSOR_V1\nname x\ndtype float32\nlayout O\nndim 1\nshape 2\ncount 2\nchecksum_fnv1a64 deadbeefdeadbeef\ndata\n1 2\n");
    throws_with([&] { srcnn::load_tensor_file(root / "checksum.tensor", "O", {2}); }, "checksum mismatch");
    std::filesystem::remove_all(root);
}

}  // namespace

int main() {
    const std::vector<std::pair<std::string, std::function<void()>>> tests = {
        {"zero input / zero weights -> zero output", test_zero_input_zero_weights_zero_output},
        {"zero input + bias; add once then ReLU", test_zero_input_nonzero_bias_added_once_then_relu},
        {"ones input / ones weights hand calculation", test_ones_input_ones_weights_hand_calculated},
        {"impulse kernel direction, padding, spatial index", test_impulse_kernel_direction_padding_and_spatial_index},
        {"single nonzero OIHW weight and channel mapping", test_single_nonzero_weight_oihw_channel_mapping},
        {"signed values and activation placement", test_signed_values_relu_conv1_conv2_and_no_relu_conv3},
        {"centre, edge, and corner", test_center_edge_and_corner_coordinates},
        {"minimum legal same and valid sizes", test_minimum_legal_sizes_same_and_valid},
        {"full SRCNN minimum valid all-ones", test_full_srcnn_minimum_valid_all_ones_hand_calculated},
        {"fixed-seed random oracle", test_fixed_seed_random_against_independent_oracle},
        {"each layer independently runnable", test_each_layer_runs_independently},
        {"input/intermediate/final dump round trip", test_tensor_dump_round_trip_and_all_outputs},
        {"constructor parameter count validation", test_parameter_constructor_count_validation},
        {"file shape/count/layout/data validation", test_file_loader_shape_layout_count_short_extra_and_checksum_validation},
    };
    std::size_t failures = 0;
    for (const auto& test : tests) {
        try {
            test.second();
            std::cout << "[PASS] " << test.first << '\n';
        } catch (const std::exception& error) {
            ++failures;
            std::cerr << "[FAIL] " << test.first << ": " << error.what() << '\n';
        }
    }
    std::cout << (tests.size() - failures) << '/' << tests.size() << " tests passed\n";
    return failures == 0 ? 0 : 1;
}
