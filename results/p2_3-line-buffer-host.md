# P2.3 line-buffer host checkpoint

Date: 2026-10-08  
Branch: `optimize/line-buffer`  
Status: host correctness complete; Vitis synthesis not run

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

## Evidence boundary

This is not a performance result. The following remain `NOT MEASURED` until an
x86 Vitis machine is available:

- achieved/target II and latency;
- schedule/dependency and memory-port limitations;
- DSP/LUT/FF/BRAM/URAM;
- estimated and implemented clock;
- board throughput or speedup.

Before adding pragmas, synthesize both tops under the same part, clock, numeric
configuration, dimensions, and interface assumptions. Preserve both reports.
The checked-in Tcl/Make entry point accepts only `srcnn_hls_top` or
`srcnn_hls_line_buffer_top` through `SRCNN_HLS_TOP` and writes them into separate
`build-vitis/<top>` projects so the baseline report cannot be overwritten.
