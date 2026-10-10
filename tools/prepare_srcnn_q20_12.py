"""Prepare a V2 official Q20.12 bundle; never usable by the frozen Q24.8 runner."""
import argparse
import copy
import json
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"pynq"))
from srcnn_q20_12_bundle import (PROFILE_ID,SCHEMA,FORMAT,SCALE,NUMERIC_CONTRACT,MODEL_LAYOUT,
    encode_values,validate_float_input,validate_float_model,validate_raw_ranges,read_bundle)
from deployment_numeric import infer,metrics,sha256_file
from precision_numeric import FixedFormat,infer_fixed,official_declared_sizing


def prepare(input_path,model_path,destination,golden_path=None,gt_path=None,crop=0):
    image=validate_float_input(np.load(input_path,allow_pickle=False))
    if image.shape!=(255,255): raise ValueError("deployment bundle requires the full 255x255 frame")
    model=validate_float_model(np.load(model_path,allow_pickle=False))
    fmt=FixedFormat(32,12)
    sizing=official_declared_sizing(fmt)
    widths=[layer["total_bits"] for layer in sizing["layers"]]
    if widths!=NUMERIC_CONTRACT["accumulator_bits"] or not sizing["declared_range_static_assert_passes"]:
        raise ValueError("Q20.12 derived sizing does not match host contract")
    input_words,model_words=encode_values(image),encode_values(model)
    validate_raw_ranges({"input":input_words,"model":model_words})
    fixed,diag=infer_fixed(input_words.view("<i4"),model_words.view("<i4"),fmt,accumulator_bits=widths)
    floating,_=infer(image,model,fixed=False)
    if any(d["data_saturations"] or d["accumulator_saturations"] for d in diag):
        raise ValueError("unexpected saturation under the official numerical contract")
    actual=fixed[-1][0].astype(np.float64)/SCALE
    report={"numeric_profile":PROFILE_ID,"fixed_vs_float":metrics(actual,floating[-1][0],1,crop),
            "layer_metrics":[metrics(a.astype(np.float64)/SCALE,b,1,crop) for a,b in zip(fixed,floating)],
            "saturation_diagnostics":diag}
    sources={"input":{"path":str(Path(input_path).resolve()),"sha256":sha256_file(Path(input_path))},
             "model":{"path":str(Path(model_path).resolve()),"sha256":sha256_file(Path(model_path))}}
    for name,path in (("course_golden",golden_path),("ground_truth",gt_path)):
        if path is not None:
            reference=np.load(path,allow_pickle=False).reshape(255,255)
            report["fixed_vs_"+name]=metrics(actual,reference,1,crop)
            report["float_vs_"+name]=metrics(floating[-1][0],reference,1,crop)
            sources[name]={"path":str(Path(path).resolve()),"sha256":sha256_file(Path(path))}
    destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=False)
    arrays={"input.npy":input_words.reshape(-1),"model.npy":model_words,
            "expected.npy":fixed[-1].astype("<i4").view("<u4").reshape(-1)}
    for name,array in arrays.items(): np.save(destination/name,array,allow_pickle=False)
    manifest={"schema":SCHEMA,"numeric_profile":PROFILE_ID,"format":FORMAT,
              "top":"srcnn_axis_dataflow_top","shape":[1,255,255],
              "numeric_contract":copy.deepcopy(NUMERIC_CONTRACT),"model_layout":copy.deepcopy(MODEL_LAYOUT),
              "sources":sources,"artifacts":{name:{"sha256":sha256_file(destination/name),"words":int(a.size)} for name,a in arrays.items()},
              "reference":"independent integer MAC reference with official 31/37/44-bit accumulator sizing",
              "status":"EXPERIMENT_PREPARED_NOT_HLS_RTL_OR_BOARD_VALIDATED",
              "legacy_overlay_compatible":False}
    (destination/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    (destination/"offline_metrics.json").write_text(json.dumps(report,indent=2,allow_nan=False),encoding="utf-8")
    read_bundle(destination)
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--model",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--golden",type=Path)
    parser.add_argument("--ground-truth",type=Path)
    parser.add_argument("--crop",type=int,default=0)
    args=parser.parse_args()
    print(json.dumps(prepare(args.input,args.model,args.out,args.golden,args.ground_truth,args.crop),indent=2,allow_nan=False))
