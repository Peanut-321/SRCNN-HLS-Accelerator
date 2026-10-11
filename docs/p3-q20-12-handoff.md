# SRCNN cross-branch handoff — 2026-10-11

This inventory is based on the fetched GitHub refs and the actual uploaded
delivery ZIP contents. No physical board operation was performed by this audit.

## Versions to keep

| Purpose | Branch/checkpoint | Status |
|---|---|---|
| Q20.12 DUT repair | `optimize/official-q20-12`, `5f76e4e` | Conv1 II=1; unchanged numeric outputs |
| Q20.12 complete functional checkpoint | same branch, `18281e7` | Full fixed 255x255 two-frame independent RTL PASS, no reset |
| Windows Q20.12 implementation evidence | latest commit of same branch containing `results/p3-q20-12-vivado.md` | Routed 5 ns/export PASS |
| Aero dummy and formal delivery | `deploy/vivado-pynq`, `8b87af8` | Dummy board evidence plus both formal packages uploaded |
| Aero Q24.8 frozen source | `5f02167` | Routed 5 ns package; SRCNN board gate pending |
| Aero Q20.12 frozen source | `18281e7` | Routed 5 ns package; SRCNN board gate pending |

The original host-checkpoint report is historical, not the latest project
status. Follow its links to the subsequent HLS, full-frame RTL and Vivado reports.
No newer DUT optimization is hidden in an uncommitted working tree. The latest
Windows follow-up changes only integration verification scripts/documentation.
Existing local `logs/` and Vivado journal files are generated files, not new code.

The subsequent [formal runner offline audit](../results/p3-formal-board-runner-offline-audit.md)
executes both actual uploaded deliveries: package inspection PASS, 9 existing
tests PASS and 13 fake-PYNQ host-control/failure tests per profile PASS. It found
no required delivery-code repair. Both formal physical board gates remain pending.

## Completed work

- Q20.12 host/profile/V2 bundle and 19-test regression; all 14 supplied-image
  outputs agree with the independent integer reference. Quality is documented
  in `results/p3-q20-12-host-checkpoint.md`; the supplied assets are not the full
  Set5/Set14 benchmark sets.
- Q20.12 Vitis C-sim, fixed deployment synthesis/IP export and Conv1 II=1 repair.
- Q20.12 independent RTL: small frames, negative Golden controls, and two complete
  255x255 transactions with changed second input/model and no DUT reset;
  130,050 outputs exactly match Golden. This is independent SV validation,
  not a claim that the Vitis automatic UVM harness was repaired.
- Windows Q20.12 KV260 integration, route and export: WNS/WHS +0.107/+0.010 ns,
  pulse slack +1.000 ns, all 12 timing-coverage categories zero, no blocking DRC.
- Aero's uploaded reports document dummy physical tests: 1,200/1,200 for BTT14
  and 1,500/1,500 unique cases for BTT26. Dummy speed is not SRCNN speed.
- Aero separately rebuilt, routed and packaged both formal numeric profiles;
  its board wrapper/notebook has offline tests. Neither formal profile has a
  physical-board PASS recorded in the audited checkpoint.

## Uploaded packages independently inspected here

Both files are under `deliverables/aero-local/` on `deploy/vivado-pynq@8b87af8`.

| ZIP | Bytes | SHA-256 | Manifest-listed files |
|---|---:|---|---:|
| srcnn_q20_12.zip | 3,810,465 | 96f7d47471e065dceb655c442ec2d854634b6eb6b5418c52d90e3e1e8ab40828 | 28 |
| srcnn_q24_8.zip | 3,598,954 | 741a29830047d0402d9f7908dbdd5140a4f37b507e5e7e5e7913adf8b4f75d51 | 27 |

For both: ZIP CRC PASS, every manifest-listed file hash PASS, XSA embedded
bit/HWH hashes match the standalone files, `board_gate=PENDING`.
Q20.12's 63 exported Verilog/data files are byte-identical to the Windows
validated export. Its Butterfly input/model/expected NPY files are also identical.
Different IP ZIP/bit/HWH archive hashes belong to separate recorded builds;
do not apply one build's acceptance hashes to another build or mix their files.
Use Aero's already uploaded matched package for physical tests rather than
rebuilding or replacing individual files with this Windows export.

## Completed Windows files intentionally outside Git

Workspace root:
`C:\Users\xzype\Documents\Codex\2026-10-08\windows-codex-mac-github-windows-codex`.

| Artifact | Path below workspace root |
|---|---|
| Original repaired deployment HLS IP ZIP, SHA `ac79f070...ec965` | `work\q20mac2\deployment_255x255_5ns\hls\impl\ip\xilinx_com_hls_srcnn_axis_dataflow_top_1_0.zip` |
| Windows Q20.12 bit/HWH/XSA and candidate manifest | `outputs\q20-12-vivado-5ns\srcnn_axis_q20_12_255x255.*`, `q20-overlay-manifest.json` |
| Routed timing/DRC, logs, SHA inventories and package audit JSONs | `outputs\q20-12-vivado-5ns` |
| Verified full-frame Q20.12 V2 input/model/Golden bundle | `outputs\q20-12-profile\butterfly-bundle-v2` |
| Full-frame/restart logs/manifests | `outputs\q20-12-full-frame-rtl` |
| Full two-frame WDB, 189,436,059 bytes | `work\q20restart\rtl-full-two\independent_srcnn.wdb` |

The independent Vivado project/routed DCP is `C:\fpga\q20-vivado-5ns`.
Full binary hashes are in `results/p3-q20-12-vivado.md`. These local generated
artifacts are complete but are not committed. Aero's uploaded matched IP/
overlay/bundles cover the practical handoff; another binary upload is unnecessary.

## Remaining work and proposed ownership

1. Aero: run formal packages on KV260, keeping Q24.8 and Q20.12 separate.
   Check boot/PL clock, model address, DMA status/timeouts, all 65,025 words,
   warmup/repeats, changed input/model, restored model and overlay reload.
   Preserve the executed notebook and per-frame outputs/status logs.
2. Aero: report real SRCNN latency/FPS with the stated model-load/DMA timing
   boundary; record image correctness/quality. Any power claim needs an actual
   board measurement. Do not reuse dummy throughput as an inference benchmark.
3. Windows/core side: retain this verified source/RTL provenance and review board
   failures against it; consolidate quality/architecture/resource/timing evidence
   for the final report. No new Conv2 optimization or additional size experiment
   is in progress, and no duplicate build is needed for handoff.
4. After the board gates: choose the release baseline and integrate the required
   cross-branch code/docs deliberately. This audit does not merge branches or
   replace the default Q24.8 overlay.

These ownership lines are a coordination proposal, not messages sent to the
teammate or a claim that they agreed. The user can share this exact version list.
