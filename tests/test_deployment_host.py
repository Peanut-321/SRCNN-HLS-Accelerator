"""Software gates for deployment packing and bounded host completion.

Optional --rtl-vectors validates independent arithmetic against the vectors
already checked by XSIM; it does not rerun or claim full-frame RTL simulation.
"""
import argparse
import json
from pathlib import Path
import sys
import uuid
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "pynq"))
from deployment_numeric import infer, metrics, quantize, signed_to_words, words_to_float
from srcnn_axis_host import arm_dma, read_bundle, wait_complete, FRAME_WORDS, Runner
from summarize_set5 import summarize

RTL_VECTORS = None


class FakeMMIO:
    def __init__(self, registers):
        self.registers = registers
        self.writes = []

    def read(self, offset):
        return self.registers.get(offset, 0)

    def write(self, offset, value):
        self.writes.append((offset, value))


class DeploymentTests(unittest.TestCase):
    def test_quantization_ties_sign_and_saturation(self):
        values = np.array([0.5, 1.5, 2.5, -0.5, -1.5, -2.5]) / 256
        np.testing.assert_array_equal(quantize(values), [0, 2, 2, 0, -2, -2])
        np.testing.assert_array_equal(quantize([-1e20, 1e20]), [-(2**31), 2**31 - 1])
        np.testing.assert_array_equal(words_to_float(signed_to_words(quantize([-1, 0, 1]))), [-1, 0, 1])
        with self.assertRaises(ValueError):
            quantize([float("nan")])

    def test_metrics_crop_and_perfect(self):
        actual, reference = np.zeros((5, 5)), np.zeros((5, 5))
        actual[0, 0] = 1
        self.assertEqual(metrics(actual, reference, 1)["mse"], 1 / 25)
        self.assertTrue(metrics(actual, reference, 1, 1)["perfect_match"])
        with self.assertRaises(ValueError):
            metrics(actual, reference, 1, 3)

    def test_replicate_and_channel_layout(self):
        model = np.zeros(8129, dtype=np.int32)
        model[0] = 256        # conv1 out0 top-left weight
        model[5248] = 256     # conv2 out0/in0
        model[7328 + 12] = 256  # conv3 in0 kernel centre
        image = np.array([[256, 512], [768, 1024]], dtype=np.int32)
        layers, _ = infer(image, model)
        np.testing.assert_array_equal(layers[-1][0], np.full((2, 2), 256))

    def test_axi_64bit_address(self):
        mmio = FakeMMIO({})
        arm_dma(mmio, 0x30, 0x123456789, 260100)
        self.assertEqual(mmio.writes, [(0x48, 0x23456789), (0x4c, 1), (0x58, 260100)])

    def test_completion_and_short_receive(self):
        dma = FakeMMIO({4: 2, 0x34: 2, 0x28: 260100, 0x58: 260100})
        wait_complete(dma, FakeMMIO({0: 2}), 1)
        dma.registers[0x58] = 4
        with self.assertRaises(RuntimeError):
            wait_complete(dma, FakeMMIO({0: 2}), 1)

    def test_error_and_timeout(self):
        with self.assertRaises(RuntimeError):
            wait_complete(FakeMMIO({4: 0x20}), FakeMMIO({}), 1)
        ticks = iter([0, 0.5, 1.1])
        with self.assertRaises(TimeoutError):
            wait_complete(FakeMMIO({}), FakeMMIO({}), 1, clock=lambda: next(ticks), pause=lambda _: None)

    def test_nonfinite_timeout_is_rejected(self):
        for timeout in (float("nan"), float("inf"), 0, -1):
            with self.assertRaises(ValueError):
                wait_complete(FakeMMIO({}), FakeMMIO({}), timeout)

    def test_butterfly_is_not_full_set5(self):
        with self.assertRaises(ValueError):
            summarize({"butterfly": "unavailable"})

    def test_runner_model_pointer_receive_first_and_buffer_cleanup(self):
        class Buffer(np.ndarray):
            def __new__(cls, count, address):
                array = np.zeros(count, dtype=np.uint32).view(cls)
                array.physical_address, array.freed, array.flushed, array.invalidated = address, False, False, False
                return array
            def flush(self): self.flushed = True
            def invalidate(self): self.invalidated = True
            def freebuffer(self): self.freed = True
        events, allocated = [], []
        class DMA(FakeMMIO):
            def write(self, offset, value):
                events.append(("dma", offset, value))
                self.registers[offset] = 0 if (offset == 0 and value == 4) else value
                if offset == 0x28:
                    self.registers[4] = self.registers[0x34] = 2
                    allocated[1][:] = 0
        class Kernel(FakeMMIO):
            def write(self, offset, value):
                events.append(("kernel", offset, value))
                self.registers[offset] = 2 if offset == 0 else value
        def allocate(shape, dtype):
            buffer = Buffer(shape[0], 0x100000000 + len(allocated) * 0x100000)
            allocated.append(buffer)
            return buffer
        runner = Runner.__new__(Runner)
        runner.allocate, runner.timeout, runner.quarantined = allocate, 1, []
        runner.dma, runner.kernel, runner.identity = DMA({4: 1, 0x34: 1}), Kernel({0: 4}), {}
        arrays = {"input": np.zeros(FRAME_WORDS, dtype=np.uint32), "model": np.zeros(8129, dtype=np.uint32),
                  "expected": np.zeros(FRAME_WORDS, dtype=np.uint32)}
        result, _ = runner.run(arrays)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(all(b.flushed and b.freed for b in allocated))
        self.assertTrue(allocated[1].invalidated)
        self.assertLess(events.index(("dma", 0x58, 260100)), events.index(("kernel", 0, 1)))
        self.assertLess(events.index(("kernel", 0, 1)), events.index(("dma", 0x28, 260100)))
        self.assertIn(("kernel", 0x10, 0x200000), events)
        self.assertIn(("kernel", 0x14, 1), events)

    def test_incomplete_run_resets_entire_overlay_before_free(self):
        class Buffer(np.ndarray):
            def __new__(cls, count):
                array = np.zeros(count, dtype=np.uint32).view(cls)
                array.physical_address, array.freed = 0x100000, False
                return array
            def flush(self): pass
            def freebuffer(self):
                self.freed = True
                assert overlay.downloaded
        allocated = []
        def allocate(shape, dtype):
            buffer = Buffer(shape[0])
            allocated.append(buffer)
            return buffer
        class DMA(FakeMMIO):
            def write(self, offset, value):
                self.registers[offset] = 0 if offset == 0 and value == 4 else value
        class Overlay:
            downloaded = False
            def download(self):
                self.downloaded = True
                runner.dma.registers[4] = runner.dma.registers[0x34] = 1
                runner.kernel.registers[0] = 4
        runner, overlay = Runner.__new__(Runner), Overlay()
        runner.allocate, runner.timeout, runner.quarantined = allocate, 0.001, []
        runner.overlay, runner.identity = overlay, {}
        runner.dma, runner.kernel = DMA({4: 1, 0x34: 1}), FakeMMIO({0: 4})
        with self.assertRaises(TimeoutError):
            runner.run({"input": np.zeros(FRAME_WORDS, dtype=np.uint32), "model": np.zeros(8129, dtype=np.uint32)})
        self.assertTrue(overlay.downloaded and all(b.freed for b in allocated))

    def test_bundle_rejects_corruption(self):
        import hashlib
        scratch = ROOT / ".codex-build" / "host-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        path = scratch / str(uuid.uuid4())
        path.mkdir()
        try:
            manifest = {"schema": "SRCNN_DEPLOYMENT_BUNDLE_V1", "top": "srcnn_axis_dataflow_top",
                        "shape": [1, 255, 255], "format": "signed Q24.8 raw bits in uint32", "artifacts": {}}
            for name, count in (("input", FRAME_WORDS), ("model", 8129), ("expected", FRAME_WORDS)):
                artifact = path / (name + ".npy")
                np.save(artifact, np.zeros(count, dtype="<u4"))
                manifest["artifacts"][artifact.name] = {"sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}
            (path / "manifest.json").write_text(json.dumps(manifest))
            read_bundle(path)
            with (path / "input.npy").open("ab") as file:
                file.write(b"corrupt")
            with self.assertRaises(ValueError):
                read_bundle(path)
        finally:
            # Only remove this test's known files; no recursive directory removal.
            for name in ("input.npy", "model.npy", "expected.npy", "manifest.json"):
                (path / name).unlink(missing_ok=True)
            path.rmdir()

    def test_independent_reference_matches_rtl_checked_output(self):
        if RTL_VECTORS is None:
            self.skipTest("supply existing XSIM vector directory")
        def codes(name):
            return np.array([int(line, 16) for line in (RTL_VECTORS / name).read_text().split()], dtype="<u4")
        image = codes("input.hex").view("<i4").reshape(13, 17)
        model = codes("model.hex").view("<i4")
        layers, _ = infer(image, model)
        actual = signed_to_words(layers[-1]).reshape(-1)
        np.testing.assert_array_equal(actual, codes("expected.hex"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rtl-vectors", type=Path)
    args, remaining = parser.parse_known_args()
    RTL_VECTORS = args.rtl_vectors
    unittest.main(argv=[sys.argv[0], *remaining])
