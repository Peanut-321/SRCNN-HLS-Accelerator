"""Independent offline arithmetic for the current Q24.8 deployment contract.

NumPy arrays contain signed raw codes, not IEEE float bit patterns. This is a
host reference; it never changes HLS types or claims board validation.
"""
import hashlib
import math
import numpy as np

MODEL_PARTS = (
    ("conv1_weights", 0, (64, 1, 9, 9)),
    ("conv1_bias", 5184, (64,)),
    ("conv2_weights", 5248, (32, 64, 1, 1)),
    ("conv2_bias", 7296, (32,)),
    ("conv3_weights", 7328, (1, 32, 5, 5)),
    ("conv3_bias", 8128, (1,)),
)
MODEL_WORDS = 8129
FRAME_WORDS = 255 * 255
SCALE = 256


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def quantize(values):
    values = np.asarray(values, dtype=np.float64)
    if not np.isfinite(values).all():
        raise ValueError("non-finite input/model value")
    # AP_RND_CONV: nearest, ties to even; AP_SAT: signed 32-bit endpoints.
    return np.clip(np.rint(values * SCALE), -(2**31), 2**31 - 1).astype("<i4")


def signed_to_words(values):
    return np.asarray(values, dtype="<i4").view("<u4")


def words_to_float(words):
    return np.asarray(words, dtype="<u4").view("<i4").astype(np.float64) / SCALE


def accumulator_widths():
    # Mirror the unchanged header's rational worst-case sizing: input/weights/
    # biases abs<=1; products have 16 fraction bits, bias is aligned to them.
    incoming = SCALE
    widths = []
    for terms in (81, 64, 800):
        bound = terms * incoming * SCALE + SCALE * SCALE
        integer_bits = max(1, 1 + bound.bit_length() - 16)
        widths.append(integer_bits + 16)
        incoming = min((bound + SCALE - 1) // SCALE, 2**31 - 1)
    return widths


def _round_shift_even(raw):
    quotient, remainder = np.divmod(raw, SCALE)
    return quotient + ((remainder > 128) | ((remainder == 128) & (quotient % 2 != 0)))


def infer(input_values, model, fixed=True):
    """Bias-first OIHW cross-correlation, replicate edges, layer 1/2 ReLU.

    Vectorize across output channels and pixels, retaining the C/I/J MAC order.
    Saturate after each accumulator assignment and round only at layer outputs.
    Float mode explicitly rounds each multiply and add to binary32 (no FMA).
    """
    model = np.asarray(model)
    if model.size != MODEL_WORDS:
        raise ValueError("expected 8129 model elements")
    if fixed and (not np.issubdtype(model.dtype, np.integer)):
        raise ValueError("fixed model must contain signed raw integer codes")
    current = np.asarray(input_values)
    if current.ndim == 2:
        current = current[None, :, :]
    if current.ndim != 3 or current.shape[0] != 1 or min(current.shape[1:]) < 1:
        raise ValueError("input shape must be [1,H,W], H/W positive")
    if fixed and not np.issubdtype(current.dtype, np.integer):
        raise ValueError("fixed input must contain signed raw integer codes")
    current = current.astype(np.int64 if fixed else np.float32)
    layers, diagnostics = [], []
    for layer, width in enumerate(accumulator_widths()):
        _, offset, shape = MODEL_PARTS[2 * layer]
        _, bias_offset, bias_shape = MODEL_PARTS[2 * layer + 1]
        weights = model.reshape(-1)[offset:offset + math.prod(shape)].reshape(shape)
        bias = model.reshape(-1)[bias_offset:bias_offset + bias_shape[0]]
        channels, _, kernel, _ = shape
        height, image_width = current.shape[1:]
        padded = np.pad(current, ((0, 0), (kernel // 2, kernel // 2), (kernel // 2, kernel // 2)), mode="edge")
        dtype = np.int64 if fixed else np.float32
        initial = bias.astype(dtype) * (SCALE if fixed else 1)
        sums = np.broadcast_to(initial[:, None, None], (channels, height, image_width)).copy()
        saturation_count = 0
        for channel in range(shape[1]):
            for row in range(kernel):
                for column in range(kernel):
                    sample = padded[channel, row:row + height, column:column + image_width]
                    product = weights[:, channel, row, column].astype(dtype)[:, None, None] * sample
                    sums = sums + product
                    if fixed:
                        low, high = -(2**(width - 1)), 2**(width - 1) - 1
                        saturation_count += int(np.count_nonzero((sums < low) | (sums > high)))
                        np.clip(sums, low, high, out=sums)
        if layer < 2:
            np.maximum(sums, 0, out=sums)
        if fixed:
            narrowed = _round_shift_even(sums)
            data_saturations = int(np.count_nonzero((narrowed < -(2**31)) | (narrowed > 2**31 - 1)))
            current = np.clip(narrowed, -(2**31), 2**31 - 1).astype(np.int64)
        else:
            current, data_saturations = sums.astype(np.float32), 0
        layers.append(current.copy())
        diagnostics.append({"layer": layer + 1, "accumulator_bits": width if fixed else 32,
                            "accumulator_saturations": saturation_count, "data_saturations": data_saturations})
    return layers, diagnostics


def metrics(actual, reference, peak, crop=0):
    actual, reference = np.asarray(actual, dtype=np.float64), np.asarray(reference, dtype=np.float64)
    if actual.shape != reference.shape or actual.ndim < 2:
        raise ValueError("metric shapes must match and contain H/W axes")
    if not np.isfinite(actual).all() or not np.isfinite(reference).all():
        raise ValueError("metrics require finite values")
    if not np.isfinite(peak) or peak <= 0 or crop < 0 or 2 * crop >= min(actual.shape[-2:]):
        raise ValueError("invalid peak/crop")
    if crop:
        actual, reference = actual[..., crop:-crop, crop:-crop], reference[..., crop:-crop, crop:-crop]
    difference = actual - reference
    mse = float(np.mean(difference * difference))
    return {"mse": mse, "psnr_db": None if mse == 0 else float(10 * math.log10(peak * peak / mse)),
            "perfect_match": mse == 0, "max_abs": float(np.max(np.abs(difference))),
            "peak": float(peak), "crop": int(crop), "pixels": int(actual.size)}
