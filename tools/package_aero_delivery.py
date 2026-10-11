"""Package a timing-passing local build and its matching board-test inputs."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pynq"))
from aero_board_test import CHECKPOINTS, validate_reset_tieoffs


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_gate(reports):
    console = (reports / "console-all.log").read_text(encoding="utf-8", errors="replace")
    # Tcl source echo also contains gate strings; require executed standalone lines.
    if not any(line.strip() == "GATE_BITSTREAM_PASS" for line in console.splitlines()):
        raise ValueError("No completed bitstream gate; do not package an unfinished build")
    gate = {}
    for line in (reports / "implementation_gate.txt").read_text().splitlines():
        key, _, value = line.partition(" ")
        gate[key] = value
    if (float(gate["WNS"]) < 0 or float(gate["WHS"]) < 0
            or int(gate["DRC_BLOCKERS"]) != 0):
        raise ValueError("Timing or DRC did not pass")
    return gate


def validate_hwh(path):
    root = ET.parse(path).getroot()
    info = root.find("SYSTEMINFO")
    if info is None or info.get("DEVICE") != "xck26":
        raise ValueError("Not a K26 hardware handoff")
    modules = {module.get("INSTANCE"): module for module in root.findall("MODULES/MODULE")}
    if "srcnn" not in modules or modules["srcnn"].get("MODTYPE") != "srcnn_axis_dataflow_top":
        raise ValueError("Wrong SRCNN deployment top in hardware handoff")
    for name, required in {
        "dma": {"c_include_sg": 0, "c_sg_length_width": 26, "c_addr_width": 64,
                "c_m_axis_mm2s_tdata_width": 32, "c_s_axis_s2mm_tdata_width": 32},
        "reset": {"c_ext_reset_high": 0, "c_aux_reset_high": 0},
        "srcnn": {"c_m_axi_model_mem_addr_width": 64},
        "ps": {"psu__use__m_axi_gp0": 0, "psu__use__m_axi_gp1": 1,
               "psu__use__s_axi_gp0": 1, "psu__use__s_axi_gp2": 0,
               "psu__saxigp0__data_width": 128},
    }.items():
        params = {p.get("NAME").lower(): p.get("VALUE")
                  for p in modules[name].findall("PARAMETERS/PARAMETER")}
        for key, value in required.items():
            if int(params[key], 0) != value:
                raise ValueError(f"Hardware parameter mismatch: {name}/{key}")
    # Validate the generated wiring, not just reset parameters. The v2 build
    # passed timing while keeping an active-low auxiliary reset asserted.
    validate_reset_tieoffs(modules)
    ranges = modules["ps"].findall("MEMORYMAP/MEMRANGE")
    for instance, address in (("dma", 0xB0000000), ("srcnn", 0xB0010000)):
        if not any(r.get("INSTANCE") == instance
                   and int(r.get("BASEVALUE", "0"), 0) == address
                   and r.get("MASTERBUSINTERFACE") == "M_AXI_HPM1_FPD"
                   for r in ranges):
            raise ValueError(f"Unvalidated control route/address: {instance}")
    for name in ("dma", "srcnn"):
        memory_ranges = modules[name].findall("MEMORYMAP/MEMRANGE")
        ddr = [r for r in memory_ranges if r.get("MEMTYPE") == "MEMORY"]
        if not ddr or any(r.get("SLAVEBUSINTERFACE") != "S_AXI_HPC0_FPD" for r in ddr):
            raise ValueError(f"Unvalidated DDR route: {name}")


def validate_constraints(reports):
    text = (reports / 'check_timing.rpt').read_text(encoding='utf-8', errors='replace')
    for check in ('no_clock', 'unconstrained_internal_endpoints', 'multiple_clock',
                  'generated_clocks', 'loops', 'latch_loops'):
        matches = re.findall(r'checking ' + check + r' \((\d+)\)', text)
        if not matches or any(int(count) for count in matches):
            raise ValueError(f'Timing constraint coverage failed: {check}')


def validate_xsa(reports):
    with zipfile.ZipFile(reports / "srcnn_axis_255x255.xsa") as archive:
        bit_hash = sha256(reports / "srcnn_axis_255x255.bit")
        hwh_hash = sha256(reports / "srcnn_axis_255x255.hwh")
        for suffix, expected in ((".bit", bit_hash), (".hwh", hwh_hash)):
            if not any(hashlib.sha256(archive.read(name)).hexdigest() == expected
                       for name in archive.namelist() if name.endswith(suffix)):
                raise ValueError(f"XSA does not contain the standalone {suffix} artifact")


def validate_reset_sim(reports):
    text = (reports / "reset_simulation.log").read_text(encoding="utf-8", errors="replace")
    if not any(line.strip() == "RESET_TIEOFF_PASS: aux=0 holds AXI reset; aux=1 releases AXI reset"
               for line in text.splitlines()):
        raise ValueError("Missing executed reset-release simulation gate")
    if "Fatal:" in text or "ERROR:" in text:
        raise ValueError("Reset-release simulation contains an error")


def notebook():
    sources = [
        ("markdown", "# SRCNN physical-board validation\n\nRun on the KV260, from this delivery directory. All saved outputs start empty.\n\nDo not run both formats at the same time. If a reset failure retains buffers, keep this kernel alive and reset/power-cycle the board before closing it."),
        ("code", "from pathlib import Path\nimport aero_board_test\n\nDELIVERY = Path.cwd()\n_, manifest, _, _ = aero_board_test.verify_delivery(DELIVERY)\nprint('Profile:', manifest['profile'])\nprint('No FPGA programming in this cell.')"),
        ("code", "# Set RUN_BOARD = True only when connected to the borrowed KV260.\nRUN_BOARD = False\n\nif RUN_BOARD:\n    from datetime import datetime, timezone\n    output_dir = DELIVERY / ('board_results_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'))\n    report = aero_board_test.run_board(DELIVERY, output_dir, iterations=10, timeout=120)\n    print('Status:', report['status'])\n    print('Benchmark:', report['benchmark'])\n    print('Saved:', output_dir)\nelse:\n    print('Board execution disabled; set RUN_BOARD = True when ready.')"),
    ]
    sources.insert(2, ("code", "# Explicitly programs FPGA, but starts no inference or DMA.\nRUN_PREFLIGHT = False\nPREFLIGHT_OK = False\nif RUN_PREFLIGHT:\n    control_status = aero_board_test.preflight_board(DELIVERY)\n    PREFLIGHT_OK = True\nelse:\n    print('Set RUN_PREFLIGHT = True only when the board is ready.')"))
    kind, source = sources[-1]
    sources[-1] = (kind, source.replace("if RUN_BOARD:\n", "if RUN_BOARD:\n    if not PREFLIGHT_OK:\n        raise RuntimeError('Complete the control-path preflight first')\n"))
    cells = []
    for kind, source in sources:
        cell = {"cell_type": kind, "id": hashlib.sha256(source.encode()).hexdigest()[:12],
                "metadata": {}, "source": source.splitlines(keepends=True)}
        if kind == "code":
            cell.update(execution_count=None, outputs=[])
        cells.append(cell)
    return {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python", "version": "3.10"}}, "nbformat": 4, "nbformat_minor": 5}


def delivery_hashes(destination):
    # The notebook is user-editable UI, not trusted executable input to the runner.
    # Hardware, runner code, reference data and reports remain hash-protected.
    return {str(path.relative_to(destination)).replace("\\", "/"): sha256(path)
            for path in sorted(destination.rglob("*")) if path.is_file()
            and path.name not in ("SRCNN_board_test.ipynb", "delivery_manifest.json")}


def package(profile, source, reports, ip, original, changed, destination):
    gate = validate_gate(reports)
    validate_constraints(reports)
    validate_hwh(reports / "srcnn_axis_255x255.hwh")
    validate_reset_sim(reports)
    validate_xsa(reports)
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if revision != CHECKPOINTS[profile]:
        raise ValueError("Source checkout is not the approved checkpoint")
    provenance_path = ip.parents[3] / "source-manifest.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8-sig"))
    if provenance.get("revision", provenance.get("commit")) != revision:
        raise ValueError("HLS source provenance does not match the checkout")
    flags = provenance.get("numeric_flags", provenance.get("flags", ""))
    if "SRCNN_HLS_FIXED_POINT=1" not in flags:
        raise ValueError("HLS export is not a fixed-point build")
    is_q20 = "SRCNN_HLS_OFFICIAL_Q20_12=1" in flags
    if is_q20 != (profile == "q20_12"):
        raise ValueError("HLS numerical profile differs from requested delivery")
    for record in provenance["source_hashes"]:
        path = Path(record["path"])
        if not path.is_absolute():
            path = source / path
        if sha256(path) != record["sha256"].lower():
            raise ValueError(f"Source changed since HLS synthesis: {path}")
    if destination.exists() or destination.with_suffix(".zip").exists():
        raise ValueError("Use a new destination; existing deliveries are not overwritten")
    destination.mkdir(parents=True, exist_ok=False)
    for name in ("srcnn_axis_255x255.bit", "srcnn_axis_255x255.hwh"):
        shutil.copy2(reports / name, destination / name)
    for name in ("srcnn_axis_host.py", "srcnn_q20_12_bundle.py"):
        if name == "srcnn_q20_12_bundle.py" and profile != "q20_12":
            continue
        runtime_source = (ROOT / "pynq" / "aero_srcnn_axis_host.py"
                          if name == "srcnn_axis_host.py" else source / "pynq" / name)
        shutil.copy2(runtime_source, destination / name)
    shutil.copy2(ROOT / "pynq" / "aero_board_test.py", destination / "aero_board_test.py")
    shutil.copytree(original, destination / "butterfly")
    shutil.copytree(changed, destination / "changed")
    report_dir = destination / "build_reports"
    report_dir.mkdir()
    # PYNQ 3.0.1 mistakes a same-stem sibling XSA for runtime metadata.
    # Archive XSA away from the runtime BIT/HWH pair, without monkeypatching PYNQ.
    shutil.copy2(reports / "srcnn_axis_255x255.xsa", report_dir / "srcnn_axis_255x255.xsa")
    shutil.copy2(provenance_path, report_dir / "hls_source_manifest.json")
    shutil.copy2(source / "pynq" / "srcnn_axis_host.py", report_dir / "upstream_srcnn_axis_host.py")
    for name in ("implementation_gate.txt", "integration_config.txt", "post_route_timing.rpt",
                 "post_route_utilization.rpt", "post_route_drc.rpt", "post_route_methodology.rpt",
                 "check_timing.rpt", "srcnn_system_bd.tcl"):
        shutil.copy2(reports / name, report_dir / name)
    shutil.copy2(reports / "reset_simulation.log", report_dir / "reset_simulation.log")
    shutil.copy2(ROOT / "results" / "aero-reset-audit.md", report_dir / "reset_audit.md")
    shutil.copy2(ROOT / "tests" / "aero_reset_tb.v", report_dir / "reset_testbench.v")
    (destination / "ip").mkdir()
    shutil.copy2(ip, destination / "ip" / ip.name)
    (destination / "SRCNN_board_test.ipynb").write_text(json.dumps(notebook(), indent=2), encoding="utf-8")
    text = f"""# {profile} local SRCNN board delivery

Build: routed timing/DRC and bitstream gates passed. Physical board validation
is PENDING. Source: {revision}.

Revision V3 fixes the permanently asserted auxiliary reset in V2.
Generated HWH wiring is checked and reset-release simulation must pass.
Do not execute or merge files from V2. Physical inference is still PENDING.

Upload/extract this entire directory inside your board Project directory.
Keep it separate from the other format and from the dummy overlay.
Open SRCNN_board_test.ipynb: inspect first, then enable RUN_PREFLIGHT and run
the control-path check. Only after that passes enable RUN_BOARD for inference.
Both switches default to false. Never run old notebooks or compatibility patches.
The notebook is editable; all runtime Python, hardware and reference files
remain protected by the manifest. XSA is archived under build_reports, not
beside the runtime BIT/HWH pair (PYNQ 3.0.1 compatibility).

Each run checks all 65,025 output words. It tests warmup, ten repeated frames,
changed input/model, original-model restoration and overlay reload. Results
are written to a new directory. Benchmark includes model loading and DMA,
not pure kernel latency. Ten samples are a preliminary benchmark, not a
large statistical study. The changed case is a synthetic restart test,
not another official dataset image.

Use a fresh directory for this revision: HPM1/HPC0 at B0000000/B0010000.
Do not merge these files into the old HPM0 directory, which may retain XSA.
Runtime uses direct MMIO polling; the original upstream host is preserved
under build_reports for provenance, and is NOT the executable runtime.

Only one notebook/kernel may use the PL hardware at a time. Finish and close
the first format's kernel before programming the other. On transfer failure,
do not continue blindly. If buffers are retained, keep the kernel alive and
reset/power-cycle the board before closing it. Do not uninstall or update PYNQ.

Offline inspection (no board required):
python aero_board_test.py

Hardware results must not be labelled PASS before physical execution.
"""
    (destination / "README.md").write_text(text, encoding="utf-8")
    files = delivery_hashes(destination)
    manifest = {"schema": "AERO_SRCNN_LOCAL_DELIVERY_V1", "profile": profile,
                "source_commit": revision, "build_gate": "ROUTED_TIMING_DRC_BITSTREAM_PASS",
                "board_gate": "PENDING", "timing": gate, "files": files}
    manifest["deployment_revision"] = "HPM1_HPC0_B000_B001_RESETFIX_V3"
    manifest["mutable_files"] = ["SRCNN_board_test.ipynb"]
    (destination / "delivery_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    # Use a fresh Python process to avoid mixing same-named modules from two profiles.
    subprocess.run([sys.executable, "-B", str(destination / "aero_board_test.py")], check=True)
    with zipfile.ZipFile(destination.with_suffix(".zip"), "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(destination.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(destination.parent))
    print(f"PASS: Delivery ready for physical board testing: {destination}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=tuple(CHECKPOINTS), required=True)
    for key in ("source", "reports", "ip", "original", "changed", "destination"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    package(args.profile, args.source, args.reports, args.ip, args.original, args.changed, args.destination)


if __name__ == "__main__":
    main()
