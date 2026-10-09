# P2.5 AXI-Stream DATAFLOW Vitis validation (Windows)

## Scope

This run validates the existing `deploy/srcnn-axis-dataflow` implementation in
Vitis HLS only. It does not enter Vivado Block Design, PYNQ, board deployment,
or Conv2 optimization.

| Item | Value |
|---|---|
| Git commit | `05afaf6 Add streaming SRCNN dataflow deployment path` |
| Vitis HLS | 2026.1, build 6493734 (Jun 16 2026) |
| Part | `xck26-sfvc784-2LV-c` |
| Clock target | 5 ns (200 MHz) |
| Numeric build | `-std=c++14 -DSRCNN_HLS_FIXED_POINT=1` |
| Deployment top | `srcnn_axis_dataflow_top` |
| Small-image verification top | `srcnn_axis_dataflow_cosim_top` |

The Vitis 2026.1 Unified HLS component flow was used. The repository's legacy
Tcl C-simulation flow omitted design objects from its link manifest on this
installation, so it could not link the testbench; no source was changed to
work around that tool-flow issue.

## C simulation: PASS

`srcnn_axis_dataflow_cosim_top` was compiled and run with the repository test
bench. The testbench explicitly calls that top, rather than only a software
reference.

| Case | Result |
|---|---|
| 1 x 1, replicate-edge | PASS (1 AXIS word) |
| 5 x 7, replicate-edge | PASS (35 AXIS words) |
| 13 x 17, replicate-edge | PASS (221 AXIS words) |
| Final output against frozen OC4 | Exact match |
| Output word count | Correct |
| TKEEP / TSTRB | `0xF` on every output word |
| TLAST | Asserted only on the final output word |

The C-simulation log reports `maximum depth reached: 14144` and completes with
zero errors.

## RTL co-simulation: incomplete / not a pass

Vitis launched XSIM and compiled the generated RTL co-simulation harness for
`srcnn_axis_dataflow_cosim_top`. This confirms that the intended RTL top was
used; it is not a testbench-only false pass.

The C testbench phase printed all three PASS lines. RTL simulation completed
only transaction 1 of 3, reaching simulation time `254308000`, then stopped
making progress before the 5 x 7 and 13 x 17 transactions. CPU usage and
`xsim.log` remained unchanged during a further observation interval, so the
run was stopped manually.

| Item | Observation |
|---|---|
| RTL language / simulator | Verilog / XSIM |
| Completed transactions | 1 / 3 |
| Co-sim total cycles | Not available: run did not complete |
| Explicit deadlock or timeout diagnostic | None emitted before the stall |
| Result | **FAIL / incomplete** |

Relevant artifacts remain in:

```text
C:\fpga\vitis-workspace\srcnn_axis_dataflow_cosim_5ns\srcnn_axis_dataflow_cosim_5ns\hls\sim\report\cosim.log
C:\fpga\vitis-workspace\srcnn_axis_dataflow_cosim_5ns\srcnn_axis_dataflow_cosim_5ns\hls\sim\verilog\xsim.log
```

## Deployment C synthesis: completed, but dataflow performance is invalid

The fixed-size `srcnn_axis_dataflow_top` was synthesized and exported as an IP
Catalog IP. It meets the local 5 ns combinational timing estimate:

| Metric | Result |
|---|---|
| Estimated Fmax | 273.97 MHz |
| 5 ns timing | PASS by Fmax estimate |
| Top timing slack shown in hierarchy | 0.00 ns (aggregate DATAFLOW boundary) |
| Top latency | 756,699,474 cycles |
| Top interval | 756,699,475 cycles |
| BRAM | 191 (66%) |
| DSP | 30 (2%) |
| LUT | 29,607 (25%) |
| FF | 13,097 (5%) |
| URAM | 0 |

The latency and interval are not acceptable deployment performance results.
They show that the stages have not been scheduled as an overlapping streaming
pipeline.

## DATAFLOW analysis

The report recognizes `run_srcnn_axis_dataflow` as a DATAFLOW region and
creates the requested FIFOs:

| Channel | FIFO depth |
|---|---:|
| `input_pixels` | 64 |
| `conv1_features` | 128 |
| `conv2_features` | 64 |
| `output_pixels` | 64 |

The stage hierarchy is present, but its schedule shows sequential rather than
streaming behavior:

| Stage | Reported latency / interval (cycles) |
|---|---:|
| `axis_to_scalar` | 65,027 / 65,026 |
| `conv1_stream` | 512,715,760 / 512,715,760 |
| `conv2_stream` | 73,805,468 / 73,805,468 |
| `conv3_stream` | 170,178,238 / 170,178,238 |
| `scalar_to_axis` | 65,027 / 65,026 |
| `run_srcnn_axis_dataflow_Block_entry_model_mem_rd_proc` | 756,699,471 / 756,699,471 |

The stage latencies sum to the enormous top estimate. The generated
`model_mem_rd_proc` has the same near-top interval, which is direct evidence
that accesses through the shared `model_mem` process are part of the current
scheduling limitation. Conv1 has the largest individual stage estimate;
therefore this run does **not** prove that Conv2 is the bottleneck.

Vitis also issued these structural diagnostics:

```text
WARNING: [HLS 214-114] Since the only kind of statements allowed in a
canonical dataflow region are variable declarations and function calls, the
compiler may not be able to correctly handle the region
(srcnn_axis_dataflow.cpp:501:9)
WARNING: [HLS 200-471] Dataflow form checks found 1 issue(s)
```

No array-port-conflict, loop-carried-dependency, or memory-port warning was
reported in this run beyond the DATAFLOW-form diagnostic. The next source
change must first make this region canonical and then repeat C simulation,
co-simulation, synthesis, and the schedule/dependency/memory-port inspection.
Do not add a Conv2 UNROLL pragma based on this result.

## Interface check

The exported deployment IP is synthesized from `srcnn_axis_dataflow_top`, not
the small-image co-simulation top.

| Interface | Reported implementation |
|---|---|
| `input_r` | AXI4-Stream input: TDATA 32, TKEEP 4, TSTRB 4, TLAST 1, TVALID/TREADY |
| `output_r` | AXI4-Stream output: TDATA 32, TKEEP 4, TSTRB 4, TLAST 1, TVALID/TREADY |
| `m_axi_model_mem` | Read-only AXI master, 32 -> 32-bit data, 64-bit address, max read burst 16 |
| `s_axi_control` | 32-bit AXI4-Lite control |
| Control protocol | `ap_ctrl_hs` |

AXI-Lite registers: `CTRL` (0x00), `GIER` (0x04), `IP_IER` (0x08),
`IP_ISR` (0x0c), and the 64-bit model pointer as `model_1` (0x10) and
`model_2` (0x14).

## IP export

Export completed successfully. The artifact is intentionally not added to Git:

```text
C:\fpga\vitis-workspace\srcnn_axis_dataflow_deployment_255x255_5ns\srcnn_axis_dataflow_deployment_255x255_5ns\hls\impl\export.zip
```

## Conclusion and next action

Function-level C simulation and the requested AXI metadata checks pass.
However, RTL co-simulation stalls after its first transaction and synthesis
reports a non-canonical DATAFLOW warning together with a serialized
756,699,474-cycle deployment schedule. The deployment IP must not yet be used
for Vivado integration.

The next task is to make the DATAFLOW region canonical with the smallest
functional-preserving source change, then re-run the same four gates:
C simulation, three-case RTL co-simulation, deployment synthesis, and IP
export. Only after a completed co-sim and an overlapping dataflow schedule
should a per-stage bottleneck analysis decide whether Conv2 needs optimization.

---

# Canonical DATAFLOW re-validation (commit `72e7f7e`)

## Revision under test

| Item | Value |
|---|---|
| Commit | `72e7f7e Make SRCNN dataflow region canonical` |
| Vitis HLS | 2026.1, build 6493734 |
| Part / clock | `xck26-sfvc784-2LV-c` / 5 ns |
| Deployment top | `srcnn_axis_dataflow_top` |
| Co-sim top | `srcnn_axis_dataflow_cosim_top` |

This re-run used the pushed minimal structural fix: the 8,129 model values are
loaded before the DATAFLOW region into layer-local arrays. No arithmetic,
padding, OC4, FIFO-depth, numeric-type, or Conv2-parallelism change was made.

## Gate results

### C simulation: PASS

The Vitis C-simulation run passed 1 x 1, 5 x 7, and 13 x 17 replicate-edge
cases. It also reported an exact final-output match to OC4, correct AXIS word
counts, `TKEEP=TSTRB=0xF`, and TLAST on only the final output word.

### RTL co-simulation: FAIL / incomplete

The generated harness again compiled and invoked
`srcnn_axis_dataflow_cosim_top` in Verilog XSIM. C-testbench preparation
passed all three cases. RTL simulation reached transaction `1 / 3` at
simulation time `254308000` and then made no reported transaction progress for
more than three minutes, despite XSIM continuing to consume CPU. No explicit
stream-deadlock or timeout diagnostic was emitted. The stalled XSIM run was
stopped manually; consequently no total co-simulation cycle count is available.

This is a repeatable gate failure and prevents Vivado integration.

### Deployment synthesis and IP export: completed

The fixed-size deployment top synthesized and exported successfully. The
canonical DATAFLOW diagnostics are gone: this run contains no `HLS 214-114`
or `HLS 200-471` message.

| Metric | Result |
|---|---:|
| Estimated Fmax | 273.97 MHz |
| 5 ns timing | PASS by Fmax estimate |
| Top latency | 512,719,257 cycles |
| Top interval | 512,719,258 cycles |
| Top hierarchy slack | 0.00 ns |
| DATAFLOW region slack | 0.04 ns |
| BRAM | 247 (85%) |
| DSP | 86 (6%) |
| LUT | 24,375 (20%) |
| FF | 9,287 (3%) |
| URAM | 0 |

The final exported IP is:

```text
C:\fpga\vitis-workspace\srcnn_axis_dataflow_deployment_255x255_5ns\hls\impl\export.zip
```

## DATAFLOW result

The report now shows a short, separate model preload stage:

```text
load_runtime_model: latency/interval 8,201 / 8,201 cycles
```

There is no longer a `model_mem_rd_proc` that encloses the convolution stages.
The core is identified as a DATAFLOW region. The configured stream FIFO depths
remain unchanged:

| Channel | Depth |
|---|---:|
| `input_pixels` | 64 |
| `conv1_features` | 128 |
| `conv2_features` | 64 |
| `output_pixels` | 64 |

The stage estimates show overlap rather than the prior sum of all stages:

| Stage | Latency / interval (cycles) |
|---|---:|
| `axis_to_scalar` | 65,027 / 65,026 |
| `conv1_stream` | 512,711,051 / 512,711,051 |
| `conv2_stream` | 15,540,976 / 15,540,976 |
| `conv3_stream` | 170,178,228 / 170,178,228 |
| `scalar_to_axis` | 65,027 / 65,026 |
| DATAFLOW core | 512,711,051 / 512,711,052 |

The core latency equals the maximum stage estimate (`conv1_stream`) rather
than the sum of Conv1, Conv2, and Conv3, which is evidence that the canonical
DATAFLOW structure is now recognized. Conv1 is the current estimated
throughput bottleneck; Conv2 is not. This synthesis run emitted no explicit
array-port-conflict, memory-port, dependency, or schedule-failure diagnostic.

## Interfaces

The exported deployment top remains correct:

- AXI4-Stream `input_r` and `output_r`: 32-bit TDATA, 4-bit TKEEP/TSTRB,
  TLAST, TVALID, and TREADY.
- Read-only `m_axi_model_mem`: 32-bit data, 64-bit address, maximum read burst
  length 16.
- 32-bit `s_axi_control` and `ap_ctrl_hs`; model pointer registers are
  `model_1` at 0x10 and `model_2` at 0x14.

## Decision

The source-level DATAFLOW repair is successful in synthesis, but the complete
Windows Vitis gate is still **not passed** because RTL co-simulation does not
finish. Do not enter Vivado or optimize Conv2 yet. The next debugging task is
to diagnose the XSIM transaction-2 stall using the generated RTL testbench and
DATAFLOW trace/FIFO profiling, while preserving the verified canonical
structure.
