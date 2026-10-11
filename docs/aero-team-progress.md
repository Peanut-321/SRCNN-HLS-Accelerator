# Aero deployment handoff — 2026-10-11

Branch: `deploy/vivado-pynq`. This update does not merge or modify the team's
SRCNN HLS core. Previously committed P0a/P0b sources and reports are not recopied.

## Completed and uploaded

- Dummy KV260/PYNQ physical validation: 14-bit DMA 1,200/1,200 PASS;
  upgraded 26-bit DMA 1,500/1,500 unique cases PASS, across three overlay
  loads and lengths 1, 5, 257, 4,095 and 65,025 words.
- Dummy host-observed benchmark: 65,025 words, median 885.97 us,
  P95 941.39 us, input-payload throughput 293.58 MB/s. This is NOT SRCNN speed.
- Evidence: `results/p0c-board/` includes both run logs, both benchmarks and
  the latest executed notebook. `deliverables/aero-local/` contains the
  matching 26-bit dummy bit/HWH pair; `vivado/p0b-btt26/` contains its Tcl.
- Formal Q24.8 and Q20.12 deployment IPs rebuilt from separate frozen sources,
  both synthesized, routed and exported at requested 200 MHz.
  Q24.8 WNS/WHS: +0.077/+0.011 ns; Q20.12: +0.107/+0.010 ns.
  Both have zero blocking DRC violations; nonblocking advisories remain.
- `deliverables/aero-local/srcnn_q24_8.zip` and `srcnn_q20_12.zip` each
  contain the IP ZIP, matching bit/HWH/XSA, source provenance, timing/DRC
  reports, Butterfly and changed-case bundles, and an English board notebook.
  Packages passed offline hash/ZIP/XSA consistency checks.

## Remaining / avoid duplicate work

Formal SRCNN physical-board results are **PENDING for both formats**. Aero's
next task is to test these packages on KV260: all output words, repeated
frames, changed input/model, restored model and overlay reload; then measure
and save real hardware results. The notebook defaults to RUN_BOARD=False.

Do not rebuild these two local deployment packages merely because generated
IP/bit/HWH files were previously missing from Git. HLS core optimization,
dataset-wide quality evaluation and final reporting remain separate tasks;
this update does not claim the whole project complete.

Use each format's own bundle/runner. Finish one notebook kernel before
programming the other. No license files, temporary Vivado projects or
duplicate extracted copies of these delivery ZIPs are included.

Detailed build provenance: `results/aero-local-dual-build.md`.
