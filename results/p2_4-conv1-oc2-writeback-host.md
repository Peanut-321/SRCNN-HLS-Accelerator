# P2.4 Conv1 OC2 incremental writeback — host checkpoint

Date: 2026-10-08  
Branch: `optimize/conv1-oc2-writeback-address`  
Parent tag: `hls-conv1-oc2-5ns` (`201cceb`)  
Code commit: `a7b41d3`  
Status: Mac host correctness complete; Vitis 5 ns synthesis pending

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

## Required Vitis gate

Synthesize only the new top under the frozen OC2 settings:

```text
Top: srcnn_hls_line_buffer_replicate_oc2_writeback_top
Part: xck26-sfvc784-2LV-c
Clock: 5 ns
CFLAGS: -std=c++14 -DSRCNN_HLS_FIXED_POINT=1
```

Use a distinct component, for example:

```text
srcnn_hls_conv1_oc2_writeback_5ns
```

Compare against `hls-conv1-oc2-5ns`:

- top and Conv1 slack;
- the two-element output-loop slack, latency, and II;
- grouped MAC trip counts, II, and latency;
- top and Conv1 latency/interval;
- BRAM, DSP, LUT, and FF;
- Bind Op/address-generation operations in the output loop.

## Decision gate

Accept this experiment only if host equivalence remains true and synthesis
shows a real writeback-path improvement without reducing MAC throughput or
increasing material resources. The primary target is output-loop/top slack
greater than the OC2 baseline's `+0.02 ns`; top latency must not regress
materially from 310,940,237 cycles. If synthesis gives no improvement, keep
the frozen OC2 tag and discard this branch rather than layering OC4 on it.
