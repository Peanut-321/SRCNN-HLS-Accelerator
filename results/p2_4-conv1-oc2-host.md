# P2.4 Conv1 OC2 throughput experiment — host checkpoint

Date: 2026-10-08  
Branch: `optimize/conv1-oc2-throughput`  
Parent tag: `hls-mac-a-replicate-5ns` (`1965c5c`)  
Code commit: `d8c4849`  
Status: frozen; Mac host correctness and Vitis 5 ns synthesis complete

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
`64 * 9 * 9 = 5184` to `(64 / 2) * 9 * 9 = 2592`.

## Host correctness gate

```text
Release float build:       4/4 CTest PASS
Release host ap_fixed:     7/7 CTest PASS
ASan/UBSan float build:    4/4 CTest PASS
```

For replicate padding, the OC2 top is compared layer-by-layer with the frozen
MAC-A top on 13x17, 1x1, and 33x29 inputs. Float comparisons are bitwise and
fixed-point comparisons are exact for Conv1, Conv2, and Conv3.

## Vitis 5 ns synthesis result

The OC2 top was synthesized under the same settings as MAC-A:

```text
Top: srcnn_hls_line_buffer_replicate_oc2_top
Part: xck26-sfvc784-2LV-c
Clock: 5 ns
CFLAGS: -std=c++14 -DSRCNN_HLS_FIXED_POINT=1
```

| Metric | MAC-A | OC2 | Change |
|---|---:|---:|---:|
| Top latency | 457,505,951 | 310,940,237 | -32.0% |
| Top interval | 457,505,952 | 310,940,238 | -32.0% |
| Conv1 latency | 360,373,126 | 213,807,412 | -40.7% |
| Top slack | +0.05 ns | +0.02 ns | -0.03 ns |
| BRAM | 136 | 154 | +18 |
| DSP | 13 | 17 | +4 |
| FF | 7,661 | 7,786 | +125 |
| LUT | 13,982 | 14,868 | +886 |

The schedule represents the effective 2592 Conv1 iterations as 32 output
channel groups times an inner 81-position kernel loop. The inner loop has II=1
and latency 84 cycles, and its two unrolled MAC lanes use eight DSPs. This is
the intended `32 * 81 = 2592` schedule even though no single flattened report
row has trip count 2592.

The 18 added BRAMs are fully explained by two 8-BRAM weight banks and two
1-BRAM bias banks. The former are required for two simultaneous weight reads;
the latter are low-utilization candidates for a separate future experiment.

The MAC loop retains +0.23 ns slack. The new minimum +0.02 ns slack is in the
two-element Conv1 output loop, which performs activation/narrowing, CHW address
generation, and output writeback. OC2 therefore passes 5 ns, but this output
loop must be isolated before attempting OC4.

Raw-report fingerprint:

```text
csynth (4).rpt  bfd749fbbd502b78bcee98a674aaf2e29d577fb4c84a7ae0f1147325bf496f94
```

OC2 is accepted as the new HLS throughput checkpoint, subject to the still-open
P0 overlay-specific kernel budget. Its child experiment may change only Conv1
writeback address generation; OC4 must not be mixed into that experiment.
