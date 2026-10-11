"""Prepare a changed-input/model full-frame test using existing numeric tools."""
import argparse
from pathlib import Path
import sys

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--float-bundle", type=Path, required=True)
    parser.add_argument("--profile", choices=("q24_8", "q20_12"), required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.source / "tools"))
    args.out.mkdir(parents=True, exist_ok=False)
    image = np.load(args.float_bundle / "input_float.npy", allow_pickle=False)
    model = np.load(args.float_bundle / "model_float.npy", allow_pickle=False).copy()
    changed = np.float32(1) - image
    if args.profile == "q20_12":
        # Stay below the strict float-domain 0.029 bound. Raw code 119 is
        # allowed after quantization, but 119/4096 itself exceeds that bound.
        model[-1] -= np.float32(1 / 4096)
        from prepare_srcnn_q20_12 import prepare
    else:
        model[-1] += np.float32(1 / 256)
        from prepare_srcnn_deployment import prepare
    np.save(args.out / "input_float.npy", changed, allow_pickle=False)
    np.save(args.out / "model_float.npy", model, allow_pickle=False)
    prepare(args.out / "input_float.npy", args.out / "model_float.npy", args.out / "bundle")
    print(f"PASS: Prepared changed-input/model case for {args.profile}; not board validated.")


if __name__ == "__main__":
    main()
