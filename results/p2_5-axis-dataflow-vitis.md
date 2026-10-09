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

## Follow-up diagnostic prepared after the re-run

The testbench now supports compile-time isolation modes without changing the
DUT. Modes 1, 2, and 3 run 1x1, 5x7, and 13x17 as independent single
transactions. Mode 4 calls 1x1 twice, and mode 5 calls 1x1 followed by 5x7.
The existing three-transaction regression remains mode 0 and the default.

All six host configurations (default plus modes 1--5) pass on macOS. This does
not close the RTL gate; it only validates the diagnostic testbench. The next
Windows action is to run independent RTL co-simulation for modes 1--3, then
use modes 4 and 5 only if all three single-transaction runs pass. The decision
table and exact compile definition are recorded in `docs/p2-axis-dataflow.md`.

---

# RTL co-simulation isolation re-validation (commit `063b180`)

## Configuration

Five dedicated Vitis component configurations were created in
`C:\fpga\vitis-workspace`. Each keeps the same DUT
`srcnn_axis_dataflow_cosim_top`, part `xck26-sfvc784-2LV-c`, 5 ns clock, and
`-std=c++14 -DSRCNN_HLS_FIXED_POINT=1` design flags. Only the testbench flag
changes:

```text
-DSRCNN_AXIS_DATAFLOW_TEST_CASE=N
```

DATAFLOW profiling, FIFO sizing, and port tracing were enabled for every
component. No DUT, convolution, FIFO-depth, or pragma change was made.

## Results

| Mode | Calls | C testbench | RTL co-sim | Completion evidence |
|---:|---|---|---|---|
| 1 | 1x1 | PASS | **PASS** | `1 / 1` at `215833000 ps` |
| 2 | 5x7 | PASS | **PASS** | `1 / 1` at `524353000 ps` |
| 3 | 13x17 | PASS | **FAIL / incomplete** | remained `0 / 1` at `113000 ps`; stopped after CPU progress ceased |
| 4 | 1x1 then 1x1 | Not run | Not run | mode 3 already fails as a single transaction |
| 5 | 1x1 then 5x7 | Not run | Not run | mode 3 already fails as a single transaction |

Mode 1 and mode 2 each use exactly one top-level call and completed in XSIM.
The reported timestamps correspond to approximately 43,167 and 104,871 clock
periods at 5 ns, respectively, including simulator/testbench overhead; Vitis
does not print a separate integer RTL cycle total for these single-call runs.

For mode 3, the C testbench passed the 13x17 output comparison and AXIS
metadata checks, then XSIM began the one transaction but never reached a
completion/progress line. Its CPU time stopped changing at 118.09 seconds
while the log remained at `0 / 1`. The process was terminated manually.

## FIFO / channel profiling

The generated DATAFLOW channel inventory contains the expected channels:

```text
input_pixels_U     -> depth1.csv / chan_status1.csv
conv1_features_U   -> depth2.csv / chan_status2.csv
conv2_features_U   -> depth3.csv / chan_status3.csv
output_pixels_U    -> depth4.csv / chan_status4.csv
```

The failed run generated the monitor RTL and channel metadata, but did not
produce `chan_status*.csv` or `depth*.csv` runtime traces before it stopped.
Consequently this run cannot identify a particular FIFO as full or empty
without guessing. The isolation result is nevertheless decisive: the 13x17
DATAFLOW RTL execution itself is the current failing case, rather than a
second-start or changing-dimension harness issue.

## Next action

Do not run modes 4 or 5 until the single 13x17 transaction can complete. Keep
the DUT unchanged while inspecting the generated XSIM waveform / dataflow
monitor for the 13x17 run, then identify the producer/consumer channel that
prevents forward progress. Vivado integration and Conv2 optimization remain
blocked.

## Minimal AXIS verification-adapter diagnostic

Code inspection confirms balanced counts for the failed 13x17 transaction:

```text
axis_to_scalar: 221
Conv1 output / Conv2 input: 221 * 64 = 14,144
Conv2 output / Conv3 input: 221 * 32 = 7,072
Conv3 output / scalar_to_axis: 221
```

The pipeline is linear and has no feedback channel. The next checkpoint adds
`depth=65025` to the input and output AXIS interface pragmas of both top-level
wrappers. Per AMD UG1399, this depth is the maximum sample capacity of the RTL
co-simulation verification adapter; it does not allocate a full-frame FIFO in
the synthesized AXIS datapath. This change does not alter arithmetic, internal
FIFO depths, padding, loop structure, or interfaces visible to Vivado.

Repeat mode 3 first under the same part, 5 ns clock, and fixed-point flags. A
PASS attributes the prior stop to an underspecified verification adapter. A
repeat failure rejects that hypothesis and requires waveform inspection of
the four internal DATAFLOW channel handshakes before any FIFO depth is changed.

---

# AXIS depth re-validation (commit `46af475`)

## Fresh mode-3 build

The repository was fast-forwarded to `46af475 Size AXIS cosim adapters for full
frames`. The Windows test used a new component directory rather than the
previous mode-3 component, so its RTL was freshly generated from the updated
source:

```text
Component: srcnn_axis_dataflow_cosim_case3_depth_5ns
Top:       srcnn_axis_dataflow_cosim_top
Part:      xck26-sfvc784-2LV-c
Clock:     5 ns
Design:    -std=c++14 -DSRCNN_HLS_FIXED_POINT=1
Testbench: -DSRCNN_AXIS_DATAFLOW_TEST_CASE=3
```

C synthesis completed successfully in 1 minute 25 seconds and reported an
estimated Fmax of 273.97 MHz. During synthesis, however, Vitis emitted the
following warnings for the two newly added top-level AXIS pragmas:

```text
WARNING: [HLS 214-387] Ignore depth setting for top argument 'input'
WARNING: [HLS 214-387] Ignore depth setting for top argument 'output'
```

Thus Vitis HLS 2026.1 did not apply the requested `depth=65025` as an HLS
interface-depth setting for this top-level stream interface.

## Result

The newly generated co-simulation C testbench passed the 13x17 functional
comparison and reported a maximum C-model stream depth of 14,144. XSIM then
started a single RTL transaction and remained at:

```text
RTL Simulation : 0 / 1 [n/a] @ "113000"
```

for more than two minutes of additional XSIM CPU time, with no simulation-time
or transaction progress. The XSIM process was stopped manually. Therefore the
AXIS-depth hypothesis is **not resolved by this Windows/Vitis 2026.1 test**;
the pragma was explicitly ignored and the prior mode-3 symptom remains.

The fresh waveform is retained at:

```text
C:\fpga\vitis-workspace\srcnn_axis_dataflow_cosim_case3_depth_5ns\hls\sim\verilog\srcnn_axis_dataflow_cosim_top.wdb
```

No mode-0 three-frame run was performed because the prerequisite single 13x17
RTL transaction still does not complete. No DUT, convolution code, padding,
internal FIFO depth, or numeric type was changed in this Windows validation.

## Next diagnostic

Inspect the retained waveform in this order: `ap_start/ap_ready/ap_done`,
completion of `load_runtime_model`, start of `run_streaming_core`, AXIS
`TVALID/TREADY` on input and output, then each internal FIFO's
empty/full/read/write signals. Do not change FIFO depths or Conv2 pragmas
before identifying the blocked producer/consumer relationship.
