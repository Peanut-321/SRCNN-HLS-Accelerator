# P2.3 line-buffer host checkpoint

Date: 2026-10-08  
Branch: `optimize/line-buffer`  
Status: host correctness complete; original structure synthesized but failed
timing at 5 ns and 6 ns

## Scope

This checkpoint adds a second synthesizable entry point,
`srcnn_hls_line_buffer_top`, without replacing the frozen natural-loop
`srcnn_hls_top`.

- Conv1: nine circular row banks and a 9x9 shifted window.
- Conv2: direct 1x1 channel reduction.
- Conv3: five circular row banks per input channel and a 5x5 shifted window.
- Padding: valid, zero-same, and replicate-edge retain the existing contract.
- Arithmetic: existing per-layer accumulator types, bias-first ordering, ReLU,
  and narrowing helpers are reused unchanged.
- Pragmas: none. No PIPELINE, UNROLL, ARRAY_PARTITION, DATAFLOW, or AXI claim is
  made by this checkpoint.

## Verification

`tests/test_hls_line_buffer.cpp` compares every layer from the natural and
line-buffer tops for:

- replicate-edge 13x17;
- zero-same 13x17;
- valid 13x17;
- replicate-edge 1x1;
- replicate-edge 33x29 (non-square).

Float comparison is bitwise. Fixed-point comparison is exact. Deterministic
operands are binary-exact fractions so a mismatch identifies structure/order,
not decimal parsing noise.

Results:

```text
Release + host ap_fixed: 7/7 CTest PASS
ASan/UBSan float build:  4/4 CTest PASS
```

The first run failed at Conv1 flat index 40. The cause was an invalid physical
slice: storage declared `[channel][row-bank][column]` was passed to a loader as
if row-bank were the leading contiguous dimension. The declaration was changed
to `[row-bank][channel][column]`; the sanitizer and numerical suites then passed.

## Windows synthesis observation

The original circular-bank checkpoint was synthesized in Vitis 2026.1 under
the same part, CFLAGS, and no-user-pragma conditions as the natural baseline.
Vitis automatically enabled `syn.compile.pipeline_loops=64`; these results are
therefore automatic-pipelining exploration, not a hand-pipelined design.

| Top | Constraint | Slack | BRAM | LUT | FF | Result |
|---|---:|---:|---:|---:|---:|---|
| natural | 5 ns | +0.02 ns | 0 | 6,929 | 2,179 | pass, marginal |
| circular line buffer | 5 ns | -0.61 ns | 138 | 16,767 | 7,575 | fail |
| natural | 6 ns | +0.07 ns | 0 | 6,922 | 2,390 | pass, marginal |
| circular line buffer | 6 ns | -0.27 ns | 138 | 16,671 | 6,837 | fail |

The hierarchy report identifies the Conv1 line-buffer submodule as the timing
bottleneck; Conv3 has +0.08 ns slack at the 6 ns diagnostic point. The reported
top interval of 440,873,343 cycles is not evidence of end-to-end II=1 or FPS.
Raw report directories are not yet checked into this repository, so the table
records the reviewed console/report values supplied during the Windows run.

This result triggered the isolated Conv1 fixed-delay refactor on branch
`optimize/conv1-static-line-buffer`; see
`results/p2_3-conv1-static-line-buffer-host.md`.

## Evidence boundary

This is not a demonstrated performance improvement. The following remain
unresolved until the refactored branch is synthesized and the raw reports are
preserved:

- meaningful per-loop II, latency, and throughput interpretation;
- schedule/dependency and memory-port limitations;
- refactored DSP/LUT/FF/BRAM/URAM and timing;
- implemented clock after Vivado place-and-route;
- board throughput or speedup.

Before adding pragmas, synthesize both tops under the same part, clock, numeric
configuration, dimensions, and interface assumptions. Preserve both reports.
The checked-in Tcl/Make entry point accepts only `srcnn_hls_top` or
`srcnn_hls_line_buffer_top` through `SRCNN_HLS_TOP` and writes them into separate
`build-vitis/<top>` projects so the baseline report cannot be overwritten.
