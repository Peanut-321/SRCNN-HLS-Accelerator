"""Offline numerical gates, including compatibility with frozen Q24.8."""
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from deployment_numeric import infer, quantize
from precision_numeric import FixedFormat, infer_fixed, official_model_intervals, official_declared_sizing


class PrecisionTests(unittest.TestCase):
    def test_frozen_model_compatibility(self):
        rng=np.random.default_rng(574)
        model=quantize(rng.uniform(-0.2,0.2,8129))
        image=quantize(rng.uniform(0,1,(5,7)))
        frozen, old_diag=infer(image,model)
        candidate, diag=infer_fixed(image,model,FixedFormat())
        for a,b in zip(frozen,candidate): np.testing.assert_array_equal(a,b)
        self.assertEqual([24,30,40],FixedFormat().accumulator_widths())
        for a,b in zip(old_diag,diag):
            for key in a: self.assertEqual(a[key],b[key])

    def test_rounding_ties_negative_and_endpoint_saturation(self):
        for bits in (8,10,12,14,16,18,20):
            fmt=FixedFormat(32,bits)
            np.testing.assert_array_equal(fmt.quantize(np.array([0.5,1.5,2.5,-0.5,-1.5,-2.5])/fmt.scale),[0,2,2,0,-2,-2])
            halfway=np.array([1,3,5,-1,-3,-5],dtype=np.int64)*(fmt.scale//2)
            np.testing.assert_array_equal(fmt.round_output(halfway),[0,2,2,0,-2,-2])
            np.testing.assert_array_equal(fmt.quantize([-1e30,1e30]),[fmt.low,fmt.high])

    def test_interval_covers_pixels_and_partial_sums(self):
        rng=np.random.default_rng(719)
        fmt=FixedFormat(32,14)
        model=fmt.quantize(rng.uniform(-0.1,0.1,8129))
        proof=official_model_intervals(model,fmt)
        for image in (np.zeros((3,5)),np.ones((3,5)),rng.uniform(0,1,(3,5))):
            layers,diag=infer_fixed(fmt.quantize(image),model,fmt)
            for layer,p,d in zip(layers,proof,diag):
                self.assertGreaterEqual(int(layer.min()),p["unclipped_output_min_raw"])
                self.assertLessEqual(int(layer.max()),p["unclipped_output_max_raw"])
                self.assertLessEqual(max(abs(d["accumulator_min"]),abs(d["accumulator_max"])),p["partial_accumulator_abs_bound"])

    def test_old_range_contract_is_not_silently_relaxed(self):
        self.assertFalse(any(x["worst_case_data_saturation"] for x in FixedFormat().sizing()))
        self.assertTrue(any(x["worst_case_data_saturation"] for x in FixedFormat(32,14).sizing()))
        # Actual saturation must still be detected, even if observations on the
        # official model later contain none.
        fmt=FixedFormat(8,6)
        model=np.zeros(8129,dtype=np.int64)
        model[:81]=fmt.scale
        _,diag=infer_fixed(np.full((1,1),fmt.scale),model,fmt)
        self.assertGreater(diag[0]["data_saturations"],0)
        self.assertFalse(official_model_intervals(model,fmt)[0]["data_guaranteed_no_saturation"])

    def test_invalid_formats_and_nonfinite_values(self):
        for w,f in ((1,0),(33,8),(32,-1),(32,32),(32,24)):
            with self.assertRaises(ValueError): FixedFormat(w,f)
        with self.assertRaises(ValueError): FixedFormat().quantize([float("nan")])

    def test_proposed_official_bounds_do_not_remove_old_guard(self):
        fmt=FixedFormat(32,12)
        proposed=official_declared_sizing(fmt)
        self.assertEqual([31,37,44],[x["total_bits"] for x in proposed["layers"]])
        self.assertTrue(proposed["declared_range_static_assert_passes"])
        self.assertTrue(any(x["worst_case_data_saturation"] for x in fmt.sizing()))
        self.assertLess(proposed["layers"][-1]["preactivation_abs_bound"],524288)


if __name__=="__main__": unittest.main()
