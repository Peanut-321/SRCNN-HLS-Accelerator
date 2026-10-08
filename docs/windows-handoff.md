# Windows / Vitis handoff

Last updated: 2026-10-08

## Repository state

- Repository: `https://github.com/Peanut-321/SRCNN-HLS-Accelerator`
- Active branch: `optimize/line-buffer`
- Frozen baseline tag: `hls-functional-baseline-p2.2a`
- Baseline commit: `3f8d285` (`Save verified HLS functional baseline`)
- Line-buffer implementation commit: `f0662e5`

`main` remains the unoptimized functional baseline. Do not merge the active
branch until Vitis synthesis evidence has been reviewed.

## Completed work

- Frozen sequential float32 Golden Reference and independent oracle.
- Dual-target float / `ap_fixed` HLS arithmetic skeleton.
- Fixed-vs-float error harness for five frozen random vector sets.
- Natural-loop synthesizable top: `srcnn_hls_top`.
- Experimental structural top: `srcnn_hls_line_buffer_top`.
- Conv1/Conv3 use circular row banks and shifted windows in the experimental
  top; Conv2 remains a direct 1x1 channel reduction.
- Release + host `ap_fixed`: 7/7 CTest PASS.
- ASan/UBSan float build: 4/4 CTest PASS.
- Float natural-vs-line-buffer comparison is bitwise exact; fixed comparison
  is exact on replicate-edge, zero-same, valid, 1x1, and 33x29 cases.

No `PIPELINE`, `UNROLL`, `ARRAY_PARTITION`, `DATAFLOW`, or AXI interface pragma
has been added. Latency, II, clock, and FPGA resources are `NOT MEASURED`.

## Windows checkout

Use a short local path outside OneDrive:

```powershell
cd C:\
mkdir fpga
cd fpga
git clone --recurse-submodules https://github.com/Peanut-321/SRCNN-HLS-Accelerator.git
cd SRCNN-HLS-Accelerator
git switch optimize/line-buffer
git submodule update --init --recursive
git log -2 --oneline
```

## Immediate objective

Run two Vitis HLS syntheses under the same exact device part and clock:

1. natural baseline: `srcnn_hls_top`;
2. line-buffer checkpoint: `srcnn_hls_line_buffer_top`.

First record:

```powershell
vitis_hls -version
vivado -version
git --version
```

Then, after confirming the exact KV260/K26 part and target clock:

```powershell
$env:SRCNN_HLS_PART = "<confirmed-exact-part>"
$env:SRCNN_HLS_CLOCK_NS = "<confirmed-target-period-ns>"
$env:SRCNN_HLS_TOP = "srcnn_hls_top"
vitis_hls -f .\hls\scripts\run_hls.tcl

$env:SRCNN_HLS_TOP = "srcnn_hls_line_buffer_top"
vitis_hls -f .\hls\scripts\run_hls.tcl
```

The two projects are kept separate:

```text
build-vitis/srcnn_hls_top/
build-vitis/srcnn_hls_line_buffer_top/
```

## Evidence to preserve

For both tops, retain:

- complete `solution1/syn/report/` directory;
- `vitis_hls.log`;
- target part and clock;
- tool versions;
- latency min/max and interval/II;
- estimated clock;
- DSP, LUT, FF, BRAM, and URAM;
- schedule/dependency/memory-port warnings;
- exact failure log if synthesis or export fails.

Do not add pragmas or rewrite loops before reviewing these reports. A failed
synthesis is evidence: preserve the exact error rather than guessing a fix.

## Documents to read

1. `docs/windows-handoff.md` (this file)
2. `results/p2_3-line-buffer-host.md`
3. `docs/versioning-and-optimization.md`
4. `plan.md`, especially P0, P2.2, and P2.3
5. `spec.md` for the frozen functional contract

Formal weights/course images are not currently present in the repository, so
P2.2b deployment numeric freeze remains open.
