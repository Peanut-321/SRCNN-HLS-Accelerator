# P2.3 Conv1 fixed-delay line-buffer checkpoint

Date: 2026-10-08  
Branch: `optimize/conv1-static-line-buffer`  
Code commit: `936ecd6`  
Status: Mac host correctness complete; Vitis re-synthesis pending

## Why this checkpoint exists

The first line-buffer structure used nine circular row banks for Conv1 and
selected a physical bank at runtime with `head + kernel_row`. At 6 ns it used
138 BRAM overall and failed timing by 0.27 ns; the hierarchy report placed the
critical path in Conv1. Relaxing the clock again would not remove that path.

## Structural change

Only Conv1 changed:

- one padded raster sample enters per structural iteration;
- eight fixed row-delay banks hold the previous eight raster rows;
- every bank has a permanent delay role, so there is no circular `head` and no
  runtime row-bank selector;
- nine vertical taps feed a 9x9 horizontal shift window;
- output computation starts only after the 9x9 window is warm;
- valid, zero-same, and replicate-edge modes remain supported;
- zero-same still skips invalid MAC terms instead of multiplying by zero, which
  preserves the frozen binary32 operation sequence and signed-zero behaviour.

The natural baseline, Conv2, Conv3, numeric typedefs, accumulator derivation,
bias-first order, ReLU placement, and narrowing helpers were not changed. No
HLS pragma was added.

## Host verification

The line-buffer regression gained a `zero_1x1` boundary case in addition to
replicate 13x17, zero 13x17, valid 13x17, replicate 1x1, and replicate 33x29.

```text
Float build:              4/4 CTest PASS
Host ap_fixed build:      7/7 CTest PASS
ASan/UBSan float build:   4/4 CTest PASS
```

For the structural comparison, float outputs are bitwise equal and fixed-point
outputs are exactly equal to the natural top at Conv1, Conv2, and Conv3.

## Required Vitis gate

Re-run `srcnn_hls_line_buffer_top` at the existing 6 ns diagnostic constraint
with the same part and CFLAGS. Compare against the already recorded 6 ns
circular checkpoint, focusing on:

- Conv1 hierarchy slack and critical path;
- top-level slack;
- Conv1 and total BRAM/LUT/FF/DSP;
- inferred memory instances and port conflicts;
- schedule/dependency report and automatically pipelined loops;
- latency/interval fields, without interpreting the top interval as II=1.

If timing still fails, inspect the new schedule and memory binding before any
pragma is added. The next change must respond to report evidence rather than
another clock relaxation.
