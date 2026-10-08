# P0a AXI dummy — Vitis 2026.1 checkpoint

Date: 2026-10-08  
Branch: `deploy/axis-dummy`  
Source commit: `f594722`  
Part: `xck26-sfvc784-2LV-c`  
Clock constraint: 5 ns  
Status: PASS

## Compatibility finding

Vitis 2026.1 did not accept the original namespace-scoped top/interface form.
The working implementation uses:

- a global `extern "C" axis_dummy_top` that refers to namespaced stream types;
- `#pragma HLS INTERFACE mode=axis ...`;
- `#pragma HLS INTERFACE mode=s_axilite ...`.

Mac host simulation still uses the queue-backed compatibility types and passes
after the same source change.

## Results

| Metric | Result |
|---|---:|
| C Simulation | PASS |
| C Synthesis | PASS |
| Main-loop II | 1 |
| Top slack | +1.20 ns |
| Main-loop slack | +3.65 ns |
| Estimated Fmax | 408.36 MHz |
| BRAM | 0 |
| DSP | 0 |
| FF | 112 |
| LUT | 325 |
| IP Catalog export | PASS |

The generated `input_r` and `output_r` ports are 32-bit AXI4-Stream interfaces
with TKEEP, TSTRB, TLAST, TVALID, and TREADY. `length` is an AXI4-Lite register
at offset `0x10`; block control is `ap_ctrl_hs`.

## Artifact locations on the Windows tool machine

```text
C:\fpga\vitis-workspace\axis_dummy_5ns\axis_dummy_5ns\hls\syn\report\csynth.rpt
C:\fpga\vitis-workspace\axis_dummy_5ns\axis_dummy_5ns\hls\impl\export.zip
```

The raw report and export archive are not copied into Git. This record captures
their user-verified results; P0b must retain its own Vivado logs, BD Tcl,
post-implementation timing/utilization, `.bit`, and `.hwh`.
