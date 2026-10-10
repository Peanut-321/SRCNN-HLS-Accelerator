"""Host gates for profile separation, packing and declared numerical bounds."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
import uuid
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"pynq"))
sys.path.insert(0,str(ROOT/"tools"))
import srcnn_q20_12_bundle as candidate
from srcnn_axis_host import read_bundle as read_legacy
from deployment_numeric import MODEL_PARTS,words_to_float
from precision_numeric import FixedFormat,infer_fixed


class BundleTests(unittest.TestCase):
    def setUp(self):
        scratch=ROOT/".codex-build/q20-12-tests"
        scratch.mkdir(parents=True,exist_ok=True)
        self.path=scratch/str(uuid.uuid4())
        self.path.mkdir()

    def tearDown(self):
        for name in ("input.npy","model.npy","expected.npy","manifest.json"):
            (self.path/name).unlink(missing_ok=True)
        self.path.rmdir()

    def write_bundle(self,model=None,image=None):
        arrays={"input":np.zeros(65025,dtype="<u4") if image is None else image,
                "model":np.zeros(8129,dtype="<u4") if model is None else model,
                "expected":np.zeros(65025,dtype="<u4")}
        manifest={"schema":candidate.SCHEMA,"numeric_profile":candidate.PROFILE_ID,
            "format":candidate.FORMAT,"top":"srcnn_axis_dataflow_top","shape":[1,255,255],
            "numeric_contract":copy.deepcopy(candidate.NUMERIC_CONTRACT),
            "model_layout":copy.deepcopy(candidate.MODEL_LAYOUT),"artifacts":{}}
        for name,array in arrays.items():
            file=self.path/(name+".npy")
            np.save(file,array,allow_pickle=False)
            manifest["artifacts"][file.name]={"sha256":hashlib.sha256(file.read_bytes()).hexdigest(),"words":array.size}
        (self.path/"manifest.json").write_text(json.dumps(manifest))
        return manifest

    def test_codec_scale_signed_ties_and_saturation(self):
        values=np.array([0.5,1.5,2.5,-0.5,-1.5,-2.5])/4096
        raw=candidate.encode_values(values)
        np.testing.assert_array_equal(raw.view("<i4"),[0,2,2,0,-2,-2])
        np.testing.assert_array_equal(candidate.encode_values([-1e20,1e20]).view("<i4"),[-2**31,2**31-1])
        raw=candidate.encode_values(np.array([-0.125,0,1],dtype=np.float32))
        np.testing.assert_array_equal(raw.view("<i4"),[-512,0,4096])
        np.testing.assert_array_equal(candidate.decode_words(raw),[-0.125,0,1])
        self.assertNotEqual(candidate.decode_words(raw)[0],words_to_float(raw)[0])
        with self.assertRaises(ValueError): candidate.decode_words(raw.view("<i4"))

    def test_model_order_is_unchanged(self):
        self.assertEqual(candidate.MODEL_LAYOUT,[{"name":n,"offset":o,"shape":list(s)} for n,o,s in MODEL_PARTS])

    def test_profiles_cannot_be_mixed(self):
        manifest=self.write_bundle()
        candidate.read_bundle(self.path)
        with self.assertRaises(ValueError): read_legacy(self.path)
        manifest.update(schema="SRCNN_DEPLOYMENT_BUNDLE_V1",format="signed Q24.8 raw bits in uint32")
        (self.path/"manifest.json").write_text(json.dumps(manifest))
        read_legacy(self.path)
        with self.assertRaises(ValueError): candidate.read_bundle(self.path)

    def test_contract_changes_rejected_before_loading_arrays(self):
        manifest=self.write_bundle()
        for key,value in (("scale",256),("accumulator_bits",[32,38,48]),("allow_worst_case_data_saturation",True)):
            corrupted=copy.deepcopy(manifest)
            corrupted["numeric_contract"][key]=value
            with self.assertRaises(ValueError): candidate.validate_manifest(corrupted)

    def test_every_float_model_part_is_range_checked_before_quantizing(self):
        candidate.validate_float_model(np.zeros(8129,dtype=np.float32))
        for part,(n,d) in zip(candidate.MODEL_LAYOUT,candidate.NUMERIC_CONTRACT["model_abs_max_rationals"]):
            model=np.zeros(8129,dtype=np.float64)
            model[part["offset"]]=n/d+1e-10  # Can round to a permitted raw code; still out of contract.
            with self.assertRaisesRegex(ValueError,part["name"]): candidate.validate_float_model(model)
        with self.assertRaises(ValueError): candidate.validate_float_model(np.full(8129,np.nan))
        with self.assertRaises(ValueError): candidate.validate_float_model(np.zeros(8129,dtype=np.uint32))

    def test_input_range_is_checked_before_cast_or_quantization(self):
        for value in (-1e-10,1+1e-10,np.nan):
            with self.assertRaises(ValueError): candidate.validate_float_input(np.full((1,1),value))
        with self.assertRaises(ValueError): candidate.validate_float_input(np.zeros((256,1)))

    def test_valid_checksums_do_not_hide_raw_range_violations(self):
        model=np.zeros(8129,dtype="<u4")
        model[8128]=np.array([-120],dtype="<i4").view("<u4")[0]
        self.write_bundle(model=model)
        with self.assertRaisesRegex(ValueError,"conv3_bias"): candidate.read_bundle(self.path)
        image=np.zeros(65025,dtype="<u4");image[0]=4097
        self.write_bundle(image=image)
        with self.assertRaisesRegex(ValueError,"input raw"): candidate.read_bundle(self.path)

    def test_checksum_corruption_is_rejected(self):
        self.write_bundle()
        with (self.path/"input.npy").open("ab") as file: file.write(b"changed")
        with self.assertRaisesRegex(ValueError,"checksum"): candidate.read_bundle(self.path)

    def test_narrow_derived_accumulators_cover_declared_worst_case(self):
        fmt=FixedFormat(32,12)
        model=np.empty(8129,dtype=np.int64)
        for part,(n,d) in zip(candidate.MODEL_LAYOUT,candidate.NUMERIC_CONTRACT["model_abs_max_rationals"]):
            offset,count=part["offset"],int(np.prod(part["shape"]))
            model[offset:offset+count]=(n*4096+d-1)//d
        image=np.full((1,1),4096,dtype=np.int64)
        generic,_=infer_fixed(image,model,fmt)
        official,diag=infer_fixed(image,model,fmt,accumulator_bits=[31,37,44])
        for a,b in zip(generic,official): np.testing.assert_array_equal(a,b)
        self.assertTrue(all(x["accumulator_saturations"]==x["data_saturations"]==0 for x in diag))
        self.assertGreater(official[-1][0,0,0]/4096,348000)


if __name__=="__main__": unittest.main()
