# P2.6: KV260 SRCNN AXIS system implementation

## Provenance and scope

Windows validation on 2026-10-10 uses repository checkpoint
`178ecad60b2e469ebe92fb40936ecf4e02ee9006` on
`deploy/srcnn-axis-dataflow`. The exported HLS deployment IP was built from
source checkpoint `fef80439290af7d418bf05b57a9b6fc95c485e15`.
The independent 13x17 AXI RTL testbench gate and the fixed 255x255 HLS
synthesis/export gate are recorded in `p2_5-axis-dataflow-vitis.md`.

This gate integrates the fixed `srcnn_axis_dataflow_top` IP with the KV260 PS
and AXI DMA. No DUT, convolution, numerical type, padding, model layout,
FIFO depth or HLS pragma was changed. Board programming and measured FPS
are outside this gate.

Tool: Vivado 2026.1, build 6511674. Part: `xck26-sfvc784-2LV-c`.
Installed board definitions: KV260 SOM 2.0 with KV260 carrier 2.0;
effective combined board part:
`xilinx.com:kv260_som_som240_1_connector_kv260_carrier_som240_1_connector:part0:2.0`.
The official `preset_s4.xml` enables the PS DDR controller.

HLS IP archive SHA-256:
`2E832D8E2BCEBC681C36155D29A8488D58E26B3FFC99194B273DDC1009928FC8`.

## System connections and register map

```text
PS M_AXI_HPM0_FPD -> control SmartConnect -> DMA AXI-Lite / SRCNN AXI-Lite
DMA MM2S -> SRCNN input_r -> SRCNN output_r -> DMA S2MM
DMA MM2S memory / DMA S2MM memory / SRCNN model_mem
    -> memory SmartConnect -> PS S_AXI_HP0_FPD
```

The AXIS path is 32 bits; DMA memory ports and HP0 are 64 bits. The HLS
model memory master is 32-bit data / 64-bit address. All PL logic uses the
same PS PL0 clock. PL0 is configured to 200 MHz from RPLL; the generated
PS configuration reports 199.998001 MHz, while the generated timing XDC
explicitly constrains `clk_pl_0` to **5.000 ns**.

DMA uses simple mode (SG disabled), 64-bit addresses, DRE on both paths,
16-beat maximum bursts, and a 26-bit buffer-length register. A frame is
65,025 words / 260,100 bytes, exceeding the default 14-bit length capacity.
The configurable 26-bit limit is documented in
[AMD AXI DMA PG021](https://www.amd.com/content/dam/xilinx/support/documents/ip_documentation/axi_dma/v7_1/pg021_axi_dma.pdf).

| Control block | Base address | Assigned range |
|---|---|---|
| AXI DMA | `0xA0000000` | 64 KiB |
| SRCNN | `0xA0010000` | 64 KiB |

SRCNN register offsets: CTRL `0x00`, GIER `0x04`, IER `0x08`, ISR `0x0c`,
model pointer low/high `0x10` / `0x14`. The fixed top has no height/width
registers. The model has 8,129 32-bit elements / 32,516 bytes.

PS `pl_resetn0` drives the active-low external reset input of proc_sys_reset;
generated reset parameter `C_EXT_RESET_HIGH=0` is verified in HWH.
IRQ concat bits 0/1/2 are DMA MM2S, DMA S2MM, SRCNN respectively, connected
to PS `pl_ps_irq0`; the generated PS interrupt-input count is 3.

Memory address assignment exposes PS DDR_LOW, DDR_HIGH and QSPI decode
windows to the three memory masters. These decode ranges are not physical
RAM capacity. The host must use valid allocated DDR buffers and physical
addresses for input, output and model.

## Implementation gates

**PASS: Block Design validation, synthesis, routed 5 ns timing, bitstream,
and XSA export with the bitstream included.**

| Routed check | Result |
|---|---|
| Setup WNS / TNS | +0.077 ns / 0.000 ns |
| Hold WHS / THS | +0.011 ns / 0.000 ns |
| Pulse-width slack / total violation | +1.000 ns / 0.000 ns |
| Setup / hold failing endpoints | 0 / 0 (69,666 endpoints each) |
| Clock | clk_pl_0, 5.000 ns / 200.000 MHz |
| No-clock / unconstrained internal endpoints | 0 / 0 |
| Other check_timing categories | All zero |
| Routed networks / routing errors | 35,164 / 0 |
| DRC errors / critical warnings | 0 / 0 |
| Methodology violations | 0 |

The worst setup path is inside Conv3, from `line_buffer_1_U` BRAM to
`line_buffer_2_U` BRAM. Reported data-path delay is 3.922 ns (2.593 ns
logic, 1.329 ns routing), with five logic levels. The worst hold path is
in `model_mem_m_axi_U`, between an address register and the burst request
register. Timing margin is positive but small; this is closure at the
specified 5 ns constraint, not evidence for a higher clock or board FPS.

| Resource | Top synthesis | Routed system | Device usage |
|---|---:|---:|---:|
| LUT | 18,108 | 15,739 | 13.44% |
| FF | 16,995 | 16,456 | 7.03% |
| BRAM tiles | 97 | 97 | 67.36% |
| RAMB36 / RAMB18 | 93 / 8 | 93 / 8 | 194 equivalent 18-Kib blocks |
| DSP | 86 | 86 | 6.89% |
| URAM | 0 | 0 | 0% |

The routed SRCNN cell itself uses 10,677 LUT, 8,428 FF, 91 RAMB36,
6 RAMB18 and 86 DSP. The full system additionally includes DMA and
SmartConnect. Vivado's actual optimized physical-memory counts are
different from the earlier HLS estimates; do not compare a 36-Kib tile
count directly with HLS BRAM_18K.

The initial run was interrupted by shutdown during `init_design`, after all
OOC IP synthesis and top synthesis completed. Its logs are preserved.
The resumed run resets only `impl_1`, retains synthesis checkpoints, and
uses the same generated RTL, IP and 5 ns constraints.

## Warnings and limits

The routed default DRC contains 162 **warning-level** advisories:
32 DPIP-2 (DSP input registers), 42 DPOP-3 (DSP output registers),
84 DPOP-4 (DSP multiplier registers), and two each REQP-1934/1935
(NO_CHANGE RAM collision advisories). The four memory advisories are in
the vendor DMA MM2S/S2MM XPM FIFOs, not SRCNN line buffers. They are not
proof that a collision occurred. No primitive or write-mode changes were
made; integrated DMA behavior remains part of the later platform test.

The synthesis and implementation run logs contain 277 warning lines:
117 Synth 8-7071, 100 Synth 8-7129, 21 Synth 8-6014,
12 Synth 8-7023, 9 Synth 8-13161, 8 Synth 8-3848,
3 Synth 8-689, and one each Vivado 12-508, Vivado_Tcl 4-921,
Power 33-332, one Project 1-153, and three unnumbered `WARNING::74` lines.
These cover unused generated-IP ports / removed logic,
PS wrapper widths, an empty generated CDC waiver after optimization,
and uncertain vectorless reset activity for power analysis. The routed
timing and methodology checks above independently pass. Full warning
lines are saved in `tool-warning-lines.txt`; this count excludes initial
BD creation notices and DRC advisory instances. Power estimates are not
measured board power. During generated hardware-definition creation,
Project 1-153 changes its temporary default device to the board's K26 part,
and the memory-info helper emits `WARNING::74` about K26 recognition.
The routed design, final bitstream header, and HWH all identify
`xck26-sfvc784-2LV-c`; bitstream and XSA generation complete successfully.
No model update relies on updatemem; parameters are read from runtime DDR.

- Block Design width-propagation warnings are retained in the logs. DMA
  S2MM is explicitly 64-bit memory / 32-bit stream, and HP0 is 64 bits.
- HLS ARLOCK is two bits while SmartConnect AXI4 uses one. The exported
  HLS RTL assigns ARLOCK and AWLOCK to zero; dropping the upper zero bit
  loses no lock request. HP0 AWUSER/ARUSER defaults cover unused user bits.
- Vivado recommends migrating xlconstant/xlconcat utility IPs to inline HDL.
  This supported-IP notice does not change this design's current behavior.
- The initial BD runner attempted to set two read-only parameters (PS IRQ
  count and reset polarity), generating warnings. Actual propagated values
  are 3 and 0. The reproduction runner lets connectivity derive them and
  checks the resulting values explicitly.
- RPLL is also used by preset peripherals including DP audio. A driver
  that retunes that PLL can affect PL0. Board boot/clock behavior still
  requires a separate platform check; timing closure alone does not prove it.

## Reproduction and artifacts

Project directory:
`C:\fpga\vivado-srcnn-axis-dataflow-255x255-5ns`.
Exported HLS IP directory:
`C:\fpga\vitis-workspace\srcnn_axis_dataflow_deployment_current_255x255_5ns\hls\impl\ip`.
Reports and generated deployment files:
`C:\Users\xzype\Documents\Codex\2026-10-08\windows-codex-mac-github-windows-codex\outputs\vivado-255x255`.

From the repository in PowerShell, use a new project directory:

```powershell
& .\hls\scripts\run_srcnn_axis_vivado.ps1 `
  -ProjectDir C:\fpga\vivado-srcnn-axis-dataflow-reproduction `
  -IPDir C:\fpga\vitis-workspace\srcnn_axis_dataflow_deployment_current_255x255_5ns\hls\impl\ip `
  -ResultDir C:\fpga\vivado-srcnn-axis-dataflow-reproduction-results
```

To resume an interrupted implementation with no Vivado process running,
use `-Stage implement -RestartInterruptedImplementation` and the existing
ProjectDir. The runner archives interrupted implementation files before
resetting that run. Normal `-Stage implement` resumes without forcing a reset.
Existing projects are never replaced in `all` / `bd` mode.

Only reproduction scripts and this Markdown are committed. Generated IP,
Vivado project, reports, checkpoints, bitstream and XSA remain outside Git.

### Exported artifacts

All three files are in the reports directory above and use matching
`srcnn_axis_255x255` filenames.

| File | Bytes | SHA-256 |
|---|---:|---|
| srcnn_axis_255x255.bit | 7,797,911 | FED3B1059333BD1D42255A5668A10854573B427227DF95A59AB3204FCE960415 |
| srcnn_axis_255x255.hwh | 372,116 | 00CD8212361B850514FD85B3E3454FEC13275A136008D58F6FD8C56453C5710A |
| srcnn_axis_255x255.xsa | 2,060,979 | 517C30EB3BEFD5846597B35504C05DE449EE227FF1231C22732DC536B651C340 |

The XSA archive's bitstream and top HWH have SHA-256 values identical to
the delivered standalone files. Its drivers identify the fixed deployment
IP. Full reports, OOC/implementation logs, board definitions, HWH parameter
checks, input/artifact manifests and executed-script snapshots are retained
with these files. The routed checkpoint remains in the Vivado project.

An initial runner generated a standalone bitstream successfully, then XSA
export failed because Vivado could not find a managed-run bitstream.
The runner now completes `impl_1` through `write_bitstream`; recovery used
the existing routed checkpoint, with no resynthesis or rerouting. XSA
export subsequently passed with `-include_bit`.
The final PowerShell/Tcl runner was then executed in normal `implement`
mode against the completed project. It exited 0 with GATE_SYNTH_PASS,
GATE_ROUTE_PASS and GATE_BITSTREAM_PASS, without launching any synthesis,
implementation or bitstream run. Its logs are in `runner-validation`.

## Next gate

Prepare the host deployment test against the actual KV260 software image
and boot/PL clock configuration. Use independent allocated input/output
buffers (260,100 bytes each) and the model buffer (32,516 bytes), start
the receive DMA before producing output, and compare a full-frame result
against the fixed-point golden reference. Check DMA status/timeouts,
model pointer, cache synchronization, TLAST completion and repeatability
before measuring throughput. Board access, programming, Linux/PYNQ
integration and measured FPS have not been performed in this gate.
