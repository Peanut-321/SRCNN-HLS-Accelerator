# P2.5 AXI-Stream + DATAFLOW host checkpoint

Date: 2026-10-09

Branch: `deploy/srcnn-axis-dataflow`

Implemented:

- fixed `255x255` AXI4-Stream deployment wrapper;
- one 32-bit `data_t` per beat and deterministic output sidebands;
- Conv1 OC4 -> Conv2 -> Conv3 internal `hls::stream` stages;
- top-level `DATAFLOW` region and explicit FIFO depths;
- pixel-major internal feature streams;
- row-buffered replicate-edge Conv1/Conv3 with no full intermediate maps;
- one contiguous 8,129-element runtime model buffer on `m_axi`;
- Mac queue-backed stream compatibility using the same stage code.

Host gates:

```text
float:    srcnn_axis_dataflow_float  PASS
ap_fixed: srcnn_axis_dataflow_fixed  PASS
cases:    1x1, 5x7, 13x17 replicate-edge
oracle:   frozen OC4 line-buffer implementation
result:   exact final-output equality; AXIS count/KEEP/STRB/LAST correct
```

Full regression after the change:

```text
Release unit:          1/1 PASS
Release float_bitwise: 3/3 PASS
Release fixed:         4/4 PASS
ASan/UBSan float set:  5/5 PASS
```

Not yet measured:

- Vitis C simulation / C synthesis / RTL co-simulation for this top;
- achieved DATAFLOW schedule, stage interval, latency, or FIFO occupancy;
- 5 ns timing and resource use;
- post-implementation timing;
- board DMA correctness or throughput;
- official-model PSNR/error metrics.

Run the host gate with:

```bash
make host-axis-dataflow
```

Run the Windows/Vitis gate with the confirmed KV260 part and 5 ns target:

```bash
make vitis-axis-dataflow-export \
  SRCNN_HLS_PART=xck26-sfvc784-2LV-c \
  SRCNN_HLS_CLOCK_NS=5.0
```
