# Final V3 board deliverables and evidence

Updated 12 October 2026. Freeze the validated V3 hardware. Original/V2 packages
are historical failures and must not be used for submission or execution.

## English execution entry points

- `deliverables/aero-local/SRCNN_V3_Run_EN.ipynb`: common English host notebook
  for either validated V3 format. Extract the corresponding V3 ZIP, copy the
  notebook into that extracted directory, then open it there on KV260 PYNQ.
  Run cells in order. Inspection does not program hardware. Explicitly enable
  preflight, and enable inference only after preflight passes. Never run both
  formats concurrently or reuse an imported runtime from the other directory.
- `deliverables/aero-local/q20_12_return_board_check_EN.zip`: self-contained
  supplementary kit with 14 supplied inputs, official model, independent
  expected outputs, metric references, CPU C++ source, and benchmark scripts.
  Extract alongside `srcnn_q20_12_v3_resetfix` in the board Project directory.
  Open `Q20_12_Supplementary_Run_EN.ipynb` inside the kit. Do not overwrite an
  existing kit/results directory. The clean reproduction sequence is image
  tests, CPU tests, then memory-to-memory benchmark using that CPU result path.

Requirements: Python 3.10+, NumPy, working KV260 PYNQ; GCC/g++ is additionally
required for the CPU baseline. The recorded board compiler was GCC 11.3.0,
with `-O3 -std=c++14`. No package installation is performed automatically.
All hardware switches default to False. Keep the kernel alive after a hardware
failure that retains buffers; do not run another kernel against active DMA.

These clean English notebooks are reproduction copies, validated offline, not
new physical executions. The immutable V3 runtime/BIT/HWH/reference contents
are unchanged. Historical PENDING wording inside the frozen deployment ZIPs
describes the packaging date and is superseded by the physical evidence below.

## Audited original physical evidence

| Evidence | Location | Scope |
|---|---|---|
| Original Q24.8 V3 run | `results/srcnn-board/q24_8/` | 14 frames: warmup, 10 repeats, changed input/model, restoration, overlay reload |
| Original Q20.12 V3 run | `results/srcnn-board/q20_12/` | Same 14-frame protocol |
| Additional Q20.12 images | `results/srcnn-board/q20_12/return-board-2026-10-12/additional_board_results_20260817T063556_159491Z.zip` | 14 distinct supplied images; 910,350 words bit-exact |
| ARM CPU reference | Same directory, `cpu_results_20260817T063705_562593Z.zip` | Butterfly: warmup plus 3 measured runs; all outputs bit-exact |
| Memory-to-memory benchmark | Same directory, `memory_to_memory_results_20260817T070820_275461Z.zip` | Butterfly FPGA warmup plus 3 measured runs; reuses verified CPU record |

Original notebooks and raw result archives are retained unchanged, including
the path-separator and timing-module initialization failures followed by
successful runs. Do not submit them as the clean runnable entry point. The two
Untitled3 captures record different stages, not repeated output-array copies.
Some historical cells contain Chinese comments/messages; translating them
would alter the raw execution record. All new submission-facing code,
notebook instructions, comments and messages are English.

The board clock incorrectly reports August 17. Actual original V3 validation
was received on October 11, and supplementary evidence on October 12, 2026.
Preserve filenames, but do not use the board timestamp as the true test date.

## Reportable results and boundaries

- Original transfer-window medians: Q24.8 0.749827779 s; Q20.12 0.749866265 s.
  This includes model loading and DMA; it is not isolated kernel latency.
- Butterfly memory-to-memory medians: scalar single-thread C++ CPU
  10.994656504 s; FPGA 0.755946391 s; ratio 14.5442 relative to this CPU baseline.
  Inputs/model start resident in host memory; complete output ends resident
  in host memory. Disk IO, correctness comparisons and initial overlay loading
  are excluded. FPGA includes necessary allocation, copies, cache operations,
  reset/control and DMA. CPU includes intermediate allocations. Cleanup after
  the output-ready timestamp is excluded. Measurements are sequential; CPU
  frequency/thermal state were not controlled. This is not an optimized
  NEON/multithreaded CPU-library comparison or a sustained-throughput claim.
- Q20.12 minimum fixed-versus-float agreement PSNR is 60.621162606 dB;
  maximum absolute reconstruction-PSNR change versus float is 0.004187329 dB.
  Agreement compares two model outputs; reconstruction compares output to GT.
  Policy: peak 1, no crop, no clipping; Butterfly plus 13 supplied Set14 images.
- Q24.8 board arithmetic passes its fixed-point reference but its image quality
  does not pass the team's quality gate. Do not confuse the two gates.
- Later full-frame RTL evidence is not automatically evidence for the same
  source commit as V3 hardware. Keep source identities separate in the report.

No separate compute/model/DMA profile, power/energy measurement or long-duration
stress test is claimed. These are limitations/future work, not completed tests.

The final assignment also requires a PDF report (at most 25 pages excluding
appendices) and the final HLS project/source in one submission ZIP. This board
handoff is not that entire submission. Match final HLS sources to the V3 frozen
commits recorded in `results/aero-local-dual-build.md`; do not silently substitute
newer source while retaining V3 physical-test claims.

Audit records: `results/srcnn-board/final_english_delivery_audit.json` and the
supplementary `audit.json` / `memory_benchmark_audit.json`. Tests use local fake
MMIO for software verification; those tests are not additional physical runs.
