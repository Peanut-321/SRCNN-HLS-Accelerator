"""Study fractional precision offline using verified official-model assets.

The default sweep preserves 32-bit transport. Existing deployment packing,
HLS types, RTL and overlay stay unchanged. Quality limits are proposed local
engineering criteria, never course requirements or a board result.
"""
import argparse
import csv
import json
from pathlib import Path
import time
import numpy as np
from deployment_numeric import MODEL_PARTS, infer, metrics, sha256_file
from precision_numeric import FixedFormat, infer_fixed, official_model_intervals, official_declared_sizing


def study(root, output, source_commit, fractions, max_quality_delta, min_reference_psnr):
    recorded = json.loads(Path(__file__).with_name("course_asset_hashes.json").read_text())
    for item in recorded["assets"]:
        file = root/item["path"]
        if file.stat().st_size != item["bytes"] or sha256_file(file) != item["sha256"]:
            raise ValueError("recorded asset mismatch: " + str(file))
    if not (np.isfinite(max_quality_delta) and max_quality_delta >= 0 and np.isfinite(min_reference_psnr)):
        raise ValueError("invalid engineering quality criteria")
    formats = [FixedFormat(32, f) for f in sorted(set(fractions))]
    if not formats: raise ValueError("empty format list")
    model = np.concatenate([np.fromfile(root/f"src/weights/conv{i}_{kind}_3x_flp.bin", dtype="<f4")
                            for i in (1,2,3) for kind in ("weights", "biases")])
    if model.size != 8129 or not np.isfinite(model).all(): raise ValueError("invalid model")
    output.mkdir(parents=True, exist_ok=False)
    result = {"status": "OFFLINE_PRECISION_STUDY_NOT_HARDWARE", "source_commit": source_commit,
              "metric_policy": {"peak": 1, "crop": 0, "output_clamp": False, "pixel_rounding": False},
              "engineering_criteria": {"not_course_requirement": True,
                  "max_abs_reconstruction_psnr_delta_db": max_quality_delta,
                  "min_fixed_vs_float_psnr_db": min_reference_psnr,
                  "require_zero_observed_saturations": True, "require_official_model_interval_proof": True},
              "model_hashes": {str(p.relative_to(root)): sha256_file(p) for p in sorted((root/"src/weights").glob("*.bin"))},
              "formats": []}
    for fmt in formats:
        raw_model = fmt.quantize(model)
        proposed_contract = official_declared_sizing(fmt)
        parts = []
        for part_index,(name, offset, shape) in enumerate(MODEL_PARTS):
            part, raw = model[offset:offset+int(np.prod(shape))], raw_model[offset:offset+int(np.prod(shape))]
            if int(np.max(np.abs(raw))) > proposed_contract["raw_model_abs_max_bounds"][part_index]:
                raise ValueError("official parameter exceeds proposed range contract: "+name)
            parts.append({"name": name, "count": part.size,
                          "new_zero_count": int(np.count_nonzero((part != 0) & (raw == 0))),
                          "max_quantization_error": float(np.max(np.abs(raw/fmt.scale-part)))})
        result["formats"].append({"format": fmt.label, "total_bits": fmt.total_bits,
            "integer_bits": fmt.total_bits-fmt.fraction_bits, "fraction_bits": fmt.fraction_bits,
            "step": 1/fmt.scale, "old_generic_sizing": fmt.sizing(),
            "old_declared_range_static_assert_passes": not any(p["worst_case_data_saturation"] for p in fmt.sizing()),
            "proposed_official_contract": proposed_contract,
            "official_model_intervals": official_model_intervals(raw_model, fmt),
            "model_quantization": parts, "cases": []})
    for dataset in ("set5", "set14"):
        for file in sorted((root/"test"/dataset).glob("*_3x_LR_u8.bin")):
            name = file.name.split("_3x_")[0]
            gt_file = file.with_name(file.name.replace("LR_u8", "GT_u8"))
            image = np.fromfile(file, dtype="u1").astype(np.float32).reshape(255,255)/np.float32(255)
            gt = np.fromfile(gt_file, dtype="u1").astype(np.float32).reshape(255,255)/np.float32(255)
            floating, _ = infer(image, model, fixed=False)
            float_metric = metrics(floating[-1][0], gt, 1)
            for fmt, entry in zip(formats, result["formats"]):
                start = time.perf_counter()
                layers, diagnostics = infer_fixed(fmt.quantize(image), fmt.quantize(model), fmt)
                actual = layers[-1][0].astype(np.float64)/fmt.scale
                reconstruction = metrics(actual, gt, 1)
                case = {"dataset": dataset, "name": name,
                    "source_hashes": {file.name: sha256_file(file), gt_file.name: sha256_file(gt_file)},
                    "float_vs_gt": float_metric, "fixed_vs_gt": reconstruction,
                    "fixed_vs_float": metrics(actual, floating[-1][0], 1),
                    "float_to_fixed_psnr_loss_db": float_metric["psnr_db"]-reconstruction["psnr_db"],
                    "layer_metrics": [metrics(a.astype(np.float64)/fmt.scale,b,1) for a,b in zip(layers,floating)],
                    "layer_ranges": diagnostics, "wall_seconds": time.perf_counter()-start}
                entry["cases"].append(case)
                destination = output/fmt.label/dataset/name
                destination.mkdir(parents=True)
                layers[-1].astype("<i4").tofile(destination/"expected_raw.bin")
                (destination/"metrics.json").write_text(json.dumps(case,indent=2,allow_nan=False))
                (output/"study.json").write_text(json.dumps(result,indent=2,allow_nan=False))
                print(f"{dataset}/{name} F={fmt.fraction_bits}: PSNR={reconstruction['psnr_db']:.6f} loss={case['float_to_fixed_psnr_loss_db']:+.6f} ref={case['fixed_vs_float']['psnr_db']:.3f}",flush=True)
    for entry in result["formats"]:
        cases = entry["cases"]
        if not cases: raise ValueError("no paired image assets")
        acc_sat = sum(layer["accumulator_saturations"] for c in cases for layer in c["layer_ranges"])
        data_sat = sum(layer["data_saturations"] for c in cases for layer in c["layer_ranges"])
        delta = max(abs(c["float_to_fixed_psnr_loss_db"]) for c in cases)
        reference = min(c["fixed_vs_float"]["psnr_db"] for c in cases if not c["fixed_vs_float"]["perfect_match"]) if any(not c["fixed_vs_float"]["perfect_match"] for c in cases) else None
        proof = all(p["accumulator_guaranteed_no_saturation"] and p["data_guaranteed_no_saturation"] for p in entry["official_model_intervals"])
        entry["aggregate"] = {"images": len(cases), "max_abs_quality_delta_db": delta,
            "worst_quality_case": max(cases,key=lambda c: abs(c["float_to_fixed_psnr_loss_db"]))["name"],
            "min_fixed_vs_float_psnr_db": reference, "accumulator_saturations": acc_sat, "data_saturations": data_sat,
            "engineering_gate_pass": delta <= max_quality_delta and (reference is None or reference >= min_reference_psnr) and acc_sat == data_sat == 0 and proof,
            "dataset_mean_fixed_psnr_db": {d: float(np.mean([c["fixed_vs_gt"]["psnr_db"] for c in cases if c["dataset"]==d])) for d in ("set5","set14") if any(c["dataset"]==d for c in cases)}}
    result["inventory"] = {d: [c["name"] for c in result["formats"][0]["cases"] if c["dataset"]==d] for d in ("set5","set14")}
    passing = [e for e in result["formats"] if e["aggregate"]["engineering_gate_pass"]]
    result["minimum_tested_passing_fraction_bits"] = min(e["fraction_bits"] for e in passing) if passing else None
    (output/"study.json").write_text(json.dumps(result,indent=2,allow_nan=False))
    with (output/"summary.csv").open("w",newline="",encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["format","set5_butterfly_psnr","set14_supplied_mean_psnr","max_abs_quality_delta","min_reference_psnr","acc_sat","data_sat","engineering_gate"])
        for e in result["formats"]:
            a=e["aggregate"]
            writer.writerow([e["format"],a["dataset_mean_fixed_psnr_db"].get("set5"),a["dataset_mean_fixed_psnr_db"].get("set14"),a["max_abs_quality_delta_db"],a["min_fixed_vs_float_psnr_db"],a["accumulator_saturations"],a["data_saturations"],a["engineering_gate_pass"]])
    return result


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--source-commit",required=True)
    parser.add_argument("--fractions",type=int,nargs="+",default=[8,10,12,14,16,18,20])
    parser.add_argument("--max-quality-delta",type=float,default=0.1)
    parser.add_argument("--min-reference-psnr",type=float,default=50)
    args=parser.parse_args()
    study(args.root,args.out,args.source_commit,args.fractions,args.max_quality_delta,args.min_reference_psnr)
