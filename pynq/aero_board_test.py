"""Validate a locally built SRCNN delivery before optional physical board tests.

CLI: read-only offline inspection. run_board() is an explicit FPGA programming
operation used from a persistent notebook. Keep that kernel alive on reset failure.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import xml.etree.ElementTree as ET

import numpy as np


CHECKPOINTS = {
    "q24_8": "5f0216704cdd7ba70e2c8a493469c2df97e32259",
    "q20_12": "18281e76b9070b6801620a8548c7ae8b72f47db5",
}
# Retain failed runners in a notebook until PL has been safely reset.
ACTIVE_RUNNERS = []
PREFLIGHT_OVERLAY = None


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_reset_tieoffs(modules):
    """Fail closed on a reset controller tied permanently active."""
    reset = modules.get("reset")
    if reset is None:
        raise ValueError("Missing reset controller")
    params = {p.get("NAME").lower(): p.get("VALUE")
              for p in reset.findall("PARAMETERS/PARAMETER")}
    for name in ("c_ext_reset_high", "c_aux_reset_high"):
        if int(params.get(name, "-1"), 0) != 0:
            raise ValueError(f"Unexpected reset polarity: {name}")
    for port_name, required_value in (("aux_reset_in", 1), ("dcm_locked", 1),
                                      ("mb_debug_sys_rst", 0)):
        port = reset.find(f"PORTS/PORT[@NAME='{port_name}']")
        connections = [] if port is None else port.findall("CONNECTIONS/CONNECTION")
        if len(connections) != 1:
            raise ValueError(f"Reset tie-off is missing or ambiguous: {port_name}")
        driver = modules.get(connections[0].get("INSTANCE"))
        value = None if driver is None else driver.find("PARAMETERS/PARAMETER[@NAME='CONST_VAL']")
        if (driver is None or driver.get("MODTYPE") != "xlconstant" or
                connections[0].get("PORT") != "dout" or value is None or
                int(value.get("VALUE"), 0) != required_value):
            raise ValueError(f"Unsafe reset tie-off: {port_name}; expected constant {required_value}")


def verify_delivery(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "delivery_manifest.json").read_text(encoding="utf-8"))
    profile = manifest.get("profile")
    if (manifest.get("schema") != "AERO_SRCNN_LOCAL_DELIVERY_V1"
            or profile not in CHECKPOINTS
            or manifest.get("source_commit") != CHECKPOINTS[profile]
            or manifest.get("build_gate") != "ROUTED_TIMING_DRC_BITSTREAM_PASS"):
        raise ValueError("Unapproved delivery provenance or build gate")
    for relative, expected_hash in manifest["files"].items():
        path = (directory / relative).resolve()
        if not path.is_relative_to(directory) or not path.is_file():
            raise ValueError(f"Missing or unsafe delivery file: {relative}")
        if sha256(path) != expected_hash:
            raise ValueError(f"Delivery checksum mismatch: {relative}")
    required = {"srcnn_axis_255x255.bit", "srcnn_axis_255x255.hwh",
                "srcnn_axis_host.py", "aero_board_test.py"}
    for case in ("butterfly", "changed"):
        required.update(f"{case}/{name}" for name in
                        ("manifest.json", "input.npy", "model.npy", "expected.npy"))
    if profile == "q20_12":
        required.add("srcnn_q20_12_bundle.py")
    if not required <= set(manifest["files"]):
        raise ValueError("Incomplete delivery manifest")
    if (directory / "srcnn_axis_255x255.xsa").exists():
        raise ValueError("Move runtime sibling XSA into build_reports before using PYNQ")
    root = ET.parse(directory / "srcnn_axis_255x255.hwh").getroot()
    validate_reset_tieoffs({m.get("INSTANCE"): m for m in root.findall("MODULES/MODULE")})
    sys.path.insert(0, str(directory))
    import srcnn_axis_host as host
    if Path(host.__file__).resolve() != directory / "srcnn_axis_host.py":
        raise ValueError("Restart the kernel before switching delivery directories")
    if profile == "q20_12":
        import srcnn_q20_12_bundle as codec
        if Path(codec.__file__).resolve() != directory / "srcnn_q20_12_bundle.py":
            raise ValueError("Wrong Q20.12 bundle reader")
        reader = codec.read_bundle
    else:
        reader = host.read_bundle
    cases = {name: reader(directory / name) for name in ("butterfly", "changed")}
    if (np.array_equal(cases["butterfly"][1]["input"], cases["changed"][1]["input"])
            or np.array_equal(cases["butterfly"][1]["model"], cases["changed"][1]["model"])
            or np.array_equal(cases["butterfly"][1]["expected"], cases["changed"][1]["expected"])):
        raise ValueError("Changed case must change input, model and expected output")
    # Bind the upstream runner to this recorded local build, never bypass hashes.
    host.BIT_SHA256 = manifest["files"]["srcnn_axis_255x255.bit"]
    host.HWH_SHA256 = manifest["files"]["srcnn_axis_255x255.hwh"]
    print(f"PASS: Offline package inspection ({profile}); no FPGA programming.")
    return directory, manifest, host, cases


def preflight_board(directory):
    """Explicit programming and control-path check; no DMA or inference starts.

    Python timeouts cannot recover a hard AXI bus stall. Do not repeat a stuck
    preflight in another kernel; recover the board and inspect its configuration.
    """
    global PREFLIGHT_OVERLAY
    directory, manifest, _, _ = verify_delivery(directory)
    if manifest.get("deployment_revision") != "HPM1_HPC0_B000_B001_RESETFIX_V3":
        raise ValueError("Preflight requires the corrected HPM1 delivery")
    from pynq import Overlay, MMIO, Clocks
    print("STAGE 1: Parse metadata; no programming yet", flush=True)
    overlay = Overlay(str(directory / "srcnn_axis_255x255.bit"), download=False)
    for name, expected in (("dma", 0xB0000000), ("srcnn", 0xB0010000)):
        if overlay.ip_dict[name]["phys_addr"] != expected:
            raise ValueError(f"Wrong control address for {name}")
    print("STAGE 2: Download verified bitstream", flush=True)
    overlay.download()
    PREFLIGHT_OVERLAY = overlay
    if not overlay.is_loaded() or abs(float(Clocks.fclk0_mhz) - 200) > 1:
        raise ValueError("Overlay load or PL0 clock check failed")
    values = {}
    for name in ("dma", "srcnn"):
        info = overlay.ip_dict[name]
        print(f"STAGE 3: Map {name} at {info['phys_addr']:#x}", flush=True)
        mmio = MMIO(info["phys_addr"], info["addr_range"], device=overlay.device)
        print(f"STAGE 4: Read {name} status", flush=True)
        values[name] = int(mmio.read(0x04 if name == "dma" else 0x00))
        print(f"{name} status: {values[name]:#x}", flush=True)
    if not values["srcnn"] & 4 or not values["dma"] & 1:
        raise RuntimeError("Fresh overlay is not idle with DMA halted; do not start inference")
    print("PASS: Control path only; inference has NOT been validated", flush=True)
    return values


def run_board(directory, out, iterations=3, timeout=120):
    if iterations < 1 or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Iterations and timeout must be positive")
    directory, manifest, host, cases = verify_delivery(directory)
    if manifest.get("deployment_revision") != "HPM1_HPC0_B000_B001_RESETFIX_V3":
        raise ValueError("Old deployment is not approved for physical execution")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    report = {"status": "RUNNING", "profile": manifest["profile"],
              "source_commit": manifest["source_commit"], "runs": [],
              "measurement": "Host-observed transfer-start-to-done, including model loading and DMA",
              "not_kernel_only": True, "warmup_transfers": 1}
    runner = None
    try:
        runner = host.Runner(directory / "srcnn_axis_255x255.bit", timeout)
        ACTIVE_RUNNERS.append(runner)
        # Same kernel instance across all these frames. DMA is reset per frame;
        # SRCNN is not reset between warmup, changed-model and restored-model runs.
        schedule = [("warmup", "butterfly")]
        schedule += [("repeat", "butterfly")] * iterations
        schedule += [("changed", "changed"), ("restored", "butterfly")]
        for index, (phase, case) in enumerate(schedule):
            result, output = runner.run(cases[case][1])
            result.update(index=index, phase=phase, case=case)
            report["runs"].append(result)
            np.save(out / f"output_{index:03d}_{phase}.npy", output, allow_pickle=False)
            print(f"PASS: {phase} frame, all 65,025 words match; "
                  f"transfer={result['transfer_start_to_done_s']:.6f} s")
        # Reload uses another Runner and the same validated artifact hashes.
        ACTIVE_RUNNERS.remove(runner)
        runner = host.Runner(directory / "srcnn_axis_255x255.bit", timeout)
        ACTIVE_RUNNERS.append(runner)
        result, output = runner.run(cases["butterfly"][1])
        result.update(index=len(schedule), phase="reload", case="butterfly")
        report["runs"].append(result)
        np.save(out / "output_reload.npy", output, allow_pickle=False)
        samples = [r["transfer_start_to_done_s"] for r in report["runs"] if r["phase"] == "repeat"]
        report["benchmark"] = {"measured_frames": len(samples),
                               "median_transfer_seconds": statistics.median(samples),
                               "p95_transfer_seconds": float(np.percentile(samples, 95)),
                               "median_transfer_window_fps": 1 / statistics.median(samples)}
        report["status"] = "PASS"
        ACTIVE_RUNNERS.remove(runner)
        print("PASS: Repeat, changed input/model, restore and overlay-reload tests.")
    except Exception as error:
        report.update(status="FAIL", error=str(error))
        if runner is not None:
            report["buffers_retained"] = len(runner.quarantined)
            if not runner.quarantined and runner in ACTIVE_RUNNERS:
                ACTIVE_RUNNERS.remove(runner)
        raise
    finally:
        (out / "board_results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delivery", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    verify_delivery(args.delivery)


if __name__ == "__main__":
    main()
