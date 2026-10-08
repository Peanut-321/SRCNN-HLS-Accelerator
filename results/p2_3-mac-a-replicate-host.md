# P2.3 MAC-A replicate specialization host checkpoint

Date: 2026-10-08  
Branch: `optimize/conv1-mac-a-replicate`  
Code commit: `e68e0fd`  
Status: Mac host correctness complete; Vitis 5 ns / 6 ns synthesis pending

## Controlled change

This checkpoint performs only experiment A. It adds
`srcnn_hls_line_buffer_replicate_top`, whose padding contract is fixed to
replicate-edge at compile time while height and width remain dynamic for host
regression.

The Conv1 implementation is shared through the `ReplicateOnly` template
parameter:

- `false` preserves the existing runtime valid/zero/replicate behaviour;
- `true` removes Conv1's runtime padding-mode selection and zero-padding skip
  logic from the deployment specialization;
- the existing generic top and all zero/valid tests remain present.

There is no MAC product-register experiment, PIPELINE, UNROLL,
ARRAY_PARTITION, numeric-width change, or AXI change in this checkpoint.

## Host verification

For replicate-edge cases, the new top is compared layer by layer with the
existing generic line-buffer top on 13x17, 1x1, and 33x29 inputs. Existing
zero-same and valid tests continue to run through the generic top.

```text
Float build:              4/4 CTest PASS
Host ap_fixed build:      7/7 CTest PASS
ASan/UBSan float build:   4/4 CTest PASS
```

Float comparisons are bitwise and fixed-point comparisons are exact for Conv1,
Conv2, and Conv3.

## Required Vitis gate

Synthesize `srcnn_hls_line_buffer_replicate_top` under the same part, CFLAGS,
and automatic-pipelining configuration as the static baseline:

```text
Part: xck26-sfvc784-2LV-c
Clock points: 5 ns and 6 ns
User pragmas: none
```

Use distinct components such as `srcnn_hls_mac_a_replicate_5ns` and
`srcnn_hls_mac_a_replicate_6ns`. Record top/Conv1/MAC-loop slack, MAC II and
latency, top latency/interval, and BRAM/DSP/FF/LUT. Do not start experiment B
until these reports show whether A alone resolves the 5 ns violation.
