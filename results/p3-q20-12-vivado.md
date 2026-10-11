# Q20.12 KV260 integration and routed implementation

Date: 2026-10-11. **The independent Q20.12 KV260 design passes routed
5 ns setup, hold, pulse-width, timing coverage and DRC checks. The candidate
bitstream, HWH and XSA are exported and verified.** Branch:
`optimize/official-q20-12`. Board validation remains pending.

## Provenance and scope

Repository checkpoint before integration: `18281e76b9070b6801620a8548c7ae8b72f47db5`.
DUT source checkpoint: `5f76e4e0007db5f4b28841687273761777bc31a4`.
The [full-frame independent RTL gate](p3-q20-12-full-frame-rtl.md) passes two
complete 255x255 transactions with no reset and changed second input/model.
This integration reuses that deployment IP; no HLS source, type, arithmetic,
padding, FIFO or pragma is changed, and HLS is not rerun.

Numeric profile: `official_q20_12_v1`, signed 32-bit Q20.12 with the established
31/37/44-bit accumulators. This candidate is separate from the Q24.8 baseline.
The existing Q24.8 host runner still checks its original bit/HWH hashes and
V1 contract; it is not changed to accept this candidate.

```text
DUT srcnn_axis_dataflow.cpp SHA-256:
81a31823916065de1beb7e5e715189be036d4f19f7a5235fe52d9e5ea1bd4672
Exported Q20.12 IP archive SHA-256:
ac79f070bd1a4fc3458617628802ae25855c5e106fbac14b9a01c916aceec965
```

The exported IP has 59 Verilog/data files byte-identical to synthesized RTL.
Its top has only the known appended vendor simulation deadlock/kernel monitor
blocks. Their includes are under synthesis translate-off and their unused
constant monitor flags are optimized away. The Q20.12 wrapper verifies this
specific difference; arbitrary exported RTL differences are rejected.
All HLS source-manifest hashes still match current files. The preparation
manifest names its base revision; actual source hashes identify the repaired
DUT above. Tool: Vivado 2026.1 build 6511674; part `xck26-sfvc784-2LV-c`.

## Integration

The established KV260 PS/simple-DMA integration Tcl is reused unchanged in
a new project. Board is KV260 SOM 2.0 plus KV260 carrier 2.0, with the combined
board preset enabling PS DDR. PL0 requests 200 MHz from RPLL; generated PS
configuration reports 199.998001 MHz. The actual routed `clk_pl_0` constraint
is 5.000 ns, with rise/fall at 0.000/2.500 ns.

```text
PS HPM0 -> control SmartConnect -> DMA AXI-Lite / SRCNN AXI-Lite
DMA MM2S -> SRCNN input_r -> SRCNN output_r -> DMA S2MM
DMA read/write + SRCNN model_mem -> memory SmartConnect -> PS HP0 DDR
```

Stream ports remain 32 bits; DMA memory and HP0 are 64 bits; model memory
is 32-bit data / 64-bit address. Simple DMA has SG disabled, DRE enabled,
16-beat bursts and 26-bit transfer-length capacity. Input/output buffers
are each 260,100 bytes; the model buffer is 32,516 bytes.
DMA control base is `0xA0000000`; SRCNN control base is `0xA0010000`.
Fixed top registers remain CTRL/GIER/IER/ISR at 0/4/8/12 and model pointer
low/high at 16/20. All PL logic shares PL0. Active-low reset polarity and
three PS IRQ inputs are checked by BD validation.

**Block Design validation, OOC/top synthesis and routing: PASS.** Default
Vivado implementation was sufficient; no source repair, new false path,
clock relaxation or additional physical optimization experiment was needed.

## Routed timing and resources

| Check | Result |
|---|---:|
| Target period | 5.000 ns |
| WNS / TNS | +0.107 / 0.000 ns |
| WHS / THS | +0.010 / 0.000 ns |
| WPWS / TPWS | +1.000 / 0.000 ns |
| Setup failing / checked endpoints | 0 / 71,186 |
| Hold failing / checked endpoints | 0 / 71,186 |
| Pulse-width failing / checked endpoints | 0 / 21,523 |
| Timing coverage | All 12 `check_timing` categories zero |
| Unrouted nets / routing errors | 0 / 0 |
| DRC errors / critical warnings | 0 / 0 |
| Methodology checks found | 0 |

The worst setup path is now in Conv2: `input_value_reg_6388_reg[4]` through
the 32x32 multiplier DSP chain to `tmp_product_carry__4_i_7__5_psdsp`.
Data delay is 4.692 ns: 3.270 ns logic and 1.422 ns routing, nine logic
levels. This is a measured routed critical path; Conv2 throughput remains
unchanged by this integration gate. Worst hold is in memory SmartConnect's
model-master S02 address skid path, `ar_reg_stall/m_vector_i_reg[1100]` to
the transaction-regulator `skid_buffer_reg[1100]`: 0.250 ns data delay,
0.113 ns logic plus 0.137 ns routing. Both pass with the margins above.

| Resource | Q20.12 complete design | SRCNN alone | Q24.8 complete baseline |
|---|---:|---:|---:|
| LUT | 15,986 | 10,930 | 15,739 |
| FF | 17,546 | 9,517 | 16,456 |
| RAMB36 | 93 | 91 | 93 |
| RAMB18 | 9 | 7 | 8 |
| BRAM tile equivalents | 97.5 | 94.5 | 97 |
| BRAM18 equivalents | 195 | 189 | 194 |
| DSP | 86 | 86 | 86 |
| URAM | 0 | 0 | 0 |

Compared with the preserved Q24.8 implementation, Q20.12 adds 247 LUT,
1,090 FF and one RAMB18 across the complete design. BRAM tile utilization
is 67.71% of 144; LUT/FF/DSP utilization is 13.65%/7.49%/6.89%.
These are Vivado routed counts, not HLS resource estimates. The comparison
uses separate default implementation runs, so small placement-dependent
differences are not attributed exclusively to numeric width.

## Warnings and limits

The default routed DRC has 208 warning advisories: DPIP-2 = 64,
DPOP-3 = 56, DPOP-4 = 84, REQP-1934 = 2 and REQP-1935 = 2.
The first three recommend additional DSP input/output/multiplier registers;
they do not invalidate the measured timing result. The four NO_CHANGE
collision advisories are in vendor DMA FIFOs, not SRCNN line buffers.
No primitive, write mode, Conv schedule or pragma is changed to suppress them.
Synthesis/implementation logs contain 277 warning lines: Synth 8-7071 =
117, Synth 8-7129 = 100, Synth 8-6014 = 21, Synth 8-7023 = 12,
Synth 8-13161 = 9, Synth 8-3848 = 8, Synth 8-689 = 3, and one each
Vivado 12-508, Vivado_Tcl 4-921, Power 33-332 and Project 1-153, plus
three unnumbered `WARNING::74` lines. These cover unused generated-IP ports,
removed logic, wrapper widths, an empty generated CDC waiver, uncertain
vectorless reset activity and K26 memory-info helper notices. The final
device, timing coverage, default DRC and methodology checks pass independently.
Counts exclude initial BD notices and the individual DRC advisory instances.
Full lines are retained in `tool-warning-lines.txt` in the result directory.

BD port-width notices remain in the logs. HLS ARLOCK/AWLOCK are tied to zero,
so truncating the unused upper lock bit loses no request; DMA/HP0 widths are
verified in the actual HWH. Utility-IP migration recommendations do not alter
this run. Runtime model data comes from DDR; no `updatemem` flow is required.

PS preset RPLL also serves peripherals including DP audio. A software driver
that retunes it can affect PL0; boot/clock behavior still needs platform
validation. Routed timing and vectorless power analysis do not establish
measured board throughput or power. No board is programmed in this gate.

## Reproduction and evidence

Project: `C:\fpga\q20-vivado-5ns`.
Verified component:
`C:\Users\xzype\Documents\Codex\2026-10-08\windows-codex-mac-github-windows-codex\work\q20mac2\deployment_255x255_5ns`.
Results:
`C:\Users\xzype\Documents\Codex\2026-10-08\windows-codex-mac-github-windows-codex\outputs\q20-12-vivado-5ns`.

For a new project, run from the repository in PowerShell:

```powershell
& .\hls\scripts\run_axis_q20_12_vivado.ps1 `
  -Component C:\fpga\q20-12-validation\deployment_255x255_5ns `
  -ProjectDir C:\fpga\q20-vivado-reproduction `
  -ResultDir C:\fpga\q20-vivado-reproduction-results
```

Use an existing verified component and short project path. For resumption,
use `-Stage implement` with the original project/result directories. The
wrapper checks that the creation manifest belongs to the same project/IP
and that all IP file hashes still match. It rejects a diagnostic top or a
mismatched project checkpoint; both negative guards have been exercised.

After the underlying timing/DRC gate, the wrapper additionally requires all
12 zero `check_timing` categories, a 5.000 ns clock, and nonnegative setup,
hold and pulse-width slack with zero failing and nonzero checked endpoints
before naming artifacts
`srcnn_axis_q20_12_255x255.bit/.hwh/.xsa`. A separate profile/hash manifest
labels them as a routed candidate with `board_tested=false`.

The initial run invokes the existing base runner directly after manual
source/IP checks and passes BD/synthesis/route/bitstream gates. The Q20.12
wrapper then runs in `implement` mode against the completed project and
exits 0 with `GATE_Q20_CANDIDATE_PASS`. Its log confirms no synthesis,
implementation or bitstream run was launched; it refreshes reports and
reexports XSA from the same managed bitstream. Both negative preflight
guards pass before starting Vivado. All source hashes still match.

## Exported candidate

All files below are in the result directory above. Only this isolated
directory contains Q20.12 candidate aliases; the original Q24.8 bit/HWH/XSA
hashes were rechecked and remain unchanged.

| File | Bytes | SHA-256 |
|---|---:|---|
| srcnn_axis_q20_12_255x255.bit | 7,797,911 | 37da5817afc486920af08a6376fc033912f18c6b2f2cc4474182f91388c0b708 |
| srcnn_axis_q20_12_255x255.hwh | 372,116 | f1a32497485ecd6903ab28be9796e9a4e985713807579e1f1ed1cf112aa39ab5 |
| srcnn_axis_q20_12_255x255.xsa | 2,110,891 | 1b84481867a332248fbe82c5d962460fd3ab9ffa27201f77796f999822ba73be |

The XSA's embedded bitstream and top HWH match the standalone hashes.
The bitstream header identifies `xck26-sfvc784-2LV-c`. Actual HWH parameters
confirm the fixed top, model-memory width/address, register offsets,
DMA burst/DRE/SG/length/width configuration, DDR enable, three interrupts
and active-low reset. There are no height/width registers. The reexported
XSA's archive hash differs from the first export due to export metadata;
the bitstream and HWH hashes remain identical. The final hashes above are
the candidate manifest's hashes.

`q20-overlay-manifest.json` binds `official_q20_12_v1`, 12 data fractional
bits, 31/37/44 accumulator bits and the actual artifact hashes, with
`board_tested=false`. Evidence includes `candidate-verification.json`,
`q20-input-implement.json`, project-creation IP hashes, full warning lines,
the monitor-only top diff, negative-guard results and both run logs.
Executed script snapshots and the routed DCP are retained locally.

## Next gate

The subsequent handoff audit found Aero's `deploy/vivado-pynq` checkpoint
`8b87af8`, which already supplies independently rebuilt dual-format packages
and a profile-aware board orchestration wrapper. Do not create another runner
or repeat HLS/Vivado just to recover missing binary files. Its Q20.12 package
uses frozen source `18281e7`; all 63 exported Verilog/data files are byte-identical
to this Windows IP, despite different ZIP packaging hashes. Its Butterfly
input/model/Golden NPY files also exactly match this Windows V2 bundle.
Both uploaded packages pass independently checked ZIP CRC, every manifest
file hash and embedded XSA bit/HWH consistency. Both retain board gate PENDING.

Use Aero's entire matched package for board boot/clock, DMA status, complete
255x255 bit-exact output and repeated transactions with changed input/model.
Do not substitute this Windows bit/HWH into its differently hashed package.
See [the cross-branch handoff](../docs/p3-q20-12-handoff.md) for versions and
remaining ownership. No Q20.12 board result, measured FPS or measured power
is established by this implementation gate.

Generated project, IP, logs/reports, DCP and large binary artifacts stay
outside Git. Only scripts, this result and reproduction documentation are
committed. No board is programmed and no FPS/power measurements are claimed.
