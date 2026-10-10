"""Cross-check the offline sweep against a compiled scalar ap_fixed program.

This checks quantization and all three layer raw codes. It is HOST validation,
not Vitis synthesis/RTL or the existing deployment top at a new format.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from precision_numeric import FixedFormat, infer_fixed


def check(executable, root, output, fractions):
    output.mkdir(parents=True,exist_ok=False)
    model=np.concatenate([np.fromfile(root/f"src/weights/conv{i}_{kind}_3x_flp.bin",dtype="<f4") for i in (1,2,3) for kind in ("weights","biases")])
    image=np.fromfile(root/"test/set5/butterfly_3x_LR_u8.bin",dtype="u1").astype(np.float32).reshape(255,255)/np.float32(255)
    rng=np.random.default_rng(610)
    cases=[("official_1x1",image[:1,:1],model), ("official_5x7",image[:5,:7],model),
           ("official_13x17",image[:13,:17],model),
           ("all_ones_1x1",np.ones((1,1),dtype=np.float32),np.ones(8129,dtype=np.float32)),
           ("signed_random_5x7",rng.uniform(0,1,(5,7)).astype(np.float32),rng.uniform(-1,1,8129).astype(np.float32))]
    results={"status":"AP_FIXED_SCALAR_HOST_NOT_RTL","fractions":fractions,"quantization":[],"cases":[]}
    for fraction in fractions:
        fmt=FixedFormat(32,fraction)
        halfway=np.array([0.5,1.5,2.5,-0.5,-1.5,-2.5],dtype=np.float32)/np.float32(fmt.scale)
        values=np.concatenate([rng.uniform(-100,100,10000).astype(np.float32),halfway,np.array([-2**29,2**29],dtype=np.float32)])
        input_file=output/f"quantize_f{fraction}.float.bin"
        output_file=output/f"quantize_f{fraction}.raw.bin"
        values.tofile(input_file)
        subprocess.run([str(executable),"--quantize",str(fraction),str(input_file),str(output_file)],check=True)
        actual=np.fromfile(output_file,dtype="<i4")
        np.testing.assert_array_equal(actual,fmt.quantize(values))
        results["quantization"].append({"fraction_bits":fraction,"values":values.size,"mismatches":0})
        for name,pixels,weights in cases:
            case_dir=output/f"f{fraction}"/name
            case_dir.mkdir(parents=True)
            pixels.astype("<f4").tofile(case_dir/"input.bin")
            weights.astype("<f4").tofile(case_dir/"model.bin")
            h,w=pixels.shape
            prefix=case_dir/"actual"
            subprocess.run([str(executable),str(fraction),str(h),str(w),str(case_dir/"input.bin"),str(case_dir/"model.bin"),str(prefix)],check=True)
            layers,diag=infer_fixed(fmt.quantize(pixels),fmt.quantize(weights),fmt)
            for i,expected in enumerate(layers,1):
                actual=np.fromfile(str(prefix)+f".conv{i}.bin",dtype="<i4").reshape(expected.shape)
                np.testing.assert_array_equal(actual,expected)
            results["cases"].append({"fraction_bits":fraction,"name":name,"shape":[h,w],"layer_words":[layer.size for layer in layers],"mismatches":0,"diagnostics":diag})
            (output/"check.json").write_text(json.dumps(results,indent=2,allow_nan=False))
    (output/"check.json").write_text(json.dumps(results,indent=2,allow_nan=False))
    print(f"PASS: {len(results['quantization'])} quantizer formats; {len(results['cases'])} 3-layer scalar ap_fixed cases",flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe",type=Path,required=True)
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--fractions",type=int,nargs="+",default=[8,10,12,14,16,18,20])
    args=parser.parse_args()
    check(args.exe,args.root,args.out,args.fractions)
