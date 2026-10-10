"""Offline-only signed fixed-point experiments; frozen deployment is unchanged.

Products retain 2*F fractional bits. Default accumulator sizing uses the
legacy <=1 bounds; optional explicit widths support the official host profile.
Assignments saturate and layer outputs round to nearest/even. int64 execution
is allowed only when every accumulator fits signed int64.
"""
from dataclasses import dataclass
import math
import numpy as np
from deployment_numeric import MODEL_PARTS, MODEL_WORDS

# Upward-rounded official-model bounds, shared with the opt-in Q20.12 HLS
# configuration. Default HLS still uses legacy bounds. Order: C1 W/B, C2 W/B, C3 W/B.
OFFICIAL_DECLARED_BOUNDS = ((600,1000),(383,1000),(852,1000),
                            (85,1000),(163,1000),(29,1000))


def official_declared_sizing(fmt):
    """Mirror the opt-in numeric_config.hpp conservative rational bounds.

    This alternative contract proves a whole class of models safe, not only
    observed pixels. The bound on each quantized parameter is rounded upward.
    Calling this helper does not select the HLS profile or relax static_asserts.
    """
    raw_bounds = [(n*fmt.scale+d-1)//d for n,d in OFFICIAL_DECLARED_BOUNDS]
    incoming, layers = fmt.scale, []
    for index, terms in enumerate((81,64,800)):
        weight, bias = raw_bounds[index*2:index*2+2]
        bound = terms*incoming*weight+bias*fmt.scale
        integer_bits = max(1,1+bound.bit_length()-2*fmt.fraction_bits)
        output_bound = (bound+fmt.scale-1)//fmt.scale
        layers.append({"layer":index+1,"integer_bits":integer_bits,
                       "total_bits":integer_bits+2*fmt.fraction_bits,
                       "preactivation_abs_bound":bound/fmt.scale**2,
                       "worst_case_data_saturation":output_bound>fmt.high})
        incoming=min(output_bound,fmt.high)
    return {"status":"OFFLINE_DECLARED_SIZING_NOT_HARDWARE_VALIDATION",
            "input_abs_max":1,"model_abs_max_rationals":list(OFFICIAL_DECLARED_BOUNDS),
            "raw_model_abs_max_bounds":raw_bounds,"layers":layers,
            "declared_range_static_assert_passes":not any(x["worst_case_data_saturation"] for x in layers)}


@dataclass(frozen=True)
class FixedFormat:
    total_bits: int = 32
    fraction_bits: int = 8

    def __post_init__(self):
        if not (2 <= self.total_bits <= 32 and 0 <= self.fraction_bits < self.total_bits):
            raise ValueError("require 2 <= W <= 32 and 0 <= F < W")
        if max(self.accumulator_widths()) > 63:
            raise ValueError("accumulator exceeds signed int64 study capacity")

    @property
    def scale(self): return 1 << self.fraction_bits
    @property
    def low(self): return -(1 << (self.total_bits - 1))
    @property
    def high(self): return (1 << (self.total_bits - 1)) - 1
    @property
    def label(self): return f"W{self.total_bits}_I{self.total_bits-self.fraction_bits}_F{self.fraction_bits}"

    def sizing(self):
        incoming, result = self.scale, []
        for terms in (81, 64, 800):
            bound = terms * incoming * self.scale + self.scale * self.scale
            integer_bits = max(1, 1 + bound.bit_length() - 2 * self.fraction_bits)
            output_bound = (bound + self.scale - 1) // self.scale
            result.append({"total_bits": integer_bits + 2 * self.fraction_bits,
                           "integer_bits": integer_bits, "preactivation_bound_raw": bound,
                           "worst_case_data_saturation": output_bound > self.high})
            incoming = min(output_bound, self.high)
        return result

    def accumulator_widths(self): return [layer["total_bits"] for layer in self.sizing()]

    def quantize(self, values):
        values = np.asarray(values, dtype=np.float64)
        if not np.isfinite(values).all(): raise ValueError("non-finite value")
        return np.clip(np.rint(values * self.scale), self.low, self.high).astype(np.int64)

    def round_output(self, raw):
        quotient, remainder = np.divmod(raw, self.scale)
        twice = 2 * remainder
        return quotient + ((twice > self.scale) | ((twice == self.scale) & (quotient % 2 != 0)))


def infer_fixed(image, model, fmt, accumulator_bits=None):
    """OIHW bias-first MAC order, replicate edges, Conv1/2 ReLU.

    Collect pre-ReLU accumulator and pre/post-narrowing ranges and saturation
    counts. Generic study formats remain separate from deployment helpers;
    the official Q20.12 preparer supplies its derived accumulator widths.
    """
    widths = fmt.accumulator_widths() if accumulator_bits is None else list(accumulator_bits)
    if (len(widths) != 3 or any(not isinstance(w, int) or w < 2*fmt.fraction_bits+1 or w > 63 for w in widths)):
        raise ValueError("require three accumulator widths with full product precision, <=63 bits")
    current, model = np.asarray(image), np.asarray(model)
    if current.ndim == 2: current = current[None]
    if (current.ndim != 3 or current.shape[0] != 1 or min(current.shape[1:]) < 1
            or model.size != MODEL_WORDS or not np.issubdtype(current.dtype, np.integer)
            or not np.issubdtype(model.dtype, np.integer)):
        raise ValueError("require [1,H,W] integer image and 8129 integer parameters")
    if np.any((current < fmt.low) | (current > fmt.high)) or np.any((model < fmt.low) | (model > fmt.high)):
        raise ValueError("raw value outside selected format")
    current, model = current.astype(np.int64), model.astype(np.int64).reshape(-1)
    layers, diagnostics = [], []
    for index, width in enumerate(widths):
        _, offset, shape = MODEL_PARTS[index * 2]
        _, bias_offset, bias_shape = MODEL_PARTS[index * 2 + 1]
        weights = model[offset:offset + math.prod(shape)].reshape(shape)
        bias = model[bias_offset:bias_offset + bias_shape[0]]
        channels, _, kernel, _ = shape
        height, image_width = current.shape[1:]
        padded = np.pad(current, ((0, 0), (kernel//2, kernel//2), (kernel//2, kernel//2)), mode="edge")
        sums = np.broadcast_to((bias * fmt.scale)[:, None, None], (channels, height, image_width)).copy()
        acc_min, acc_max = int(sums.min()), int(sums.max())
        saturation_count = 0
        for channel in range(shape[1]):
            for row in range(kernel):
                for column in range(kernel):
                    sample = padded[channel, row:row+height, column:column+image_width]
                    sums += weights[:, channel, row, column][:, None, None] * sample
                    acc_min, acc_max = min(acc_min, int(sums.min())), max(acc_max, int(sums.max()))
                    low, high = -(1 << (width-1)), (1 << (width-1))-1
                    saturation_count += int(np.count_nonzero((sums < low) | (sums > high)))
                    np.clip(sums, low, high, out=sums)
        if index < 2: np.maximum(sums, 0, out=sums)
        narrowed = fmt.round_output(sums)
        data_saturations = int(np.count_nonzero((narrowed < fmt.low) | (narrowed > fmt.high)))
        current = np.clip(narrowed, fmt.low, fmt.high).astype(np.int64)
        layers.append(current.copy())
        diagnostics.append({"layer": index+1, "accumulator_bits": width,
                            "accumulator_saturations": saturation_count, "data_saturations": data_saturations,
                            "accumulator_min": acc_min / fmt.scale**2, "accumulator_max": acc_max / fmt.scale**2,
                            "pre_narrow_min": int(narrowed.min()) / fmt.scale,
                            "pre_narrow_max": int(narrowed.max()) / fmt.scale,
                            "output_min": int(current.min()) / fmt.scale,
                            "output_max": int(current.max()) / fmt.scale})
    return layers, diagnostics


def official_model_intervals(model, fmt):
    """Integer interval proof for this exact quantized model, all inputs in [0,1].

    Spatial/channel correlations are discarded conservatively. Replicate edges
    select values already within these intervals. An absolute-term bound also
    covers every partial MAC sum, not only its final value. No float arithmetic
    enters the proof. This does NOT prove arbitrary runtime models safe.
    """
    model = np.asarray(model, dtype=np.int64).reshape(-1)
    if model.size != MODEL_WORDS: raise ValueError("expected 8129 parameters")
    incoming_low, incoming_high = [0], [fmt.scale]
    result = []
    for index, width in enumerate(fmt.accumulator_widths()):
        _, offset, shape = MODEL_PARTS[index*2]
        _, bias_offset, _ = MODEL_PARTS[index*2+1]
        weights = model[offset:offset+math.prod(shape)].reshape(shape)
        outgoing_low, outgoing_high, absolute_prefix_bounds = [], [], []
        for oc in range(shape[0]):
            lo = hi = int(model[bias_offset+oc]) * fmt.scale
            prefix_bound = abs(lo)
            for ic in range(shape[1]):
                for weight in weights[oc, ic].reshape(-1):
                    weight = int(weight)
                    ends = (weight*incoming_low[ic], weight*incoming_high[ic])
                    lo += min(ends); hi += max(ends)
                    prefix_bound += abs(weight)*max(abs(incoming_low[ic]), abs(incoming_high[ic]))
            absolute_prefix_bounds.append(prefix_bound)
            if index < 2: lo, hi = max(0, lo), max(0, hi)
            narrowed = fmt.round_output(np.array([lo, hi], dtype=np.int64))
            outgoing_low.append(int(narrowed[0])); outgoing_high.append(int(narrowed[1]))
        lo, hi = min(outgoing_low), max(outgoing_high)
        prefix_bound = max(absolute_prefix_bounds)
        result.append({"layer": index+1, "unclipped_output_min_raw": lo, "unclipped_output_max_raw": hi,
                       "unclipped_output_min": lo/fmt.scale, "unclipped_output_max": hi/fmt.scale,
                       "partial_accumulator_abs_bound_raw": prefix_bound,
                       "partial_accumulator_abs_bound": prefix_bound/fmt.scale**2,
                       "accumulator_guaranteed_no_saturation": prefix_bound <= (1 << (width-1))-1,
                       "data_guaranteed_no_saturation": lo >= fmt.low and hi <= fmt.high})
        incoming_low = [max(fmt.low, min(fmt.high, v)) for v in outgoing_low]
        incoming_high = [max(fmt.low, min(fmt.high, v)) for v in outgoing_high]
    return result
