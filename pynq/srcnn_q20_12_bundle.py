"""Host contract for the official Q20.12 experiment, with no board execution.

The legacy runner deliberately accepts V1/Q24.8 only. This V2 reader/codec is
standalone so a future validated Q20.12 runner can import it explicitly.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

PROFILE_ID = "official_q20_12_v1"
SCHEMA = "SRCNN_DEPLOYMENT_BUNDLE_V2"
FORMAT = "signed Q20.12 raw bits in uint32"
SCALE = 4096
FRAME_WORDS = 65025
MODEL_WORDS = 8129
MODEL_LAYOUT = [
    {"name":"conv1_weights","offset":0,"shape":[64,1,9,9]},
    {"name":"conv1_bias","offset":5184,"shape":[64]},
    {"name":"conv2_weights","offset":5248,"shape":[32,64,1,1]},
    {"name":"conv2_bias","offset":7296,"shape":[32]},
    {"name":"conv3_weights","offset":7328,"shape":[1,32,5,5]},
    {"name":"conv3_bias","offset":8128,"shape":[1]},
]
NUMERIC_CONTRACT = {
    "data_total_bits":32,"data_integer_bits":20,"data_fraction_bits":12,
    "scale":SCALE,"data_rounding":"AP_RND_CONV","data_saturation":"AP_SAT",
    "accumulator_bits":[31,37,44],"accumulator_integer_bits":[7,13,20],
    "accumulator_fraction_bits":24,"accumulator_rounding":"AP_TRN",
    "accumulator_saturation":"AP_SAT","input_range":[0,1],
    "model_abs_max_rationals":[[600,1000],[383,1000],[852,1000],[85,1000],[163,1000],[29,1000]],
    "allow_worst_case_data_saturation":False,
}


def encode_values(values):
    """Nearest/even + signed saturation; validate semantic ranges separately."""
    values=np.asarray(values,dtype=np.float64)
    if not np.isfinite(values).all(): raise ValueError("non-finite value")
    return np.clip(np.rint(values*SCALE),-(2**31),2**31-1).astype("<i4").view("<u4")


def decode_words(words):
    words=np.asarray(words)
    if words.dtype!=np.dtype("<u4"): raise ValueError("Q20.12 decoder requires little-endian uint32 raw words")
    return words.view("<i4").astype(np.float64)/SCALE


def validate_float_input(image):
    image=np.asarray(image)
    if image.ndim==3 and image.shape[0]==1: image=image[0]
    if (image.ndim!=2 or min(image.shape)<1 or max(image.shape)>255 or
            not np.issubdtype(image.dtype,np.floating) or not np.isfinite(image).all() or
            np.min(image)<0 or np.max(image)>1):
        raise ValueError("Q20.12 input must be finite normalized [0,1] floats, H/W in [1,255]")
    return image.astype(np.float32)


def validate_float_model(model):
    model=np.asarray(model)
    if model.shape!=(MODEL_WORDS,) or not np.issubdtype(model.dtype,np.floating) or not np.isfinite(model).all():
        raise ValueError("Q20.12 model must contain 8129 finite floats")
    # Files sent to C-sim are float32; validate that representation as well as
    # the user's original values before any quantization can hide violations.
    converted=model.astype(np.float32)
    for part,(n,d) in zip(MODEL_LAYOUT,NUMERIC_CONTRACT["model_abs_max_rationals"]):
        offset,count=part["offset"],int(np.prod(part["shape"]))
        for values in (model,converted):
            if np.any(np.abs(values[offset:offset+count].astype(np.float64))>n/d):
                raise ValueError("Q20.12 model outside declared range: "+part["name"])
    return converted


def validate_raw_ranges(arrays):
    image=arrays["input"].view("<i4").astype(np.int64)
    if np.any((image<0)|(image>SCALE)): raise ValueError("Q20.12 input raw range violation")
    model=arrays["model"].view("<i4").astype(np.int64)
    for part,(n,d) in zip(MODEL_LAYOUT,NUMERIC_CONTRACT["model_abs_max_rationals"]):
        offset,count=part["offset"],int(np.prod(part["shape"]))
        maximum=(n*SCALE+d-1)//d
        if np.any(np.abs(model[offset:offset+count])>maximum):
            raise ValueError("Q20.12 model raw range violation: "+part["name"])


def validate_manifest(manifest):
    if (manifest.get("schema")!=SCHEMA or manifest.get("numeric_profile")!=PROFILE_ID or
            manifest.get("format")!=FORMAT or manifest.get("numeric_contract")!=NUMERIC_CONTRACT or
            manifest.get("top")!="srcnn_axis_dataflow_top" or manifest.get("shape")!=[1,255,255] or
            manifest.get("model_layout")!=MODEL_LAYOUT):
        raise ValueError("wrong Q20.12 deployment bundle contract")


def read_bundle(path):
    path=Path(path)
    manifest=json.loads((path/"manifest.json").read_text(encoding="utf-8"))
    validate_manifest(manifest)
    arrays={}
    for name,count in (("input",FRAME_WORDS),("model",MODEL_WORDS),("expected",FRAME_WORDS)):
        file=path/(name+".npy")
        recorded=manifest.get("artifacts",{}).get(file.name,{})
        if recorded.get("words")!=count or hashlib.sha256(file.read_bytes()).hexdigest()!=recorded.get("sha256"):
            raise ValueError("Q20.12 bundle checksum/count mismatch: "+name)
        value=np.load(file,allow_pickle=False)
        if value.shape!=(count,) or value.dtype!=np.dtype("<u4"):
            raise ValueError("Q20.12 bundle array shape/dtype mismatch: "+name)
        arrays[name]=value
    validate_raw_ranges(arrays)
    return manifest,arrays


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle",type=Path,required=True)
    args=parser.parse_args()
    manifest,arrays=read_bundle(args.bundle)
    print(json.dumps({"status":"HOST_INSPECTION_ONLY_NOT_BOARD","numeric_profile":PROFILE_ID,
                      "decoded_ranges":{name:[float(decode_words(a).min()),float(decode_words(a).max())]
                                        for name,a in arrays.items()}},indent=2))
