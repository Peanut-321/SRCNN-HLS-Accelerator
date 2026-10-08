# P0b KV260 Vivado dummy-overlay checkpoint

Date: 2026-10-09  
Branch: `deploy/vivado-pynq`  
Status: bitstream-ready, board-pending

## Scope

This checkpoint deploys the independent `axis_dummy_top` HLS IP only. It does
not instantiate or modify the SRCNN OC4 core.

```text
PS DDR -> AXI DMA MM2S -> axis_dummy_top -> AXI DMA S2MM -> PS DDR
```

`axis_dummy_top` is a 32-bit AXI4-Stream kernel that emits `input + 1`, with
AXI-Lite `length` and `ap_ctrl_hs` control.

## Block Design

- Board/part: Kria KV260 / `xck26-sfvc784-2LV-c`.
- DMA: simple mode (scatter-gather disabled); both MM2S and S2MM enabled;
  32-bit stream data width.
- Memory path: both DMA AXI memory masters use an AXI SmartConnect to
  `zynq_ultra_ps_e_0/S_AXI_HPC0_FPD`.
- Control path: AXI DMA and dummy AXI-Lite control are mapped through the PS
  `M_AXI_HPM1_FPD` path.
- The MM2S DMA interrupt is connected to PS `pl_ps_irq0`; software may poll
  the DMA channels for the initial PYNQ bring-up.
- HLS synthesis target is 5.0 ns. The implemented PS PL clock is 187.498 MHz:
  the KV260 board reference clock/divider combination did not yield an exact
  200 MHz PS PL clock, so the board clock is safely slower than the HLS target.

## Reproduction

1. Use Vivado 2026.1 and install the KV260 board files.
2. Add the directory containing the exported `axis_dummy_top` IP to the Vivado
   IP repository list.
3. Create/open a KV260 project and source
   `vivado/p0b/design_1_recreate.tcl` from the Vivado Tcl Console.
4. Generate output products and the HDL wrapper, then run synthesis,
   implementation, and bitstream generation.

The generated Tcl deliberately does not embed a developer-specific IP
repository path; it requires the repository step above.

## Generated local delivery bundle

The non-Git binary handoff is retained on the Windows tool machine at:

```text
C:\Users\aeroc\srcnn_vivado_p0b\deliverables\axis_dummy_overlay
```

It contains same-stem PYNQ files `axis_dummy_overlay.bit` and
`axis_dummy_overlay.hwh`, the generated BD Tcl, and implementation reports.
The bitstream is intentionally not committed to Git.

## Boundaries

No KV260 board transfer has been run. P0c remains responsible for overlay
load, contiguous buffers, cache maintenance, data checking, repeated transfer
tests, and bandwidth measurement.
