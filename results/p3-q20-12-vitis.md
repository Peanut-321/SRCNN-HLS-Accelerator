# Official Q20.12 Windows Vitis checkpoint

Date: 2026-10-11. Result: C simulation and independent 13x17 RTL verification
PASS; deployment synthesis and IP export complete. **Do not promote Q20.12
as the performance baseline: Conv1 MAC II regressed from 1 to 2.**

## Provenance and scope

- Branch: `optimize/official-q20-12`.
- Synthesized source: `23027ce` (full SHA in each component source manifest).
- Comparison: Q24.8 deployment reports from
  `fef80439290af7d418bf05b57a9b6fc95c485e15`.
- Vitis 2026.1, SW build 6497934 / HLS build 6493734.
- Standalone Vivado/XSim 2026.1, build 6511674.
- Part: `xck26-sfvc784-2LV-c`; target period: 5.000 ns.
- Design CFLAGS:
  `-std=c++14 -I<repo>/hls/include -DSRCNN_HLS_FIXED_POINT=1 -DSRCNN_HLS_OFFICIAL_Q20_12=1`.
- Small C testbench additionally defines
  `SRCNN_AXIS_DATAFLOW_TEST_CASE=3` and
  `SRCNN_AXIS_DATAFLOW_USE_FIXED_13X17_TOP=1`.

Both components were newly created. The three design sources are
`srcnn_axis_dataflow.cpp`, `srcnn_hls.cpp`, and `srcnn_hls_line_buffer.cpp`.
The diagnostic top is `srcnn_axis_dataflow_cosim_13x17_top`; the deployment
top is `srcnn_axis_dataflow_top` (fixed 255x255). Source manifests record
SHA-256 values before execution. Relative to the Q24.8 synthesis snapshot,
only `numeric_config.hpp` and `project_config.hpp` changed among design
sources/headers; all three design .cpp files are identical.

This gate changed no DUT, Conv, FIFO, pragma, padding or model layout.
It uses signed Q20.12 data and 31/37/44-bit accumulators under the official
model bounds documented in [the numeric contract](../docs/p3-q20-12-experiment.md).
Host quality measurements remain in
[the host checkpoint](p3-q20-12-host-checkpoint.md).

## Functional gates

| Gate | Result | Evidence |
|---|---|---|
| Vitis C Simulation, fixed 13x17 | PASS | 221 outputs exactly match the OC4 reference; zero errors; vendor HLS types |
| Diagnostic C Synthesis | PASS | Correct fixed 13x17 top, exit status 0 |
| Independent RTL, normalized synthetic fixture | PASS | 1 transaction; all 221 output words match independent integer Golden |
| Independent RTL, official model and Butterfly 13x17 input | PASS | 1 transaction; all 221 output words match independent integer Golden |
| RTL scoreboard negative control | PASS (rejected) | Deliberately corrupted Golden word 0 triggers a fatal mismatch |
| Deployment C Synthesis | PASS with II regression | Correct fixed 255x255 top, exit status 0 |
| Deployment IP export | Complete | IP component.xml and ZIP identify `srcnn_axis_dataflow_top` |

RTL validation reused the unchanged
`tests/rtl/srcnn_axis_independent_tb.sv`, compiled with `FIXED_13X17`.
It drives AXI-Lite control, an AXI model-memory responder, AXIS input and an
AXIS sink with periodic backpressure. This is independent RTL simulation,
not Vitis automatic UVM/autotb co-simulation. No forced DUT signals were used.

The official case uses the complete official 8,129-word model and the
top-left 13x17 crop of the normalized Butterfly input. The crop is treated
as its own replicate-edge frame; its Golden is recomputed for that frame,
not cropped from the 255x255 output. Golden generation uses the independent
integer reference with the same explicit numeric contract. Both cases have
zero reported saturation. The vector manifests record contract, counts and
hashes. Official float input/model SHA-256:

```text
input: b7b4aa699d5b3364cc297711b4ae85255a5b62fdf431859ce1d6b271905b7e0a
model: 836bd09cd2d386dd16530e797d5314adb832651be8910e150f68f2bb8d06a894
```

Both positive runs reported:

```text
transactions=1 inputs=221 outputs=221
model_reads=8129 unique=8129 AR_bursts=509
cycles=695135 start_to_rtl_done=694967
polled_done_cycle=695115 output_stall_cycles=13
simulation_time=3475675000 ps (3.475675 ms)
```

| Event | Cycle / simulation time |
|---|---|
| Reset released | 100 ns |
| Model pointer low/high written | 27 / 31; control offsets 0x10 / 0x14 |
| Start written / accepted | 35 / 36; accepted about 177.5 ns |
| First AXIS input handshake | 38; about 187.5 ns |
| First model AR handshake | 44; about 222.5 ns |
| Model reads complete | 8,736; about 43.683 us |
| First output | 172,086; about 860.428 us |
| RTL ap_done | 695,003; about 3.475013 ms |

All model words were addressed and read, all stream words were counted,
outputs matched bit-for-bit, TKEEP/TSTRB were 0xF, and only the last output
had TLAST. Payload stability under backpressure and no X/Z on checked
interfaces passed. No timeout or deadlock occurred. The negative run failed
at the first output with `expected=00000000 actual=ffffff94`, proving the
scoreboard actually checks DUT output.

This gate did not simulate the full 255x255 RTL or multiple transactions.
The earlier full-frame match was a host execution. Earlier Q24.8 RTL used
a different numeric fixture, so its elapsed cycles are not used as a
controlled speed comparison here.

## Deployment synthesis comparison

HLS applied 1.350 ns clock uncertainty, leaving a 3.650 ns scheduling
budget. Slack below is budget minus estimated period, not 5.000 minus
estimated period. These are HLS estimates, not routed timing closure.

| Metric | Q24.8 | Official Q20.12 |
|---|---:|---:|
| Target clock (ns) | 5.000 | 5.000 |
| Estimated top period (ns) | 3.650 | 3.650 |
| Top slack (ns) | 0.000 | 0.000 |
| Top latency minimum (cycles) | 509,109,788 | 947,330,909 |
| Top latency maximum (cycles) | 512,719,257 | 954,045,881 |
| Top interval minimum (cycles) | 509,109,789 | 947,330,910 |
| Top interval maximum (cycles) | 512,719,258 | 954,045,882 |
| BRAM_18K | 247 | 250 |
| DSP | 86 | 78 |
| LUT | 24,371 | 24,399 |
| FF | 9,287 | 9,792 |
| URAM | 0 | 0 |

The latency/interval ranges come directly from csynth XML. DATAFLOW
backpressure and loop-bound estimates make them conservative; do not
translate them into measured frame rate.

| Q20.12 stage | Latency min..max (cycles) | Interval min..max | Period / slack (ns) |
|---|---:|---:|---:|
| load_runtime_model (outside DATAFLOW) | 8,201 | 8,201 | 3.650 / 0.000 |
| run_streaming_core | 947,322,703..954,037,675 | 15,606,002..954,037,676 | 3.607 / +0.043 |
| axis_to_scalar | 65,027 | 65,026 | 1.707 / +1.943 |
| conv1_stream | 1,431,783..954,037,675 | 1,431,783..954,037,675 | 3.420 / +0.230 |
| conv2_stream | 15,606,001 | 15,606,001 | 3.442 / +0.208 |
| conv3_stream | 4,645,654..170,178,228 | 4,645,654..170,178,228 | 3.607 / +0.043 |
| scalar_to_axis | 65,027 | 65,026 | 2.133 / +1.517 |

All five expected streaming stages are synthesized. Model preloading remains
outside DATAFLOW; the three layers do not share a live model_mem read path.
FIFO width/depth remains input_pixels 32/64, conv1_features 32/128,
conv2_features 32/64 and output_pixels 32/64. No channel profiling run was
performed; these depths are from generated RTL, not observed maximum FIFO
occupancies.

## Conv1 performance regression

| Grouped Conv1 MAC metric | Q24.8 | Official Q20.12 |
|---|---:|---:|
| Output-channel groups | 16 | 16 |
| Inner kernel trip count | 81 | 81 |
| Inner loop II | 1 | **2** |
| Inner loop latency | 84 | 166 |
| Pipeline depth | 5 | 7 |
| Enclosing pipeline latency / interval | 86 / 82 | 168 / 164 |
| MAC pipeline DSP | 16 | 8 |
| Conv1 stage DSP | 17 | 9 |

The new MAC pipeline binds two `mul_32s_32s_64_1_1` instances, each using
four DSPs. Four logical OC4 lanes remain in source, but synthesis shares
operators under II=2. Fewer DSPs here accompany reduced throughput.

`HLS 200-880` reports a failed II=1 distance-1 carried dependence between
`accumulator_read_assign_write_ln18` and the `sums` select, involving a
31-bit local accumulator. Locations:
`arithmetic.hpp:18/20 -> srcnn_axis_dataflow.cpp:150`.
The XML marks loop `VITIS_LOOP_141_6_VITIS_LOOP_143_7` at cpp:142 as an II
violation, category `Memory Dependency`. The actual warning points to
accumulator feedback; it does **not** establish a weight-bank port conflict.
Whether saturation logic is the decisive feedback delay still needs
operation-level schedule inspection.

Conv2 kernel trip count remains 64, II=2, loop latency 130, pipeline depth
5, enclosing latency/interval 132/130 and DSP=64. Conv2 stage latency changes
from 15,540,976 to 15,606,001 cycles. There is no new Conv2 II warning.

Four Conv1 weight banks map to RAM_AUTO_1R1W, each 1,296x32 using four
BRAM_18K (16 total). Four 16x32 bias banks use zero BRAM, with 32 FF and
8 LUT per bank reported. Conv2 weights retain RAM_1WNR_AUTO_1R1W with 15
physical copies. The evidence does not justify changing Conv2 UNROLL.

## Warning and tool-error audit

The deployment synthesis CLI log contains 104 warnings:

| Code | Count | Meaning |
|---|---:|---|
| HLS 207-1655 | 13 | Vendor-header constexpr-if C++17 extension under C++14 |
| XFORM 203-561 | 2 | Padded loop bound estimates (263 / 259) |
| SYN 201-103 | 27 | Anonymous-namespace RTL identifier legalization |
| HLS 200-880 | 1 | New Conv1 accumulator carried dependence, detailed above |
| RTGEN 206-101 | 61 | 60 unused submodule AR outputs tied to zero; one synchronous active-low reset notice |

No timing-violation, noncanonical DATAFLOW or weight memory-port warning
was emitted. Nonnegative estimated slack does not cancel the II violation.
Standalone XSim elaboration also warns that `m_axi_model_mem_AWID` is
unconnected; the read-only testbench checks AWVALID/WVALID remain zero.

The first sandboxed C-sim launch failed when MSYS `cat` could not create a
signal pipe (Windows error 5). Running the same command with reviewed
permissions succeeded; no source change was needed.

Windows also displayed an `xcd.exe` access violation. Application events
identify Vitis `bin/unwrapped/win64.o/xcd.exe`, module
`lib/win64.o/xv_cd_server.dll`, exception 0xc0000005, offset 0x44e0e.
Events occurred after the main C-sim/synthesis commands completed.
Those commands returned 0, produced complete reports/RTL/IP, and the RTL
subsequently passed independent verification. The auxiliary crash remains
unresolved; this checkpoint does not claim it was fixed or caused by the DUT.

## Export and local evidence

The deployment IP is `srcnn_axis_dataflow_top`, with:

- `input_r` / `output_r`: AXI4-Stream, 32-bit TDATA, 4-bit TKEEP/TSTRB,
  TLAST and TVALID/TREADY.
- `m_axi_model_mem`: 32-bit data, 64-bit address, used for model reads.
- `s_axi_control`: 32-bit data, 5-bit address; ap_ctrl_hs control.
- Registers CTRL 0x00, GIER 0x04, IP_IER 0x08, IP_ISR 0x0C,
  model low 0x10, model high 0x14; no height/width registers.

Export ZIP (499,842 bytes):

```text
C:\Users\xzype\Documents\Codex\2026-10-08\windows-codex-mac-github-windows-codex\work\q20-12-vitis\deployment_255x255_5ns\hls\impl\ip\xilinx_com_hls_srcnn_axis_dataflow_top_1_0.zip
SHA-256: 49a349de115fff97b19de2cd9d7c81ba579ea0b109270fe0a9725ddad144939e
```

V++ also generated a diagnostic IP ZIP during small-top synthesis. It must
not be used as the 255x255 deployment IP.

Full logs, csynth RPT/XML, IP metadata/ZIP, vector and source manifests,
positive/negative RTL logs and WDBs are preserved locally under:

```text
Work:     C:\Users\xzype\Documents\Codex\2026-10-08\windows-codex-mac-github-windows-codex\work\q20-12-vitis
Evidence: C:\Users\xzype\Documents\Codex\2026-10-08\windows-codex-mac-github-windows-codex\outputs\q20-12-vitis
```

Evidence includes `summary.json`, `deployment-warnings.txt` and
`artifact-hashes.json`. Large tool outputs are intentionally outside Git.
Reproduction uses the commands in
[the experiment guide](../docs/p3-q20-12-experiment.md#vitis-and-independent-rtl-reproduction).
The HLS helper's generated configs were verified byte-identical to those
actually executed. Both RTL vector modes and all three RTL helper runs were
exercised; existing-directory rejection and script syntax checks passed.

## Decision and next gate

Keep Q24.8 as the existing deployment/performance baseline. Q20.12 has
functional 13x17 RTL evidence and a synthesized deployment artifact, but
loses Conv1 II=1 and has zero estimated top timing margin.

Next inspect the Conv1 accumulator feedback schedule and binding before
proposing a minimal structural fix under the same arithmetic contract.
Do not declare a real dependence false, disable saturation, change numeric
precision, or add Conv2 UNROLL to make this validation pass. Any future fix
needs the same independent bitwise RTL checks and a fresh II/resource
comparison. Full-frame/restart RTL coverage, implementation and board
validation remain outstanding. No Vivado integration or board work was
started in this gate.
