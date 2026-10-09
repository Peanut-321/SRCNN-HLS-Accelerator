# P2.5 canonical DATAFLOW repair — host checkpoint

Date: 2026-10-09

The first Vitis validation of commit `05afaf6` preserved numerical correctness
but emitted `HLS 214-114` / `HLS 200-471`, stalled RTL co-simulation after the
first transaction, and generated a `model_mem_rd_proc` whose interval was
nearly the full 756,699,474-cycle top latency. That result is preserved in
`results/p2_5-axis-dataflow-vitis.md` and is not a deployment baseline.

This repair makes two structural changes only:

1. `load_runtime_model` copies the 8,129 DDR model elements into six
   layer-owned local arrays before the streaming computation starts.
2. `run_streaming_core` is the DATAFLOW region and contains only four stream
   declarations plus the five stage calls. It has no conditional, early
   return, model pointer, or other executable statement outside those calls.

The arithmetic order, OC4 mapping, internal pixel-major order, padding,
fixed-point types, FIFO depths, external AXIS protocol, and model-buffer layout
are unchanged. Conv2 receives no new UNROLL or throughput pragma.

Mac regression after the repair:

```text
Release unit:          1/1 PASS
Release float_bitwise: 3/3 PASS
Release fixed:         4/4 PASS
ASan/UBSan float set:  5/5 PASS
```

The AXIS/DATAFLOW-specific float and fixed tests still match the frozen OC4
final output exactly for 1x1, 5x7, and 13x17 frames and still pass all
KEEP/STRB/LAST checks.

Pending Windows gate: repeat C simulation, all three RTL co-sim transactions,
5 ns deployment synthesis, DATAFLOW/memory-process inspection, and IP export.
The repair is successful only if the canonical-form warning disappears,
`model_mem_rd_proc` is limited to the short pre-load phase, and all five stages
overlap in the DATAFLOW report.

