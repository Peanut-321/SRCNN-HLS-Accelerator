# Versioning and optimization checkpoints

The repository starts from the verified functional HLS baseline. Optimizations
must be introduced as separate commits or branches so numerical changes and
structural changes remain attributable.

## Baseline tag

`hls-functional-baseline-p2.2a`

This tag contains:

- frozen Golden Reference and independent oracle assets;
- natural-loop three-layer HLS C++ implementation;
- float bitwise regression;
- Mac `ap_fixed` P2.2a regression and saturation diagnostics;
- official 255x255 shape and replicate-edge functional contract;
- no AXI Stream, line buffer, PIPELINE, UNROLL, ARRAY_PARTITION, or DATAFLOW
  optimization.

## Suggested optimization sequence

Create one branch or commit series for each checkpoint:

1. `baseline-csynth`: synthesize the unoptimized top and save schedule,
   latency, II, clock, and resource reports.
2. `axi-stream-interface`: freeze TDATA packing, TKEEP, TLAST, control, and
   DMA transfer lengths with a dummy/smoke test.
3. `line-buffer`: replace repeated frame reads with sliding-window storage;
   preserve the fixed arithmetic layer unchanged.
4. `pipeline`: pipeline the selected pixel/window loops and diagnose any
   reported dependency or memory-port limitation.
5. `unroll-partition`: choose a DSP-budgeted MAC parallelism factor and add
   matching weight/buffer partitioning.
6. `dataflow`: connect layer stages with bounded streams/FIFOs and verify that
   no depth causes deadlock.
7. `board-mvp`: export IP, build the overlay, run correctness tests on KV260,
   and measure kernel-only and end-to-end timing.
8. `ablation-report`: disable optimizations from the final version and record
   at least three controlled comparison rows.

At every checkpoint, keep the same input, weights, padding, clock target, and
measurement boundary. A version that fails layer-wise comparison against the
frozen Golden must not become the parent of the next optimization checkpoint.
