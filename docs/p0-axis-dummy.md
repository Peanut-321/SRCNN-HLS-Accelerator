# P0 AXI4-Stream dummy deployment probe

Date: 2026-10-08  
Branch: `deploy/axis-dummy`  
Parent tag: `hls-conv1-oc4-5ns`  
Status: Mac host gate passed; Vitis export, Vivado implementation, and board
test pending

## Purpose

This component isolates the Vitis/Vivado/PYNQ deployment chain from SRCNN. It
must pass before the OC4 core receives a deployment wrapper, so AXI, DMA,
clock/reset, and TLAST failures are not confused with convolution failures.

It does not modify or instantiate the frozen OC4 compute core.

## Interface contract

Top function:

```text
axis_dummy_top
```

Ports:

```text
input   32-bit AXI4-Stream slave
output  32-bit AXI4-Stream master
length  AXI4-Lite control register
return  AXI4-Lite ap_ctrl_hs control
```

For exactly `length` input words, the kernel emits exactly `length` outputs:

```text
output[i].data = input[i].data + 1 modulo 2^32
output[i].keep = 0xF
output[i].strb = 0xF
output[i].last = 1 only when i == length - 1
```

The kernel generates TLAST from `length`; it does not trust an early input
TLAST. A non-positive length accesses neither stream.

## Mac host gate

The host build uses a small queue-backed compatibility type. Vitis C simulation
uses the real vendor `hls::stream<ap_axiu<32,0,0,0>>` through the same header.

```text
make host-axis-dummy
```

Covered lengths are 0, 1, 5, and 257. The test checks data, unsigned 32-bit
wraparound, exact word count, TKEEP, TSTRB, TLAST, and complete input
consumption.

Current result:

```text
1/1 CTest PASS
```

## Windows Vitis gate

From a shell where Vitis HLS is available:

```text
git fetch origin --tags
git switch deploy/axis-dummy
git pull --ff-only
make vitis-axis-dummy-export SRCNN_HLS_PART=xck26-sfvc784-2LV-c SRCNN_HLS_CLOCK_NS=5
```

The Tcl flow runs C simulation, C synthesis, and IP export. If GNU Make is not
available, run the equivalent script directly after setting
`SRCNN_HLS_PART=xck26-sfvc784-2LV-c` and `SRCNN_HLS_CLOCK_NS=5`:

```text
hls/scripts/run_axis_dummy_hls.tcl
```

Save:

- Vitis version and command log;
- C-simulation result;
- `csynth.rpt`, including loop II and 5 ns slack;
- exported IP location and component metadata;
- warnings about AXI sidebands or interface synthesis.

## Vivado P0b gate

Build a separate overlay containing:

```text
Zynq UltraScale+ MPSoC
  MM2S -> AXI DMA -> axis_dummy_top -> AXI DMA -> S2MM
  AXI-Lite control from PS to DMA and dummy
  common clock/reset for the streaming path
```

Validate addresses, reset polarity, clock domains, stream directions, DMA
memory connections, and interrupts if used. Run validation, synthesis,
implementation, timing, and bitstream generation. Save the BD Tcl, `.bit`,
`.hwh`, utilization report, timing summary, address map, and DRC result.

P0b is not complete merely because a bitstream file exists: post-
implementation timing must pass and blocking DRCs must be absent.

## Board P0c gate

When a KV260 is available, use physically contiguous PYNQ buffers and test
lengths including 1, a non-power-of-two length, and 65,025 words. Check exact
data, transfer completion, TLAST behavior, timeout recovery, at least 100
consecutive transfers, and repeated overlay reload without reboot.

Measure sustainable DMA bandwidth separately. Until this test runs, the branch
must be described as bitstream-ready or board-pending, never board-validated.
