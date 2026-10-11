"""Package a timing-passing local build and its matching board-test inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pynq"))
from aero_board_test import CHECKPOINTS


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
        "reset": {"c_ext_reset_high": 0},
        "srcnn": {"c_m_axi_model_mem_addr_width": 64},
    }.items():
        params = {p.get("NAME").lower(): p.get("VALUE")
                  for p in modules[name].findall("PARAMETERS/PARAMETER")}
        for key, value in required.items():
            if int(params[key], 0) != value:
                raise ValueError(f"Hardware parameter mismatch: {name}/{key}")


def validate_xsa(reports):
    with zipfile.ZipFile(reports / "srcnn_axis_255x255.xsa") as archive:
        bit_hash = sha256(reports / "srcnn_axis_255x255.bit")
        hwh_hash = sha256(reports / "srcnn_axis_255x255.hwh")
        for suffix, expected in ((".bit", bit_hash), (".hwh", hwh_hash)):
            if not any(hashlib.sha256(archive.read(name)).hexdigest() == expected
                       for name in archive.namelist() if name.endswith(suffix)):
                raise ValueError(f"XSA does not contain the standalone {suffix} artifact")


def notebook():
    sources = [
        ("markdown", "# SRCNN physical-board validation\n\nRun on the KV260, from this delivery directory. All saved outputs start empty.\n\nDo not run both formats at the same time. If a reset failure retains buffers, keep this kernel alive and reset/power-cycle the board before closing it."),
        ("code", "from pathlib import Path\nimport aero_board_test\n\nDELIVERY = Path.cwd()\n_, manifest, _, _ = aero_board_test.verify_delivery(DELIVERY)\nprint('Profile:', manifest['profile'])\nprint('No FPGA programming in this cell.')"),
        ("code", "# Set RUN_BOARD = True only when connected to the borrowed KV260.\nRUN_BOARD = False\n\nif RUN_BOARD:\n    from datetime import datetime, timezone\n    output_dir = DELIVERY / ('board_results_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'))\n    report = aero_board_test.run_board(DELIVERY, output_dir, iterations=10, timeout=120)\n    print('Status:', report['status'])\n    print('Benchmark:', report['benchmark'])\n    print('Saved:', output_dir)\nelse:\n    print('Board execution disabled; set RUN_BOARD = True when ready.')"),
    ]
    cells = []
    for kind, source in sources:
        cell = {"cell_type": kind, "id": hashlib.sha256(source.encode()).hexdigest()[:12],
                "metadata": {}, "source": source.splitlines(keepends=True)}
        if kind == "code":
            cell.update(execution_count=None, outputs=[])
        cells.append(cell)
    return {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python", "version": "3.10"}}, "nbformat": 4, "nbformat_minor": 5}


def package(profile, source, reports, ip, original, changed, destination):
    gate = validate_gate(reports)
    validate_hwh(reports / "srcnn_axis_255x255.hwh")
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
    for name in ("srcnn_axis_255x255.bit", "srcnn_axis_255x255.hwh", "srcnn_axis_255x255.xsa"):
        shutil.copy2(reports / name, destination / name)
    for name in ("srcnn_axis_host.py", "srcnn_q20_12_bundle.py"):
        if name == "srcnn_q20_12_bundle.py" and profile != "q20_12":
            continue
        shutil.copy2(source / "pynq" / name, destination / name)
    shutil.copy2(ROOT / "pynq" / "aero_board_test.py", destination / "aero_board_test.py")
    shutil.copytree(original, destination / "butterfly")
    shutil.copytree(changed, destination / "changed")
    report_dir = destination / "build_reports"
    report_dir.mkdir()
    shutil.copy2(provenance_path, report_dir / "hls_source_manifest.json")
    for name in ("implementation_gate.txt", "integration_config.txt", "post_route_timing.rpt",
                 "post_route_utilization.rpt", "post_route_drc.rpt", "post_route_methodology.rpt",
                 "check_timing.rpt", "srcnn_system_bd.tcl"):
        shutil.copy2(reports / name, report_dir / name)
    (destination / "ip").mkdir()
    shutil.copy2(ip, destination / "ip" / ip.name)
    (destination / "SRCNN_board_test.ipynb").write_text(json.dumps(notebook(), indent=2), encoding="utf-8")
    text = f"""# {profile} local SRCNN board delivery

Build: routed timing/DRC and bitstream gates passed. Physical board validation
is PENDING. Source: {revision}.

Upload/extract this entire directory inside your board Project directory.
Keep it separate from the other format and from the dummy overlay.
Open SRCNN_board_test.ipynb: run the inspection cell first. Only then enable
RUN_BOARD in the next cell. The default is false and programs no FPGA.

Each run checks all 65,025 output words. It tests warmup, ten repeated frames,
changed input/model, original-model restoration and overlay reload. Results
are written to a new directory. Benchmark includes model loading and DMA,
not pure kernel latency. Ten samples are a preliminary benchmark, not a
large statistical study. The changed case is a synthetic restart test,
not another official dataset image.

Only one notebook/kernel may use the PL hardware at a time. Finish and close
the first format's kernel before programming the other. On transfer failure,
do not continue blindly. If buffers are retained, keep the kernel alive and
reset/power-cycle the board before closing it. Do not uninstall or update PYNQ.

Offline inspection (no board required):
python aero_board_test.py

Hardware results must not be labelled PASS before physical execution.
"""
    (destination / "README.md").write_text(text, encoding="utf-8")
    files = {str(path.relative_to(destination)).replace("\\", "/"): sha256(path)
             for path in sorted(destination.rglob("*")) if path.is_file()}
    manifest = {"schema": "AERO_SRCNN_LOCAL_DELIVERY_V1", "profile": profile,
                "source_commit": revision, "build_gate": "ROUTED_TIMING_DRC_BITSTREAM_PASS",
                "board_gate": "PENDING", "timing": gate, "files": files}
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
