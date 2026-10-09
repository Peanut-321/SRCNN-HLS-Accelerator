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

---

# Full-trace RTL co-simulation diagnosis (case 3)

## Configuration

The existing synthesized RTL was reused; no C synthesis and no source change
was performed. The component configuration was updated only for co-simulation:

```ini
cosim.tool=xsim
cosim.rtl=verilog
cosim.trace_level=all
cosim.wave_debug=true
cosim.enable_dataflow_profiling=true
cosim.enable_fifo_sizing=true
```

The testbench remained `-DSRCNN_AXIS_DATAFLOW_TEST_CASE=3`. Vitis accepted
these settings and elaborated XSIM with `-debug all`.

## Waveform evidence

The fresh all-trace run again remained at `RTL Simulation : 0 / 1 @ 113000 ps`.
The WDB was opened and inspected from 0 to 1,000 ns.

| Time | Signal/event | Observed state | Conclusion |
|---|---|---|---|
| 0--1,000 ns | `AESL_clock` | continuously toggles | clock is operating |
| approximately 110 ns onward | `rst`, `dut_rst` | deasserted and stable | reset is released |
| 0--1,000 ns | harness `start`, `ce`, `tb_continue` | all `X` | harness does not drive a valid start/control transaction |
| 0--1,000 ns | `AESL_start`, `AESL_ready`, `AESL_done` | `X`; `AESL_idle` is `Z` | no usable accepted top-level start state |
| 0--1,000 ns | `m_axi_model_mem_ARVALID/ARREADY` | both `X` | no address handshake occurs |
| 0--1,000 ns | `ARADDR`, `ARLEN`, `RVALID`, `RREADY`, `RLAST`, `RRESP` | all unknown | model-memory read channel never initializes |

## Classification

**B. The top does not receive a valid/accepted start from the RTL co-simulation
harness.** This is upstream of SRCNN arithmetic, model loading, DATAFLOW, AXIS,
and internal FIFOs. The absent model-memory activity is a consequence of the
invalid control state, not evidence of a Conv1/Conv2/FIFO deadlock.

Do not change Conv code, FIFO depth, or HLS pragmas. The next investigation
must inspect or repair the generated co-simulation control harness / AXI-Lite
startup path so that `start` and `ce` are driven to known values before the
DUT is expected to issue `m_axi_model_mem` reads.

## Fixed-size wrapper diagnostic prepared

The deployment top has compile-time-fixed dimensions, whereas the failing
small-image wrapper exposes `height` and `width` through AXI-Lite. A new
diagnostic top, `srcnn_axis_dataflow_cosim_13x17_top`, removes those two runtime
registers and invokes the unchanged core with constants 13 and 17. Its external
control shape otherwise matches deployment: AXIS input/output, one model
`m_axi`, AXI-Lite model pointer, and `ap_ctrl_hs` return.

The matching testbench build must define both:

```text
-DSRCNN_AXIS_DATAFLOW_TEST_CASE=3
-DSRCNN_AXIS_DATAFLOW_USE_FIXED_13X17_TOP=1
```

This is a harness-isolation experiment, not a compute optimization. It changes
no arithmetic, token counts, FIFO depths, padding, or model layout. Synthesize
and RTL co-simulate this fixed top in a new component. If it passes, the
dynamic height/width co-simulation wrapper is the blocker and does not describe
the fixed deployment IP. If its start signals remain unknown, the fault is in
the more general generated AXI-Lite/m_axi co-simulation harness.

---

# Fixed 13x17 top RTL co-simulation diagnostic (commit `7fc62cb`)

## Independent component

A new component was created outside the repository build tree:

```text
Component: srcnn_axis_dataflow_cosim_13x17_5ns
Top:       srcnn_axis_dataflow_cosim_13x17_top
Part:      xck26-sfvc784-2LV-c
Clock:     5 ns
```

Design flags were `-std=c++14 -DSRCNN_HLS_FIXED_POINT=1`. The testbench used
case 3 together with `-DSRCNN_AXIS_DATAFLOW_USE_FIXED_13X17_TOP=1`.
The logs confirm both the synthesis top and generated co-simulation harness
used `srcnn_axis_dataflow_cosim_13x17_top`.

## Gates

| Gate | Result | Evidence |
|---|---|---|
| C simulation | PASS | 13x17 AXIS/DATAFLOW output exactly matches OC4 |
| C synthesis | PASS | completed in 1m24s; estimated Fmax 273.97 MHz |
| RTL co-simulation | incomplete | remained `0 / 1 [0.00%] @ 113000 ps` |

The all-trace co-simulation was configured with XSIM, Verilog,
`trace_level=all`, `wave_debug=true`, and dataflow profiling. It elaborated
the fixed top with `-debug all`. After more than two minutes without a
transaction or simulation-time update, XSIM was stopped and the WDB retained:

```text
C:\fpga\vitis-workspace\srcnn_axis_dataflow_cosim_13x17_5ns\hls\sim\verilog\srcnn_axis_dataflow_cosim_13x17_top.wdb
```

## Conclusion

The fixed top removes the dynamic `height` and `width` AXI-Lite arguments but
reproduces the same 113000 ps, zero-transaction stop. Therefore the dynamic
wrapper is not the fault source. Together with the all-trace dynamic-wrapper
run, this points to a broader Vitis 2026.1 AXI-Lite/m_axi co-simulation harness
startup problem. Conv code, DATAFLOW, internal FIFOs, and pragmas remain
unmodified and are not implicated by this result.

---

# Generated co-simulation harness comparison (commit `7fc62cb`)

## Scope

This comparison is read-only. It compares the already-generated components:

```text
PASS: C:\fpga\vitis-workspace\srcnn_axis_dataflow_cosim_case2_5ns
FAIL: C:\fpga\vitis-workspace\srcnn_axis_dataflow_cosim_13x17_5ns
```

The passing component synthesizes `srcnn_axis_dataflow_cosim_top` with the
5x7 test case. The failing component synthesizes the distinct fixed-size top
`srcnn_axis_dataflow_cosim_13x17_top` with the 13x17 test case. They therefore
are not the same generated RTL top: the fixed top deliberately has no runtime
`height` or `width` AXI-Lite arguments.

## Generated-file inventory

Text/vector/harness files (excluding XSIM compiled objects and WDB databases):

| Set | Count |
|---|---:|
| 5x7 component | 217 |
| fixed 13x17 component | 206 |

After normalizing the two top names to `<TOP>`, 15 files exist only in the 5x7
component and four only in the fixed component. The important interface-specific
entries are:

| File/category | 5x7 | Fixed 13x17 | Meaning |
|---|---:|---:|---|
| `autotvin_height.dat` | present | absent | runtime height removed |
| `autotvin_width.dat` | present | absent | runtime width removed |
| `control_AWADDR` | 6 bits | 5 bits | address map contracts after removing the two registers |
| flow-control loop RTL | absent | present | generated schedule differs for the fixed top |

Representative checksums are below. The two `model_mem` images are byte-for-byte
identical, which rules out a different model payload as the initial cause.

| Generated file | 5x7 bytes / SHA-256 | Fixed 13x17 bytes / SHA-256 |
|---|---|---|
| `*.autotb.v` | 21066 / `B7FBD4F6A87AC5D8280A0E8DB1C94AEEAE693F6063D09FFD3FE56D37790D50D2` | 20699 / `AC82783134E8157CB78AC17BD3719E410BBD902F7BBA5D1E85F025F666ABC8E4` |
| `autowrap/systemc/apatb_*.cpp` | 41738 / `D357365B7C37C45DA8C2FC568F17B16F0BDBEE341411C6C86833E9C9AF0436F3` | 40732 / `6984E3BDA4AA7DCD933D4ABE6BCD88145869E6D14617FABD476424AD77E85021` |
| `tv/cdatafile/ref.tcl` | 373 / `05A6EC7C65E40FCE5C6F5434A33FB14AF1A33F3938433644F9BE56FB6881F365` | 354 / `DB7ABF391312438E02C47E2BF576B53E49B1A090012AC49A6E56177761C47D20` |
| input data vector | 498 / `C7AAB938AC34CFF59BD0AAF99F58C9138ADA9EDC35436AB13700ABCAAAF68DBB` | 2730 / `747ACE5AFA3EAB1744310F91BB3A197ED8F051EB44438BC822D701C069C46C54` |
| `autotvin_model_mem.dat` | 32532 / `02F083FD8EA69AAAB3DAC2064C25DD969FF594C45B232270B8F786D2617FAED0` | 32532 / `02F083FD8EA69AAAB3DAC2064C25DD969FF594C45B232270B8F786D2617FAED0` |

## Transaction-vector validation

All AXIS vectors have exactly one `[[transaction]]` / `[[/transaction]]` pair
and one enclosing runtime marker. The headers and end markers are valid.

| Item | 5x7 | Fixed 13x17 |
|---|---:|---:|
| input AXIS payload words | 35 | 221 |
| expected output AXIS payload words | 35 | 221 |
| `model_mem` depth in `ref.tcl` | 8129 | 8129 |
| transactions | 1 | 1 |
| `height` / `width` vectors | one each | correctly absent |

The 13x17 vectors therefore describe the expected single frame; no missing
header, truncated payload, or missing end marker was found.

## Start-driver analysis

The generated `*.autotb.v` files declare legacy root-level `start`, `ce`, and
`tb_continue` registers, but neither generated file assigns to any of them.
They are not the DUT start mechanism. `X` on those three signals in a WDB is
expected and cannot diagnose a failed launch.

Both harnesses use the same actual chain:

```text
SV UVM AXI-Lite master
  -> s_axi_control AW/W transactions
  -> svtb_top.misc_if.tb2dut_ap_start
  -> AESL_start in *.autotb.v
  -> DUT ap_start
```

In both generated sequence libraries the AXI-Lite sequence first writes the
`model` pointer at offset 16, waits for completion, then writes bit 0 at address
0 to start the DUT. The 5x7 sequence additionally writes `height` at offset 28
and `width` at offset 36. The fixed 13x17 sequence omits only those two writes.
The common start write is present in each harness.

This corrects the earlier classification that treated `start/ce/tb_continue = X`
as evidence that the top had not been started. The prior waveform checked
legacy un-driven signals, not `tb2dut_ap_start` or the AXI-Lite channel.

## Outcome

No generated transaction-vector or start-sequence defect uniquely explains the
13x17 run. The first concrete generated difference is the intentional interface
change caused by fixed dimensions (no `height/width` vectors and 5-bit rather
than 6-bit AXI-Lite address), and it leaves the model-pointer write at address
16 and start write at address 0 valid.

The next diagnostic must observe the actual UVM AXI-Lite signals
`control_AWVALID/AWREADY`, `control_WVALID/WREADY`, and the resulting
`tb2dut_ap_start`, rather than the unused root-level `start/ce/tb_continue`.
Before declaring a Vitis harness defect or building a replacement SystemVerilog
TB, reproduce a fresh dynamic 5x7 component from the same current commit and
co-simulation trace settings as the fixed 13x17 component. That controls for
source revision and trace configuration while retaining an input size known to
be small.

---

# Controlled co-simulation matrix (commit `24bbbb8`)

Three fresh components were created outside the repository and synthesized from
the same current source and toolchain. No DUT, FIFO, pragma, arithmetic, or
testbench source was changed.

| Component | C top | Image | Trace mode | RTL co-sim result |
|---|---|---:|---|---|
| `srcnn_axis_dataflow_cosim_case2_current_alltrace_5ns` | dynamic `srcnn_axis_dataflow_cosim_top` | 5x7 | `all`, `wave_debug=true` | stalled at `0 / 1 @ 113000`; stopped after sustained XSIM activity |
| `srcnn_axis_dataflow_cosim_13x17_porttrace_5ns` | fixed `srcnn_axis_dataflow_cosim_13x17_top` | 13x17 | `port` | stalled at `0 / 1 @ 113000`; stopped after more than 80 CPU seconds |
| `srcnn_axis_dataflow_cosim_case2_current_porttrace_5ns` | dynamic `srcnn_axis_dataflow_cosim_top` | 5x7 | `port` | **PASS**, `1 / 1 @ 524353000 ps` |

All three C simulations passed their OC4-equivalence checks; all three C
syntheses completed at estimated Fmax 273.97 MHz.

## What this proves

1. Full trace / wave-debug instrumentation can independently cause the Vitis
   auto co-sim run to stall, even for the small dynamic 5x7 test.
2. The fixed 13x17 top also stalls with the same current source and *port*
   trace, so full-trace instrumentation is not its sole cause.
3. The current dynamic 5x7 port-trace run passes. The remaining controlled
   discriminator is therefore the fixed top's reduced AXI-Lite control map:
   removing `height` and `width` reduces `control_AWADDR` from 6 to 5 bits.

The verified automatic RTL test is currently the dynamic 5x7 port-trace case.
The fixed 13x17 automatic co-sim remains blocked by the generated Vitis 2026.1
harness/control-interface combination. The correct next step is a standalone
SystemVerilog testbench for `srcnn_axis_dataflow_cosim_13x17_top`, using the
existing generated RTL and vectors, rather than changing Conv/DATAFLOW/FIFO
implementation or proceeding to Vivado integration.

---

# Fresh dynamic 13x17 port-trace gate (commit `7d8b5eb`)

A new component was created without reusing an older component or its build
cache:

```text
Component: srcnn_axis_dataflow_cosim_case3_dynamic_porttrace_5ns
Top:       srcnn_axis_dataflow_cosim_top
Part:      xck26-sfvc784-2LV-c
Clock:     5 ns
```

Its design flags were `-std=c++14 -DSRCNN_HLS_FIXED_POINT=1`; its testbench
flags added only `-DSRCNN_AXIS_DATAFLOW_TEST_CASE=3`. In particular, it did
not define `SRCNN_AXIS_DATAFLOW_USE_FIXED_13X17_TOP`.

Co-simulation used XSIM/Verilog with `trace_level=port`, `wave_debug=false`,
DATAFLOW profiling disabled, and FIFO sizing disabled.

| Gate | Result |
|---|---|
| C simulation | PASS: 221 AXIS words; final AXIS/DATAFLOW output exactly matches OC4 |
| C synthesis | PASS: estimated Fmax 273.97 MHz |
| RTL co-simulation | stalled at `0 / 1 [n/a] @ 113000` for more than 95 CPU seconds; stopped |

This is the missing matrix cell. Current dynamic 5x7 port-trace co-simulation
passes, while current dynamic 13x17 port-trace co-simulation stalls under the
same top, part, clock, and trace settings. The fixed 13x17 wrapper and its
5-bit AXI-Lite address map are therefore not the root cause.

No DUT/FIFO/pragma changes were made. Do not start a standalone SystemVerilog
TB yet. The next evidence must compare the actual AXI-Lite startup waveforms
for the passing dynamic 5x7 and failing dynamic 13x17 auto-generated harnesses,
then identify whether the 13x17 vector depth changes the generated AXI source,
AXIS source, or model-memory setup.

---

# Generated harness and port-trace comparison (current dynamic top)

This comparison used the same current dynamic top and port-trace components:

```text
PASS: C:\fpga\vitis-workspace\srcnn_axis_dataflow_cosim_case2_current_porttrace_5ns
FAIL: C:\fpga\vitis-workspace\srcnn_axis_dataflow_cosim_case3_dynamic_porttrace_5ns
Top:  srcnn_axis_dataflow_cosim_top
Part: xck26-sfvc784-2LV-c
Clock: 5 ns
```

No source, DUT, convolution, DATAFLOW, FIFO, or pragma change was made for
this analysis.

## Port-trace evidence

The passing WDB contains samples for the real generated DUT ports. Its control
sequence is:

| Time | Signal/event | Observation | Conclusion |
|---:|---|---|---|
| 112.5--112.6 ns | reset | `ap_rst_n` deasserts | DUT leaves reset |
| 117.5 ns | AXI-Lite AW | handshake at `0x10` | model pointer low-address write starts |
| 122.5 ns | AXI-Lite W | `0x00000000` | model pointer low value |
| 132.5 / 137.5 ns | AXI-Lite AW / W | address `0x14`, data `0x00000000` | model pointer high value |
| 147.5 / 152.5 ns | AXI-Lite AW / W | address `0x1c`, data `5` | height write |
| 162.5 / 167.5 ns | AXI-Lite AW / W | address `0x24`, data `7` | width write |
| 182.5 / 187.5 ns | AXI-Lite AW / W | address `0x00`, data `1` | `ap_start` write |
| 117.5 ns | input AXIS | `TVALID && TREADY` observed | input source is active |

No output handshake is expected before 200 ns. A direct `m_axi_model_mem` AR
handshake was not observed in the sampled 0--200 ns window; this does not
establish absence of model reads later in the run.

The failing WDB contains the same real port objects, but their sampled values
are blank (except reset metadata). Its expected RTL-output vector files are
empty and locked while its `xsimk.exe` process is still active. Therefore this
WDB is incomplete/unflushed and cannot supply valid evidence for an AXI-Lite,
m_axi, or AXIS protocol classification. In particular, it is not valid to
classify the run as A, B, C, or D from the blank wave values.

## Generated-file comparison

The generated UVM sequence/driver and wrapper sources that drive AXI-Lite,
m_axi model reads, and AXIS were byte-identical between the two components.
The common generated port trace Tcl was also byte-identical and explicitly
logs the DUT ports. The complete `model_mem` input vector is byte-identical:

```text
32,532 bytes
SHA-256: 02F083FD8EA69AAAB3DAC2064C25DD969FF594C45B232270B8F786D2617FAED0
```

The transaction metadata is well-formed in both cases. The only intentional
vector-size difference is frame size: 35 input/output AXIS words for 5x7 and
221 words for 13x17. The 13x17 file has one transaction, 221 inputs, 221
expected outputs, and model depth 8,129 with valid header and termination
markers.

The first material non-vector divergence occurs before XSIM executes:

| Generated artifact | PASS (5x7) | FAIL (13x17) |
|---|---|---|
| `run_sim.tcl` | DATAFLOW deadlock/FIFO sizing stages then XSIM | direct XSIM run |
| `fifo_monitor.v` | present and instantiated | absent |
| `fifo_sizing*.json/.tcl` | present | absent |
| `dataflow_monitor_API.tcl`, FIFO/process monitor files | present | absent |
| `*.autotb.v` | AXIS depth 35, FIFO monitor included | AXIS depth 221, no FIFO monitor |

This is a co-simulation execution-configuration difference, not a generated
DUT RTL, UVM-driver, model-vector, or startup-sequence difference. The two
components were therefore not fully controlled despite sharing the dynamic
top and `trace_level=port`: the passing component enabled DATAFLOW profiling
and FIFO sizing, while the failing component disabled both.

## Conclusion and next gate

The valid conclusion is **E0: incomplete comparison caused by an unfinished
failing XSIM run plus a material auto-harness configuration difference**. It
is not evidence of an SRCNN/DATAFLOW deadlock, and it does not establish
classification A--D.

Do not create another image-size experiment and do not alter the DUT. First
end the stale XSIM processes that still lock the failed run, then rerun the
existing dynamic 13x17 component with the same DATAFLOW profiling and FIFO
sizing settings as the passing dynamic 5x7 component. This is a co-simulation
configuration-only rerun; no C synthesis or design change is needed. If that
matched rerun still fails with a complete WDB, stop investigating the Vitis
automatic harness and build the independent SystemVerilog RTL testbench.

## Matched-configuration dynamic 13x17 re-run

The remaining harness configuration variable was tested on the existing
`srcnn_axis_dataflow_cosim_case3_dynamic_porttrace_5ns` component. No source,
RTL, C synthesis, DUT, FIFO, pragma, or vector was changed. Before relaunch,
stale XSIM processes from earlier abandoned runs were ended so they could not
hold the WDB or RTL-vector files open.

The component was changed only from:

```ini
cosim.enable_dataflow_profiling=0
cosim.enable_fifo_sizing=0
```

to the settings used by the passing dynamic 5x7 component:

```ini
cosim.enable_dataflow_profiling=1
cosim.enable_fifo_sizing=1
```

The co-simulation was launched with `vitis-run --mode hls --cosim`, preserving
XSim, Verilog, port trace, and the existing 13x17 test-case flag. Vitis
re-instrumented the test bench and generated the co-simulation files, then
XSIM started normally. It remained at:

```text
RTL Simulation : 0 / 1 [n/a] @ 113000
```

for about 94 CPU seconds with no transaction progress, and was then stopped.
The same stagnation therefore occurs with the passing component's DATAFLOW
profiling and FIFO-sizing flow enabled.

**Updated conclusion:** profiling/FIFO-sizing configuration is not the cause.
The dynamic 13x17 automatic co-sim failure remains reproducible after the only
material generated-harness configuration difference was eliminated. The
validated automatic comparison has now reached its useful limit: the next
verification stage is an independent SystemVerilog RTL testbench for
`srcnn_axis_dataflow_cosim_top`, using the existing 13x17 model/input/expected
vectors and explicit AXI-Lite, m_axi-read, and AXIS agents. Do not add further
Vitis auto-co-sim size/configuration experiments and do not modify the SRCNN
implementation.
