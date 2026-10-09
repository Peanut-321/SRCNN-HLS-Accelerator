"""Board-pending runner for the actual srcnn_axis_255x255 overlay.

Uses bounded MMIO polling of simple AXI DMA, avoiding blocking DMA.wait().
Software tests use fake MMIO only. A PASS here requires physical board data.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import time
import numpy as np

FRAME_WORDS = 65025
MODEL_WORDS = 8129
ERROR_MASK = 0x70
BIT_SHA256 = "fed3b1059333bd1d42255a5668a10854573b427227df95a59ab3204fce960415"
HWH_SHA256 = "00cd8212361b850514fd85b3e3454fec13275a136008d58f6fd8c56453c5710a"


def read_bundle(path):
    path = Path(path)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if (manifest.get("schema") != "SRCNN_DEPLOYMENT_BUNDLE_V1" or
        manifest.get("top") != "srcnn_axis_dataflow_top" or manifest.get("shape") != [1, 255, 255] or
        manifest.get("format") != "signed Q24.8 raw bits in uint32"):
        raise ValueError("wrong deployment bundle contract")
    result = {}
    for name, count in (("input", FRAME_WORDS), ("model", MODEL_WORDS), ("expected", FRAME_WORDS)):
        artifact = path / (name + ".npy")
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != manifest["artifacts"][artifact.name]["sha256"]:
            raise ValueError("bundle checksum mismatch: " + name)
        array = np.load(artifact, allow_pickle=False)
        if array.shape != (count,) or array.dtype != np.dtype("<u4"):
            raise ValueError("wrong word count/dtype: " + name)
        result[name] = array
    return manifest, result


def snapshot(dma, kernel):
    # Reading CTRL acknowledges ap_done; polling latches it before taking snapshots.
    return {"mm2s_status": hex(dma.read(0x04)), "s2mm_status": hex(dma.read(0x34)),
            "mm2s_bytes": dma.read(0x28), "s2mm_bytes": dma.read(0x58),
            "control": hex(kernel.read(0)), "model_low": hex(kernel.read(0x10)),
            "model_high": hex(kernel.read(0x14))}


def reset_dma(dma, timeout=2.0):
    dma.write(0, 4)
    deadline = time.monotonic() + timeout
    while dma.read(0) & 4:
        if time.monotonic() >= deadline:
            raise TimeoutError("DMA reset timeout")
        time.sleep(0.001)
    for offset in (0, 0x30):
        dma.write(offset + 4, 0x7000)  # acknowledge interrupt status
        dma.write(offset, 1)         # Run/Stop, polling mode


def arm_dma(dma, offset, address, nbytes):
    dma.write(offset + 0x18, int(address) & 0xFFFFFFFF)
    dma.write(offset + 0x1C, int(address) >> 32)
    dma.write(offset + 0x28, int(nbytes))


def wait_complete(dma, kernel, timeout, clock=time.monotonic, pause=time.sleep):
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    deadline, done = clock() + timeout, False
    while True:
        tx, rx, control = dma.read(4), dma.read(0x34), kernel.read(0)
        done |= bool(control & 2)
        if (tx | rx) & ERROR_MASK:
            raise RuntimeError("DMA error: tx=%#x rx=%#x" % (tx, rx))
        if done and tx & 2 and rx & 2:
            if dma.read(0x28) != FRAME_WORDS * 4 or dma.read(0x58) != FRAME_WORDS * 4:
                raise RuntimeError("DMA transferred-byte count mismatch")
            return
        if clock() >= deadline:
            raise TimeoutError("SRCNN/DMA completion timeout: tx=%#x rx=%#x done=%s" % (tx, rx, done))
        pause(0.0005)


class Runner:
    def __init__(self, bitfile, timeout=120.0):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        from pynq import Overlay, allocate, Clocks
        self.allocate, self.timeout, self.quarantined = allocate, timeout, []
        bitfile = Path(bitfile)
        if not bitfile.is_file() or not bitfile.with_suffix(".hwh").is_file():
            raise ValueError("matching .bit/.hwh files required")
        bit_hash = hashlib.sha256(bitfile.read_bytes()).hexdigest()
        hwh_hash = hashlib.sha256(bitfile.with_suffix(".hwh").read_bytes()).hexdigest()
        if bit_hash != BIT_SHA256 or hwh_hash != HWH_SHA256:
            raise ValueError("overlay hashes differ from the routed 200 MHz checkpoint")
        self.overlay = Overlay(str(bitfile), download=True)
        for name, expected in (("dma", "axi_dma"), ("srcnn", "srcnn_axis_dataflow_top")):
            if name not in self.overlay.ip_dict or expected not in self.overlay.ip_dict[name]["type"]:
                raise ValueError("wrong overlay IP identity: " + name)
        parameters = self.overlay.ip_dict["dma"]["parameters"]
        def param(name):
            return int(parameters[name], 0) if isinstance(parameters[name], str) else int(parameters[name])
        if param("C_INCLUDE_SG") != 0 or (1 << param("C_SG_LENGTH_WIDTH")) - 1 < FRAME_WORDS * 4:
            raise ValueError("requires simple DMA with >=260100-byte capacity")
        if param("C_M_AXIS_MM2S_TDATA_WIDTH") != 32 or param("C_S_AXIS_S2MM_TDATA_WIDTH") != 32:
            raise ValueError("requires 32-bit AXIS")
        self.clock_mhz = float(Clocks.fclk0_mhz)
        if abs(self.clock_mhz - 200) > 1:
            raise ValueError("PL0 clock differs from validated 200 MHz: %s" % self.clock_mhz)
        self.dma, self.kernel = self.overlay.dma.mmio, self.overlay.srcnn.mmio
        self.identity = {"bit_sha256": bit_hash, "hwh_sha256": hwh_hash,
                         "pl0_mhz": self.clock_mhz}

    def run(self, arrays):
        if self.quarantined:
            raise RuntimeError("previous transfer failed; reload overlay/reset PL before reusing retained buffers")
        buffers, quiescent = [], False
        begin = time.perf_counter()
        try:
            for count in (FRAME_WORDS, FRAME_WORDS, MODEL_WORDS):
                buffers.append(self.allocate(shape=(count,), dtype=np.uint32))
            source, destination, model = buffers
            source[:] = arrays["input"]
            model[:] = arrays["model"]
            destination[:] = 0xDEADBEEF
            for buffer in buffers:
                buffer.flush()
            reset_dma(self.dma)
            if not self.kernel.read(0) & 4:
                raise RuntimeError("SRCNN is not idle before start")
            self.kernel.write(0x10, int(model.physical_address) & 0xFFFFFFFF)
            self.kernel.write(0x14, int(model.physical_address) >> 32)
            # AXIS S2MM first; model address is not a dummy length register.
            transfer_begin = time.perf_counter()
            arm_dma(self.dma, 0x30, destination.physical_address, destination.nbytes)
            self.kernel.write(0, 1)
            arm_dma(self.dma, 0, source.physical_address, source.nbytes)
            wait_complete(self.dma, self.kernel, self.timeout)
            transfer_seconds = time.perf_counter() - transfer_begin
            quiescent = True
            destination.invalidate()
            output = np.asarray(destination).copy()
            mismatches = np.flatnonzero(output != arrays["expected"])
            if mismatches.size:
                first = int(mismatches[0])
                raise AssertionError("%d mismatches, first pixel %d: expected=%08x actual=%08x" %
                                     (mismatches.size, first, int(arrays["expected"][first]), int(output[first])))
            return {"status": "PASS", "words": FRAME_WORDS, "exact_match": True,
                    "transfer_start_to_done_s": transfer_seconds,
                    "host_allocate_to_compare_s": time.perf_counter() - begin,
                    "transfer_window_fps": 1 / transfer_seconds, "identity": self.identity,
                    "registers": snapshot(self.dma, self.kernel)}, output
        finally:
            if quiescent:
                for buffer in buffers:
                    buffer.freebuffer()
            else:
                # Reset the whole PL design, not merely DMA: a hung SRCNN could
                # still access model DDR. Only release allocations after reset.
                try:
                    self.overlay.download()
                    if not (self.kernel.read(0) & 4 and self.dma.read(4) & 1 and self.dma.read(0x34) & 1):
                        raise RuntimeError("overlay reload did not quiesce SRCNN/DMA")
                    for buffer in buffers:
                        buffer.freebuffer()
                except Exception:
                    self.quarantined.extend(buffers)
                    raise RuntimeError("PL reset failed; buffers retained. Reset/power-cycle board before releasing this runner")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bit", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="new result directory")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    if args.iterations < 1 or not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("iterations and timeout must be positive")
    args.out.mkdir(parents=True, exist_ok=False)
    results = {"status": "RUNNING", "runs": []}
    runner = None
    try:
        manifest, arrays = read_bundle(args.bundle)
        results["bundle"] = manifest
        runner = Runner(args.bit, args.timeout)
        for _ in range(args.iterations):
            result, output = runner.run(arrays)
            results["runs"].append(result)
            np.save(args.out / "output.npy", output, allow_pickle=False)
        results["status"] = "PASS"
    except Exception as error:
        results.update(status="FAIL", error=str(error))
        if runner is not None:
            results["registers"] = snapshot(runner.dma, runner.kernel)
        raise
    finally:
        (args.out / "board_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
