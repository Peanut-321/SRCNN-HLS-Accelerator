"""Verify teammate's recorded raw course assets and normalize without resizing.

--root points at the golden/golden directory containing src/weights and test/set5.
Only the recorded Butterfly case is imported; it is not the full Set5 dataset.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from deployment_numeric import sha256_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    records = json.loads(Path(__file__).with_name("course_asset_hashes.json").read_text(encoding="utf-8"))
    verified = {}
    for entry in records["assets"]:
        source = args.root / entry["path"]
        if not source.is_file() or source.stat().st_size != entry["bytes"] or sha256_file(source) != entry["sha256"]:
            raise ValueError("missing or mismatched formal asset: " + str(source))
        verified[entry["path"]] = source
    args.out.mkdir(parents=True, exist_ok=False)
    parameters = []
    for layer in range(1, 4):
        for kind in ("weights", "biases"):
            source = verified[f"src/weights/conv{layer}_{kind}_3x_flp.bin"]
            parameters.append(np.fromfile(source, dtype="<f4"))
    model = np.concatenate(parameters)
    np.save(args.out / "model_float.npy", model, allow_pickle=False)
    for kind, name, dtype in (("LR_u8", "input_float", "u1"), ("GT_u8", "ground_truth", "u1"),
                              ("GR_flp", "course_golden", "<f4")):
        source = verified[f"test/set5/butterfly_3x_{kind}.bin"]
        array = np.fromfile(source, dtype=dtype).astype(np.float32).reshape(255, 255)
        if dtype == "u1":
            array /= np.float32(255)
        np.save(args.out / (name + ".npy"), array, allow_pickle=False)
    (args.out / "course_sources.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    print("Verified/imported Butterfly assets; no full-Set5 claim")


if __name__ == "__main__":
    main()
