# P2.4 Conv1 OC2 incremental writeback — host checkpoint

Date: 2026-10-08  
Branch: `optimize/conv1-oc2-writeback-address`  
Parent tag: `hls-conv1-oc2-5ns` (`201cceb`)  
Code commit: `a7b41d3`  
Status: closed with no measurable synthesis benefit; do not promote over OC2

## Controlled change

The new top is:

```text
srcnn_hls_line_buffer_replicate_oc2_writeback_top
```

The frozen OC2 top computes every CHW output address through:

```text
(output_channel * output_height + output_row) * output_width + output_column
```

The experimental top instead computes once per output pixel:

```text
output_plane_size = output_height * output_width
next_output_index = output_row * output_width + output_column
```

After each channel write, it advances:

```text
next_output_index += output_plane_size
```

This preserves CHW order while removing repeated channel/height address
products from the two-element output loop. A compile-time template parameter
keeps the original OC2 top available as a control from the same source.

No MAC, accumulator, fixed-point, padding, activation, Conv2, Conv3, or
interface behavior changes. OC4 is deliberately not part of this experiment.

## Host correctness gate

```text
Release float build:       4/4 CTest PASS
Release host ap_fixed:     7/7 CTest PASS
ASan/UBSan float build:    4/4 CTest PASS
```

For replicate padding, the writeback top is compared layer-by-layer with the
frozen OC2 top on 13x17, 1x1, and 33x29 inputs. Float comparisons are bitwise
and fixed-point comparisons are exact for Conv1, Conv2, and Conv3.

## Vitis 5 ns synthesis result

The new top was synthesized under the frozen OC2 settings:

```text
Top: srcnn_hls_line_buffer_replicate_oc2_writeback_top
Part: xck26-sfvc784-2LV-c
Clock: 5 ns
CFLAGS: -std=c++14 -DSRCNN_HLS_FIXED_POINT=1
```

Component:

```text
srcnn_hls_conv1_oc2_writeback_5ns
```

| Metric | Frozen OC2 | Incremental writeback | Change |
|---|---:|---:|---:|
| Top slack | +0.02 ns | +0.02 ns | 0 |
| Output-loop slack | +0.02 ns | +0.02 ns | 0 |
| Top latency | 310,940,237 | 310,940,237 | 0 |
| Top interval | 310,940,238 | 310,940,238 | 0 |
| BRAM | 154 | 154 | 0 |
| DSP | 17 | 17 | 0 |
| FF | 7,786 | 7,786 | 0 |
| LUT | 14,868 | 14,868 | 0 |

The Conv1 MAC schedule is also unchanged: inner trip count 81, latency 84,
iteration latency 5, and II=1, repeated by 32 output-channel groups.

The most likely interpretation is that Vitis 2026.1 already canonicalized the
original CHW address expression into the same recurrence during synthesis.
Hand-writing the recurrence therefore produced an observationally identical
implementation. This is a useful negative control, not a throughput result.

The raw report remains on the Windows tool machine at:

```text
C:\fpga\vitis-workspace\srcnn_hls_conv1_oc2_writeback_5ns\srcnn_hls_conv1_oc2_writeback_5ns\hls\syn\report\csynth.rpt
```

## Decision

Do not promote this branch over `hls-conv1-oc2-5ns`, and do not cite it as an
optimization gain. Retain it as an ablation/negative-result record. The next
throughput experiment must branch from the frozen OC2 tag, not from this code.
