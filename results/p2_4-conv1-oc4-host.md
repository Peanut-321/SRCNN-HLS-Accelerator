# P2.4 Conv1 OC4 throughput experiment — host checkpoint

Date: 2026-10-08  
Branch: `optimize/conv1-oc4-throughput`  
Parent tag: `hls-conv1-oc2-5ns` (`201cceb`)  
Code commit: `df055a7`  
Status: Mac host correctness complete; Vitis 5 ns synthesis pending

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

## Required Vitis gate

```text
Top: srcnn_hls_line_buffer_replicate_oc4_top
Part: xck26-sfvc784-2LV-c
Clock: 5 ns
CFLAGS: -std=c++14 -DSRCNN_HLS_FIXED_POINT=1
Suggested component: srcnn_hls_conv1_oc4_5ns
```

Compare directly with the frozen OC2 report:

- output-channel group trip count should be 16;
- inner kernel trip count should remain 81 with II=1;
- the MAC body should contain four parallel multipliers;
- top and Conv1 latency/interval;
- top, Conv1 MAC, and output-loop slack;
- BRAM/DSP/LUT/FF and the four weight/bias bank bindings;
- memory-port, dependency, and timing warnings.

## Decision gate

OC4 is accepted only if it preserves II=1 and gives a material top-latency
reduction without exceeding the overlay-specific kernel budget. A negative
5 ns slack is not hidden by quoting estimated Fmax. If timing fails or the
speedup is small relative to its resource cost, keep OC2 as the implementation
candidate and retain OC4 only as the second design-space point.
