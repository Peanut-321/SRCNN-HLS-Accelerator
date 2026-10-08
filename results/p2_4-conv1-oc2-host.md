# P2.4 Conv1 OC2 throughput experiment — host checkpoint

Date: 2026-10-08  
Branch: `optimize/conv1-oc2-throughput`  
Parent tag: `hls-mac-a-replicate-5ns` (`1965c5c`)  
Code commit: `d8c4849`  
Status: Mac host correctness complete; Vitis 5 ns / 6 ns synthesis pending

## Controlled change

The new top is:

```text
srcnn_hls_line_buffer_replicate_oc2_top
```

Only Conv1 output-channel parallelism changes:

- two output channels share each 9x9 window sample;
- each lane has an independent accumulator and weight bank;
- the two-lane MAC loop is explicitly unrolled;
- each output channel still accumulates its 81 products in the original
  kernel-row/kernel-column order;
- Conv2, Conv3, fixed-point types, rounding, saturation, padding semantics,
  input size arguments, and external pointer interfaces are unchanged.

The expected Conv1 inner iteration count per output pixel changes from
`64 * 9 * 9 = 5184` to `(64 / 2) * 9 * 9 = 2592`. This is a hypothesis until
the schedule report confirms the loop trip count and II.

## Host correctness gate

```text
Release float build:       4/4 CTest PASS
Release host ap_fixed:     7/7 CTest PASS
ASan/UBSan float build:    4/4 CTest PASS
```

For replicate padding, the OC2 top is compared layer-by-layer with the frozen
MAC-A top on 13x17, 1x1, and 33x29 inputs. Float comparisons are bitwise and
fixed-point comparisons are exact for Conv1, Conv2, and Conv3.

## Required Vitis gate

Synthesize only the OC2 top under the same settings as MAC-A:

```text
Top: srcnn_hls_line_buffer_replicate_oc2_top
Part: xck26-sfvc784-2LV-c
Clock points: 5 ns and 6 ns
CFLAGS: -std=c++14 -DSRCNN_HLS_FIXED_POINT=1
```

Suggested Windows commands from a Vitis HLS shell:

```text
git fetch origin
git switch optimize/conv1-oc2-throughput
git pull --ff-only
make vitis-export SRCNN_HLS_PART=xck26-sfvc784-2LV-c SRCNN_HLS_CLOCK_NS=5 SRCNN_HLS_TOP=srcnn_hls_line_buffer_replicate_oc2_top
```

Use a distinct 6 ns component/workspace rather than overwriting the 5 ns
report. Record:

- top and per-layer latency/interval;
- Conv1 grouped-MAC trip count, latency, and achieved II;
- top/Conv1/Conv2/Conv3 slack;
- BRAM, DSP, LUT, FF, and the inferred storage for `weights_by_lane`;
- any scheduling warning about memory ports or loop-carried dependencies.

## Decision gate

Accept OC2 as the new throughput checkpoint only if:

1. the grouped Conv1 MAC loop has trip count 2592 and II=1;
2. top latency falls materially relative to MAC-A's 457,505,951 cycles;
3. 5 ns timing still closes, or the exact new failing path is understood;
4. resource use remains below the overlay's kernel budget;
5. no arithmetic or interface contract changes were used to obtain the gain.

If II rises above 1, inspect the schedule/dependency and memory-port reports
before changing code. Do not add a second optimization in the same experiment.
