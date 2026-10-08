# P2.3 MAC-A replicate specialization host checkpoint

Date: 2026-10-08  
Branch: `optimize/conv1-mac-a-replicate`  
Code commit: `e68e0fd`  
Status: frozen; Mac host correctness and Vitis 5 ns / 6 ns synthesis complete

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

## Vitis synthesis result

`srcnn_hls_line_buffer_replicate_top` was synthesized under the same part,
CFLAGS, and automatic-pipelining configuration as the static baseline:

```text
Part: xck26-sfvc784-2LV-c
Clock points: 5 ns and 6 ns
User pragmas: none
```

| Metric | Static 5 ns | MAC-A 5 ns | Static 6 ns | MAC-A 6 ns |
|---|---:|---:|---:|---:|
| Top slack | -0.54 ns | **+0.05 ns** | +0.08 ns | +0.04 ns |
| Conv1/MAC slack | -0.54 ns | **+0.23 ns** | +0.48 ns | **+0.72 ns** |
| MAC II | 1 | 1 | 1 | 1 |
| MAC latency | 5,187 | 5,187 | 5,187 | 5,187 |
| Top latency | 457,505,953 | 457,505,951 | 457,505,697 | 457,505,441 |
| BRAM | 136 | 136 | 136 | 136 |
| DSP | 13 | 13 | 13 | 13 |
| FF | 7,973 | **7,661** | 7,225 | **7,039** |
| LUT | 14,855 | **13,982** | 14,756 | **13,953** |

At 5 ns the top and Conv3 slack are both +0.05 ns while Conv1 is +0.23 ns; at
6 ns the top and Conv3 slack are both +0.04 ns while Conv1 is +0.72 ns. The
critical path has therefore moved from Conv1 to Conv3. Experiment B is not
started for timing: A alone meets 5 ns and preserves MAC II=1.

The replicate top has no `padding_mode` hardware port. The old Conv1
`source_row`/`source_column` and zero-padding boundary comparisons are absent
from its Bind Op report, confirming that compile-time specialization removed
the intended control logic. Throughput is not improved: top interval remains
approximately 457.5 million cycles.

Raw-report fingerprints:

```text
5 ns  csynth (2).rpt  e9c4c3322399a888a998f46aa68948ffa75f318c732e02367b40ae99f749df20
6 ns  csynth (3).rpt  58239b41410d707de943c8146b080df0d6888842382a945fc0bd3ceaf2a51b2e
```

This checkpoint is the parent of the separate Conv1 output-channel parallelism
experiment. The frozen branch/tag must not be rewritten by that experiment.
