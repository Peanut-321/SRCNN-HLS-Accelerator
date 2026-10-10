"""Evaluate the frozen float/Q24.8 paths on verified course binary assets.

No HLS/DUT changes. The starter includes one Set5 image and thirteen Set14
images; report this inventory, never call it a complete Set5/Set14 evaluation.
"""
import argparse
import csv
import json
from pathlib import Path
import time
import numpy as np
from deployment_numeric import (MODEL_PARTS, infer, metrics, quantize, sha256_file,
                                signed_to_words, words_to_float)


def evaluate(root, output, source_commit):
    root, output = Path(root), Path(output)
    recorded = json.loads(Path(__file__).with_name("course_asset_hashes.json").read_text())
    for item in recorded["assets"]:
        file = root / item["path"]
        if file.stat().st_size != item["bytes"] or sha256_file(file) != item["sha256"]:
            raise ValueError("recorded asset mismatch: " + str(file))
    model_parts = [np.fromfile(root / f"src/weights/conv{layer}_{kind}_3x_flp.bin", dtype="<f4")
                   for layer in (1, 2, 3) for kind in ("weights", "biases")]
    model = np.concatenate(model_parts)
    if model.shape != (8129,) or not np.isfinite(model).all():
        raise ValueError("model dimensions/non-finite values")
    raw_model = quantize(model)
    output.mkdir(parents=True, exist_ok=False)
    model.astype("<f4").tofile(output / "model_float.bin")
    ranges = []
    for (name, offset, shape), part in zip(MODEL_PARTS, model_parts):
        ranges.append({"name": name, "count": part.size, "abs_max": float(np.abs(part).max()),
                       "original_zeros": int(np.count_nonzero(part == 0)),
                       "new_zeros_from_quantization": int(np.count_nonzero((part != 0) & (quantize(part) == 0))),
                       "zero_after_quantization": int(np.count_nonzero(quantize(part) == 0)),
                       "zero_fraction": float(np.mean(quantize(part) == 0))})
    result = {"status": "OFFLINE_ONLY_NOT_BOARD", "source_commit": source_commit,
              "metric_policy": {"peak": 1, "crop": 0, "output_clamp": False, "pixel_rounding": False},
              "model_ranges": ranges, "cases": []}
    for dataset in ("set5", "set14"):
        for file in sorted((root / "test" / dataset).glob("*_3x_LR_u8.bin")):
            start = time.perf_counter()
            name = file.name.split("_3x_")[0]
            gt_file = file.with_name(file.name.replace("LR_u8", "GT_u8"))
            image = np.fromfile(file, dtype="u1").astype(np.float32).reshape(255, 255) / np.float32(255)
            gt = np.fromfile(gt_file, dtype="u1").astype(np.float32).reshape(255, 255) / np.float32(255)
            fixed, diagnostics = infer(quantize(image), raw_model)
            floating, _ = infer(image, model, fixed=False)
            case_dir = output / dataset / name
            case_dir.mkdir(parents=True)
            image.astype("<f4").tofile(case_dir / "input_float.bin")
            signed_to_words(fixed[-1]).reshape(-1).tofile(case_dir / "expected_raw.bin")
            floating[-1].astype("<f4").tofile(case_dir / "float_output.bin")
            actual, reference = fixed[-1][0].astype(np.float64) / 256, floating[-1][0]
            case = {"dataset": dataset, "name": name, "source_hashes": {file.name: sha256_file(file), gt_file.name: sha256_file(gt_file)},
                    "bicubic_vs_gt": metrics(image, gt, 1), "float_vs_gt": metrics(reference, gt, 1),
                    "fixed_vs_gt": metrics(actual, gt, 1), "fixed_vs_float": metrics(actual, reference, 1),
                    "layer_metrics": [metrics(a.astype(np.float64) / 256, b, 1) for a, b in zip(fixed, floating)],
                    "saturations": diagnostics,
                    "output_outside_0_1": {"float": int(np.count_nonzero((reference < 0) | (reference > 1))),
                                             "fixed": int(np.count_nonzero((actual < 0) | (actual > 1)))}}
            golden = file.with_name(file.name.replace("LR_u8", "GR_flp"))
            if golden.is_file():
                official = np.fromfile(golden, dtype="<f4").reshape(255, 255)
                case["float_vs_course_golden"] = metrics(reference, official, 1)
                case["fixed_vs_course_golden"] = metrics(actual, official, 1)
                case["source_hashes"][golden.name] = sha256_file(golden)
            conv1 = file.with_name(file.name.replace("LR_u8", "CONV1_flp"))
            if conv1.is_file():
                official = np.fromfile(conv1, dtype="<f4").reshape(64, 255, 255)
                case["float_conv1_vs_course"] = metrics(floating[0], official, 1)
            case["fixed_psnr_loss_db"] = case["float_vs_gt"]["psnr_db"] - case["fixed_vs_gt"]["psnr_db"]
            case["offline_wall_seconds"] = time.perf_counter() - start
            result["cases"].append(case)
            (case_dir / "metrics.json").write_text(json.dumps(case, indent=2, allow_nan=False))
            (output / "evaluation.json").write_text(json.dumps(result, indent=2, allow_nan=False))
            print(f"{dataset}/{name}: float={case['float_vs_gt']['psnr_db']:.4f} fixed={case['fixed_vs_gt']['psnr_db']:.4f} loss={case['fixed_psnr_loss_db']:.4f} dB", flush=True)
    result["inventory"] = {dataset: [c["name"] for c in result["cases"] if c["dataset"] == dataset] for dataset in ("set5", "set14")}
    result["aggregate"] = {}
    for dataset in ("set5", "set14"):
        cases = [c for c in result["cases"] if c["dataset"] == dataset]
        result["aggregate"][dataset] = {"images": len(cases),
            **{metric + "_mean_psnr_db": float(np.mean([case[metric]["psnr_db"] for case in cases]))
               for metric in ("bicubic_vs_gt", "float_vs_gt", "fixed_vs_gt", "fixed_vs_float")},
            "mean_fixed_psnr_loss_db": float(np.mean([case["fixed_psnr_loss_db"] for case in cases]))}
    (output / "evaluation.json").write_text(json.dumps(result, indent=2, allow_nan=False))
    with (output / "summary.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["dataset", "image", "bicubic_psnr", "float_psnr", "fixed_psnr", "fixed_vs_float_psnr", "fixed_psnr_loss"])
        for case in result["cases"]:
            writer.writerow([case["dataset"], case["name"], *[case[key]["psnr_db"] for key in
                             ("bicubic_vs_gt", "float_vs_gt", "fixed_vs_gt", "fixed_vs_float")], case["fixed_psnr_loss_db"]])
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    evaluate(args.root, args.out, args.source_commit)
