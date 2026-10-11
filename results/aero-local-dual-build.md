# Aero local dual-format deployment build

Started 2026-10-11. No board result is claimed.

## Frozen sources and separate output roots

| Format | Source checkpoint | Source directory | HLS directory | Vivado directory | Delivery directory |
|---|---|---|---|---|---|
| Q24.8 | 5f0216704cdd7ba70e2c8a493469c2df97e32259 | C:/fpga/aero-q248-src | C:/fpga/aero-q248-hls | C:/fpga/aero-q248-vivado | C:/fpga/aero-q248-delivery |
| Q20.12 | 18281e76b9070b6801620a8548c7ae8b72f47db5 | C:/fpga/aero-q2012-src | C:/fpga/aero-q2012-hls | C:/fpga/aero-q2012-vivado | C:/fpga/aero-q2012-delivery |

Both source directories are detached Git worktrees. The user's existing
deploy/vivado-pynq worktree and dummy Vivado project remain unchanged.

Tools: S:/2026.1/Vitis and S:/2026.1/Vivado, Unified HLS 6493734,
Vivado 6511674. Use the bundled Python at
S:/2026.1/tps/win64/python-3.13.0/python.exe (NumPy 2.3.0).

## Confirmed build gates

- Q24.8 deployment HLS synthesis and explicit IP packaging: exit 0.
  IP: C:/fpga/aero-q248-hls/hls/impl/ip/xilinx_com_hls_srcnn_axis_dataflow_top_1_0.zip.
  SHA256: 7a5bee41df441a8b34739b185377769122edbac18752c70cf32f761f5af7167b.
  This fresh ZIP is not byte-identical to the teammate's archived ZIP; do not
  use the old bitstream/ZIP hashes as acceptance criteria for this new build.
- Q24.8 Vivado BD validation: GATE_BD_PASS. Integration config confirms
  DDR enabled, requested PL0 200 MHz (reported 199.998001), DMA BTT=26.
  Synthesis and routed implementation passed. WNS 0.077 ns, WHS 0.011 ns,
  TNS/THS 0, no unconstrained internal endpoints and DRC blockers 0.
  Bitstream/XSA export completed with exit 0. Bit SHA256:
  a045964072df1f268ebc9a7ee38d66c8160bab804e788a1caf3d378a7e9bdd5c.
  HWH SHA256: 47c2cff3bdc8475665431ecdb8789feaa30a3106be149942c912e961bd0aaf24.
- Q20.12 small C simulation: PASS, 221 outputs exactly match OC4, zero errors.
- Q20.12 small and deployment HLS synthesis/IP export: exit 0.
  Deployment IP (not the diagnostic top):
  C:/fpga/aero-q2012-hls/deployment_255x255_5ns/hls/impl/ip/xilinx_com_hls_srcnn_axis_dataflow_top_1_0.zip.
  SHA256: 2b0eb4c06d4fd9c1cd328fc77a6d98fd5cbbfcff923b6924035a9223247dbd00.
  Separate Q20.12 Vivado synthesis and routed implementation passed.
  WNS 0.107 ns, WHS 0.010 ns, TNS/THS 0, no unconstrained internal endpoints.
  DRC blockers 0; bitstream/XSA export completed with exit 0.
  Bit SHA256: ec96f56c96fa01da04cd4ed76adaaf8e17e5e02ad46c610fae42c64200a51e28.
  HWH SHA256: e9b07fa599f1ab35a4301ea1fe34feb8ea2b8ea74024f2f75c0f376f6229e80d.
- Q20.12 bundle tests: 9/9 passed.
- Deployment-host tests: 11 passed, one optional RTL-vector test skipped.
- Formal course Butterfly asset import: checksums passed.
- Separate full-frame bundles generated successfully:
  C:/fpga/aero-q248-bundle (V1) and C:/fpga/aero-q2012-bundle (V2).
  Shared normalized inputs: C:/fpga/aero-float-butterfly.

## Delivery and physical-board boundary

Each format is packaged separately under the user's existing
`C:/Users/aeroc/Desktop/文件/EE/2026S2/90096/Project` directory as
`srcnn_q24_8` or `srcnn_q20_12`, plus the matching ZIP.
The packager requires an executed bitstream gate, nonnegative setup/hold slack,
zero DRC blockers, source/numeric provenance and bit/HWH/XSA consistency.
Both packages passed offline inspection in fresh Python processes. Both ZIPs
passed CRC checks and every manifest-listed file hash was verified. Their
bitstreams are distinct. Both manifests deliberately retain board_gate=PENDING.
DSP pipelining and DMA BRAM advisory warnings remain in the saved reports;
passing the gate does not mean warning-free hardware.

The English notebook starts unexecuted and RUN_BOARD=False. Physical testing
checks every output word on warmup, ten repeats, changed input/model,
restoration and overlay reload. Its timing includes model loading/DMA, not
pure kernel execution. Q20.12 uses the V2 bundle reader and scale 4096;
Q24.8 uses V1 and scale 256. Fresh artifact hashes are verified before the
upstream runner is bound to this local build; no hash check is bypassed.

Offline orchestration uses fake hardware only: 4 tests passed. Packaging gates
including XSA mismatch rejection: 5 tests passed. These are NOT board results.
No physical board execution has occurred for either SRCNN version here.
