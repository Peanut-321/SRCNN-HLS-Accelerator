# Aero deployment handoff — 2026-10-11

## Supplementary validation and English delivery — 2026-10-12

See `docs/board-delivery-final-en.md` for the current execution entry points,
full evidence inventory and final-report boundaries. Both original V3 result
archives were re-audited. Q20.12 additionally passed 14 distinct supplied images
(910,350 exact words). The audited Butterfly scalar C++ CPU median is
10.994656504 s; FPGA memory-to-memory median is 0.755946391 s, giving a 14.5442
time ratio relative to that single-thread scalar baseline only. English clean
reproduction notebooks were validated offline; original physical records are
unchanged. Separate model/compute/DMA timings and optimized CPU baselines are
not claimed. The remaining-task text below records the earlier handoff state.

## Q24.8 and Q20.12: final V3 physical validation PASS

Both formats passed KV260 tests. Downloaded evidence was independently audited:
all 14 frames per format contain 65,025 uint32 words, exactly matching each
format's fixed-point Golden. This does not claim zero error versus float.
Tests cover warmup, 10 repeats, changed input AND model, restored input/model,
and overlay reload. BIT/HWH hashes match V3. ZIP CRC, schedule, statistics and
executed notebooks passed audit.

| Format | Median seconds | P95 seconds | Reciprocal median FPS |
|---|---:|---:|---:|
| Q24.8 | 0.7498277790000429 | 0.7499921595999695 | 1.3336395743214293 |
| Q20.12 | 0.7498662649999801 | 0.7499635060000571 | 1.3335711268462338 |

Timing is host-observed transfer-start-to-done INCLUDING model loading and
DMA, NOT kernel-only or independently measured sustained FPS. The board clock
shows August 17; actual validation/receipt was October 11. Preserve raw names
but do not treat their timestamp as the experiment's real calendar date.

## Canonical files — no repeated extracted copies

- `deliverables/aero-local/srcnn_q24_8_v3_resetfix.zip`
- `deliverables/aero-local/srcnn_q20_12_v3_resetfix.zip`
- `results/srcnn-board/q24_8/q24_8_board_results.zip`
- `results/srcnn-board/q24_8/SRCNN_board_test.ipynb`
- `results/srcnn-board/q20_12/q20_12_board_results.zip`
- `results/srcnn-board/q20_12/SRCNN_board_test.ipynb`

Each results ZIP contains one JSON and 14 NPY outputs. These are not duplicated
as loose files. Deployment ZIPs contain IP, matched BIT/HWH, runtime, bundles,
source identity and implementation reports. Old original/V2 deployment ZIPs
are retired and removed from the current tree. Historical Git commits remain
recoverable, but MUST NOT be used for deployment.

## Correction and existing work

V2 tied the active-low auxiliary reset LOW, permanently asserting AXI reset.
V3 ties it HIGH, verified in generated HDL/HWH and reset-netlist simulation.
Control uses HPM1 at B0000000/B0010000; DDR uses HPC0. Both V3 builds pass
timing/DRC/export. See `results/aero-reset-audit.md` and
`results/aero-local-dual-build.md`. Team numerical sources are unchanged.

Known-good dummy files and `results/p0c-board/` remain unchanged: 26-bit DMA,
1,500 unique cases PASS. Its bandwidth is NOT SRCNN inference performance.

## Remaining team tasks — do not rebuild or repeat passed board tests

Aero's dual-format deployment and this board-validation scope are complete.
The full project still requires consolidation of CPU baseline, same-boundary
speedup, float/quality comparisons, resource/optimization tables, presentation,
final report and submission requirements. Check teammate artifacts before
duplicating work. No dataset-wide physical validation or whole-project
completion is claimed. Use one format and one board-test kernel at a time.
No licenses, temporary Vivado projects or failed deployment ZIPs are included.
