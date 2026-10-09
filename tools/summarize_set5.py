"""Aggregate five separately prepared official Set5 cases, never synthetic data.

--cases JSON maps baby/bird/butterfly/head/woman to deployment bundle directories.
All cases must contain course Golden and normalized ground truth comparisons.
"""
import argparse
import json
from pathlib import Path
import numpy as np


def summarize(cases):
    if set(cases) != {"baby", "bird", "butterfly", "head", "woman"}:
        raise ValueError("full Set5 requires all five named cases")
    reports = {name: json.loads((Path(path) / "offline_metrics.json").read_text()) for name, path in cases.items()}
    result = {"status": "OFFLINE_REFERENCE_ONLY_NOT_BOARD", "cases": reports, "aggregate": {}}
    for metric in ("fixed_vs_float", "fixed_vs_course_golden", "fixed_vs_ground_truth", "float_vs_ground_truth"):
        values = [report[metric] for report in reports.values()]
        if len({(value["peak"], value["crop"]) for value in values}) != 1:
            raise ValueError("inconsistent peak/crop policy")
        perfect = sum(value["perfect_match"] for value in values)
        result["aggregate"][metric] = {
            "mean_image_mse": float(np.mean([value["mse"] for value in values])),
            "mean_image_psnr_db": None if perfect else float(np.mean([value["psnr_db"] for value in values])),
            "mean_psnr_is_infinite": bool(perfect), "perfect_images": perfect,
            "crop": values[0]["crop"], "peak": values[0]["peak"]}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text())
    cases = {name: str((args.cases.parent / value).resolve()) for name, value in cases.items()}
    result = summarize(cases)
    with args.out.open("x", encoding="utf-8") as file:
        json.dump(result, file, indent=2, allow_nan=False)
