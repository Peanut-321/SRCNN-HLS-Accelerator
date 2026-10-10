"""Independent Q20.12 vectors for the existing fixed 13x17 RTL scoreboard."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pynq"))
from srcnn_q20_12_bundle import (
    MODEL_LAYOUT, NUMERIC_CONTRACT, PROFILE_ID, encode_values,
    validate_float_input, validate_float_model,
)
from precision_numeric import FixedFormat, infer_fixed


def prepare(destination, input_path=None, model_path=None):
    sources = {}
    if input_path is None and model_path is None:
        # Same inputs as the profile-specific C-sim fixture. Golden arithmetic
        # is independently implemented by the integer reference, not the DUT.
        image = (np.arange(221) % 9 / 16).astype(np.float32).reshape(13, 17)
        blocks = [(5184, 7, -3, 32), (64, 5, -2, 16),
                  (2048, 7, -3, 64), (32, 5, -2, 32),
                  (800, 7, -3, 64), (1, 3, -1, 64)]
        model = np.concatenate([
            ((np.arange(count) % period + offset) / denominator).astype(np.float32)
            for count, period, offset, denominator in blocks
        ])
        case = "deterministic_csim_fixture"
    elif input_path is not None and model_path is not None:
        full_image = validate_float_input(np.load(input_path, allow_pickle=False))
        if full_image.shape[0] < 13 or full_image.shape[1] < 17:
            raise ValueError("input must cover the top-left 13x17 crop")
        # This is a small-frame replicate test, not a crop of full-frame output.
        image = full_image[:13, :17].copy()
        model = np.load(model_path, allow_pickle=False)
        for name, path in (("input", input_path), ("model", model_path)):
            sources[name] = {"path": str(Path(path).resolve()),
                             "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
        case = "provided_model_top_left_13x17_input"
    else:
        raise ValueError("provide both --input and --model, or neither")
    image, model = validate_float_input(image), validate_float_model(model)
    input_words, model_words = encode_values(image), encode_values(model)
    layers, diagnostics = infer_fixed(
        input_words.view("<i4"), model_words.view("<i4"), FixedFormat(32, 12),
        accumulator_bits=NUMERIC_CONTRACT["accumulator_bits"],
    )
    if any(d["accumulator_saturations"] or d["data_saturations"] for d in diagnostics):
        raise ValueError("unexpected reference saturation")
    arrays = {"input.hex": input_words.reshape(-1), "model.hex": model_words,
              "expected.hex": layers[-1].astype("<i4").view("<u4").reshape(-1)}
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    artifacts = {}
    for name, words in arrays.items():
        path = destination / name
        path.write_text("".join(f"{int(word):08x}\n" for word in words), encoding="ascii")
        artifacts[name] = {"words": int(words.size),
                           "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest = {"numeric_profile": PROFILE_ID, "numeric_contract": NUMERIC_CONTRACT,
                "model_layout": MODEL_LAYOUT, "case": case, "shape": [1, 13, 17],
                "top": "srcnn_axis_dataflow_cosim_13x17_top", "sources": sources,
                "artifacts": artifacts, "diagnostics": diagnostics,
                "golden": "independent integer MAC with derived 31/37/44-bit accumulators"}
    (destination / "vectors-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--model", type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.out, args.input, args.model), indent=2))
