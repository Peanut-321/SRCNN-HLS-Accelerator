# Q20.12 full-frame and restart RTL validation

Date: 2026-10-11. Branch: `optimize/official-q20-12`.
**The fixed 255x255 deployment RTL passes two complete transactions without
a DUT reset**, including a changed second input and model. All 130,050
outputs match independent fixed-point Golden bit for bit.

## Scope and provenance

This extends the independent SystemVerilog AXI testbench, vector preparation,
and runner. DUT arithmetic, Conv stages, FIFO depths and pragmas are unchanged.
Existing RTL from the [Conv1 II=1 checkpoint](p3-q20-12-conv1-writeback.md)
is reused without another synthesis. Source code commit:
`5f76e4e0007db5f4b28841687273761777bc31a4`; documentation HEAD before this run:
`54a1d6c`. Component manifests record their preparation base and actual source
hashes; the runner verifies all source hashes before starting.

```text
hls/src/srcnn_axis_dataflow.cpp SHA-256:
81a31823916065de1beb7e5e715189be036d4f19f7a5235fe52d9e5ea1bd4672
Independent SV testbench SHA-256 used by these runs:
46093c2e78709a27eccf14c98f444dfbc325a1d5807143061968f983c720125e
```

Tool: standalone Vivado XSim 2026.1 build 6511674, default elaboration
optimization and `-debug typical`. The new runner initially tried unsupported
`xelab -O 3`; elaboration rejected it before simulation. The option was removed
and every reported run uses a fresh work directory and supported options.
RTL originated from Vitis HLS 2026.1, part `xck26-sfvc784-2LV-c`, target 5 ns,
with `SRCNN_HLS_FIXED_POINT=1` and `SRCNN_HLS_OFFICIAL_Q20_12=1`.

## Input, model and Golden

Frame one uses the official Butterfly input/model. The small test recomputes
replicate-edge Golden for the top-left 13x17 input crop. The full test uses
the validated Q20.12 V2 255x255 bundle and its independent integer Golden.

Frame two uses `input_raw = 4096 - input_raw` and changes model element 8128
(Conv3 bias) by one legal raw Q20.12 unit. Its Golden is recomputed by the
independent integer reference, retaining the 31/37/44-bit accumulator contract.
All second-frame accumulator/data saturation counters are zero. The bias
changes from raw 118 to 119, within the conservative quantized bound. All
65,025 full-frame inputs change; 65,022 Golden words change. The input,
model and Golden hashes differ between frames and are recorded in vector
manifests. No expected words come from the RTL under test.

Initial DUT reset is released at 100 ns and never reasserted. Both starts occur through AXI-Lite, with a
fresh model read on each transaction. Between frames only TB scoreboards and
the simulated external memory contents are updated; no DUT state is reset or
forced. Every frame checks model address coverage, input/output word counts,
bitwise Golden, TKEEP/TSTRB/TLAST, output stability under backpressure, defined
controls, DUT `ap_done`, and software-style done readback. Transfers outside
an active frame are rejected.

A fresh independent integer recomputation also rechecks all 65,025 first-frame
bundle Golden words. It matches exactly; its diagnostics are retained with
the evidence. This is separate from the RTL scoreboard comparison.

## Results

| Test | Result | Transactions | Inputs / outputs | Model reads / unique coverage |
|---|---|---:|---:|---:|
| Existing deterministic 13x17 fixture | PASS | 1 | 221 / 221 | 8,129 / 8,129 |
| Official 13x17 with changed second input/model | PASS | 2 | 442 / 442 | 16,258 / 16,258 |
| Corrupt second-frame Golden negative control | PASS: mismatch rejected after frame one PASS | First complete, second rejected | First second-frame output rejected | Model reload observed |
| Fixed 255x255 deployment RTL, changed second input/model | PASS | 2 | 130,050 / 130,050 | 16,258 / 16,258 |
| Existing host CTest suite | PASS | 19/19 tests | — | — |

The single-frame fixture has 478,077 start-to-RTL-done cycles and 478,487
total TB cycles. The two small frames each have 478,077 start-to-RTL-done
cycles; total is 956,950 cycles / 4.784750 ms simulated time. There are
509 model AR bursts and 13 stalled output cycles per small frame. The
negative control rejects second-frame output 0 at 2.951392500 ms:
expected `00000000`, actual `00000c78`. It proves the second-frame checks
execute after a complete first transaction.

### Full-frame measured cycles

| Event / count | Frame 1 | Frame 2 |
|---|---:|---:|
| Frame begins (`ap_rst_n=1`) | 24 | 149,884,364 |
| DUT start accepted | 36 | 149,884,376 |
| All model words loaded | 8,736 | 149,893,076 |
| First output handshake | 1,214,229 | 151,098,569 |
| DUT `ap_done` sampled | 149,884,126 | 299,768,466 |
| AXI-Lite done readback | 149,884,344 | 299,768,684 |
| Start-to-RTL-done latency | **149,884,090** | **149,884,090** |
| Input / output words | 65,025 / 65,025 | 65,025 / 65,025 |
| Model reads / unique addresses | 8,129 / 8,129 | 8,129 / 8,129 |
| Model AR bursts | 509 | 509 |
| Output cycles stalled by sink | 3,825 | 3,825 |

Cycle numbers are global TB counters except the explicit latency row.
The model reload takes 8,700 cycles from accepted start in each transaction.
The start-to-start interval in this sequential host-style TB is 149,884,340
cycles, including its done polling and setup; it is not the minimum HLS
interval. Each measured DUT latency is 749.420450 ms at the simulated 5 ns
clock. Total TB duration is 299,768,704 cycles / 1,498.843520 ms, including
initial reset, setup and final checks. Total output backpressure is 7,650
cycles; output data and sidebands stay stable throughout each stall.

XSim `run all` wall time is **1:23:14**, peak reported memory 242.906 MB.
The final log reports:

```text
PASS independent RTL: transactions=2 inputs=130050 outputs=130050 model_reads=16258 unique=16258 AR_bursts=1018 cycles=299768704 start_to_rtl_done=149884090 polled_done_cycle=299768684 output_stall_cycles=7650 time=1498843520000
```

No timeout, unknown control, output mismatch, unexpected model write,
extra transfer, sideband error, or output-stability assertion occurred.
Elaboration emits the expected `VRFC 10-3645` warning for the unconnected
model `AWID` output in the read-only TB instance. The scoreboard asserts that
model AWVALID/WVALID remain zero and rejects any model write.
The independent harness uses a single outstanding read burst and periodic
output stalls; it does not cover every possible AXI interleaving or DDR
stall pattern. Actual board throughput cannot be inferred from simulator
wall time or these idealized memory responses.

## Evidence and limitations

Work root (outside Git):
`C:\Users\xzype\Documents\Codex\2026-10-08\windows-codex-mac-github-windows-codex\work\q20restart`.
Separate `rtl-small-one`, `rtl-small-two-v2`,
`rtl-small-negative-second`, and `rtl-full-two` directories contain source/
RTL/vector manifests, compile/elaboration/simulation logs and port WDBs.
Vectors are in `vectors-small` / `vectors-full`; `restart-vector-check.json`
records their changes. No build directory, vectors or WDB is committed.
Consolidated logs/manifests and a hashed evidence inventory are retained in
`outputs\q20-12-full-frame-rtl` under the same workspace; WDBs remain in the
original work directories. The completed full-frame WDB is 189,436,059 bytes.
Its SHA-256 is
`d16edbb54fe34fddad1d1aeb7a0951562193fd85743f0bdf867839fabf710296`.

This is functional RTL verification using an independent AXI harness, not
the failing Vitis automatic UVM harness. It does not prove routed timing,
DMA/PS integration or board performance. HLS estimated top slack remains
zero under the existing uncertainty setting. Q20.12 remains opt-in; the
existing Q24.8 overlay/default is not replaced. No board integration begins
as part of this validation.

The full-frame/restart functional gate is now complete. The next Q20.12 gate
is integration and routed timing verification with the matching numeric
contract, followed by a Q20.12-specific host/board runner and board tests.
Keep those artifacts separate from the existing Q24.8 baseline; successful
RTL simulation does not promote the candidate to the default overlay.
