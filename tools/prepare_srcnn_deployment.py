"""Prepare an offline-verified bundle for the fixed 255x255 SRCNN overlay.

Inputs: float32 .npy input [255,255] or [1,255,255], model [8129].
The input is already bicubic-upsampled and normalized to [0,1].
No resizing, clamping, image colour conversion or border crop is implicit.
"""
import argparse
import json
from pathlib import Path
import sys
import numpy as np

from deployment_numeric import (MODEL_PARTS, MODEL_WORDS, SCALE, accumulator_widths,
                                infer, metrics, quantize, sha256_file, signed_to_words)


def prepare(input_path, model_path, destination, golden_path=None, gt_path=None, crop=0):
    image = np.load(input_path, allow_pickle=False)
    if not np.issubdtype(image.dtype, np.floating):
        raise ValueError("input .npy must contain normalized floats, not packed raw words")
    image = image.astype(np.float32)
    if image.shape == (1, 255, 255):
        image = image[0]
    if image.shape != (255, 255) or not np.isfinite(image).all() or np.min(image) < 0 or np.max(image) > 1:
        raise ValueError("input must be finite normalized [0,1], already bicubic, 255x255")
    model = np.load(model_path, allow_pickle=False)
    if model.shape != (MODEL_WORDS,) or not np.issubdtype(model.dtype, np.floating) or not np.isfinite(model).all():
        raise ValueError("model must be a finite [8129] float array in the documented order")
    model = model.astype(np.float32)
    raw_input, raw_model = quantize(image), quantize(model)
    fixed_layers, diagnostics = infer(raw_input, raw_model)
    float_layers, _ = infer(image, model, fixed=False)
    fixed_output = fixed_layers[-1][0].astype(np.float64) / SCALE
    report = {"fixed_vs_float": metrics(fixed_output, float_layers[-1][0], 1.0, crop),
              "layer_metrics": [metrics(a.astype(np.float64) / SCALE, b, 1.0, crop)
                                for a, b in zip(fixed_layers, float_layers)],
              "saturation_diagnostics": diagnostics,
              "weight_quantization_zero_fraction": float(np.mean(raw_model == 0))}
    optional_sources = {}
    for label, path in (("course_golden", golden_path), ("ground_truth", gt_path)):
        if path:
            reference = np.load(path, allow_pickle=False).reshape(255, 255)
            report["fixed_vs_" + label] = metrics(fixed_output, reference, 1.0, crop)
            report["float_vs_" + label] = metrics(float_layers[-1][0], reference, 1.0, crop)
            optional_sources[label] = {"path": str(Path(path).resolve()), "sha256": sha256_file(Path(path))}
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    arrays = {"input.npy": signed_to_words(raw_input).reshape(-1),
              "model.npy": signed_to_words(raw_model),
              "expected.npy": signed_to_words(fixed_layers[-1]).reshape(-1)}
    for name, array in arrays.items():
        np.save(destination / name, array, allow_pickle=False)
    manifest = {"schema": "SRCNN_DEPLOYMENT_BUNDLE_V1", "top": "srcnn_axis_dataflow_top",
                "shape": [1, 255, 255], "format": "signed Q24.8 raw bits in uint32",
                "rounding": "AP_RND_CONV", "saturation": "AP_SAT",
                "accumulator_bits": accumulator_widths(),
                "model_layout": [{"name": n, "offset": o, "shape": list(s)} for n, o, s in MODEL_PARTS],
                "sources": {"input": {"path": str(Path(input_path).resolve()), "sha256": sha256_file(Path(input_path))},
                            "model": {"path": str(Path(model_path).resolve()), "sha256": sha256_file(Path(model_path))},
                            **optional_sources},
                "artifacts": {n: {"sha256": sha256_file(destination / n), "words": int(a.size)} for n, a in arrays.items()},
                "reference": "independent NumPy integer MAC reference; regression checked against 13x17 RTL vectors",
                "status": "OFFLINE_PREPARED_NOT_BOARD_VALIDATED"}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (destination / "offline_metrics.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--golden", type=Path)
    parser.add_argument("--ground-truth", type=Path)
    parser.add_argument("--crop", type=int, default=0, help="explicit symmetric border crop; default full frame")
    args = parser.parse_args()
    report = prepare(args.input, args.model, args.out, args.golden, args.ground_truth, args.crop)
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
