#pragma once

namespace srcnn_hls {
namespace arithmetic {

// P1 compatibility decision: the frozen Golden executes `sum = bias; sum +=
// products`. Starting from zero and adding bias after all MACs is mathematically
// equivalent but not bitwise equivalent in binary32. P2.1 mirrors the frozen
// order so its five-vector bitwise gate is meaningful. Changing this requires a
// deliberate spec/P1 re-baseline decision; it must never happen accidentally
// during a structural HLS rewrite.
template <typename Accumulator, typename Data>
Accumulator begin_with_frozen_bias_order(const Data& bias) {
    return static_cast<Accumulator>(bias);
}

template <typename Accumulator, typename Data>
void accumulate_product(Accumulator& accumulator, const Data& weight,
                        const Data& sample) {
    accumulator += weight * sample;
}

template <typename Data, typename Accumulator>
Data activate_and_narrow(const Accumulator& preactivation, bool relu) {
    const Accumulator zero = static_cast<Accumulator>(0);
    // Matches std::max(0, x), including its +0 result for x == -0.
    const Accumulator activated =
        relu ? (zero < preactivation ? preactivation : zero) : preactivation;
    return static_cast<Data>(activated);
}

}  // namespace arithmetic
}  // namespace srcnn_hls
