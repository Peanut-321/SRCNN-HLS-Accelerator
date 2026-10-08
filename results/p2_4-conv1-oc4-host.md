# P2.4 Conv1 OC4 throughput experiment — host checkpoint

Date: 2026-10-08  
Branch: `optimize/conv1-oc4-throughput`  
Parent tag: `hls-conv1-oc2-5ns` (`201cceb`)  
Code commit: `df055a7`  
Status: frozen; Mac host correctness and Vitis 5 ns synthesis complete

## Controlled change

The new top is:

```text
srcnn_hls_line_buffer_replicate_oc4_top
```

Only the existing Conv1 output-lane template parameter changes from two to
four. Four channels share each 9x9 window sample, with four independent
accumulators and four lane-partitioned weight banks. Each channel retains the
original bias-first, 81-product accumulation order. Conv2, Conv3, numeric
types, padding, activation, and interfaces are unchanged.

The scheduled Conv1 work per output pixel should change from:

```text
OC2: 32 groups * 81 kernel positions = 2592 grouped iterations
OC4: 16 groups * 81 kernel positions = 1296 grouped iterations
```

This is the second and final UNROLL factor permitted by the execution plan.
No OC8 sweep should start before board integration.

## Host correctness gate

```text
Release float build:       4/4 CTest PASS
Release host ap_fixed:     7/7 CTest PASS
ASan/UBSan float build:    4/4 CTest PASS
```

For replicate padding, OC4 is compared layer-by-layer with frozen OC2 on
13x17, 1x1, and 33x29 inputs. Float comparisons are bitwise and fixed-point
comparisons are exact for all three layers.

## Vitis 5 ns synthesis result

The OC4 top was synthesized with the frozen settings:

```text
Top: srcnn_hls_line_buffer_replicate_oc4_top
Part: xck26-sfvc784-2LV-c
Clock: 5 ns
CFLAGS: -std=c++14 -DSRCNN_HLS_FIXED_POINT=1
Component: srcnn_hls_conv1_oc4_5ns
```

| Metric | OC2 | OC4 | Change |
|---|---:|---:|---:|
| Top latency | 310,940,237 | 206,910,029 | -33.5% |
| Conv1 latency | 213,807,412 | 109,777,204 | -48.7% |
| Top slack | +0.02 ns | +0.05 ns | +0.03 ns |
| Conv1 slack | +0.02 ns | +0.17 ns | +0.15 ns |
| BRAM | 154 | 152 | -2 |
| DSP | 17 | 25 | +8 |
| LUT | 14,868 | 15,960 | +1,092 |
| FF | 7,786 | 8,229 | +443 |

Scheduling matches the intended architecture: the output-channel group loop
has trip count 16; the inner kernel loop has trip count 81 and II=1; four
parallel multiplier cores each use four DSPs, for 16 DSPs in the MAC pipeline.
MAC-loop slack is +0.17 ns and output-loop slack is +1.28 ns. Four independent
single-port `weights_by_lane` banks and four lane-separated `bias_by_lane`
banks were inferred.

At 5 ns, the complete HLS top estimate is approximately 1.035 seconds per
invocation, or 0.967 invocations/s. This is a kernel/top estimate, not a PYNQ
DMA end-to-end measurement. Compared with the MAC-A top's 457,505,951 cycles,
OC4 gives approximately 2.21x kernel-level speedup.

The raw report remains on the Windows tool machine at:

```text
C:\fpga\vitis-workspace\srcnn_hls_conv1_oc4_5ns\srcnn_hls_conv1_oc4_5ns\hls\syn\report\csynth.rpt
```

## Decision

OC4 is accepted as the current HLS throughput checkpoint. Stop Conv1 UNROLL
exploration; do not create OC8 before board integration. The overlay-specific
kernel budget and post-implementation timing remain open P0/P3 gates, and
board-level kernel-only/end-to-end timings must be measured separately.
