# Q20.12 deployment readiness

Prepared 2026-10-11. This is a deployment checklist, not a board-test result.

## Local rebuild supersedes the missing-package wait

A separate local rebuild has now exported both fixed-point deployment IPs.
See `results/aero-local-dual-build.md` for current build gates and delivery
locations. The archived ZIP hash below identifies only the teammate's original
export; it must NOT be applied to the freshly generated local export.
The local packager checks frozen source hashes, numeric flags, routed timing,
DRC and matching bit/HWH/XSA before delivery. Physical validation remains pending.

## Verified upstream checkpoint

- Repository: Peanut-321/SRCNN-HLS-Accelerator.
- Branch: optimize/official-q20-12; checkpoint 18281e76b9070b6801620a8548c7ae8b72f47db5.
- Repaired source commit: 5f76e4e0007db5f4b28841687273761777bc31a4.
- Upstream reports restored Conv1 II=1 and two full-frame RTL transactions.
- Export record: results/p3-q20-12-conv1-writeback.md at that checkpoint.
- Required deployment ZIP: xilinx_com_hls_srcnn_axis_dataflow_top_1_0.zip.
- Expected bytes: 498396.
- Expected SHA256: ac79f070bd1a4fc3458617628802ae25855c5e106fbac14b9a01c916aceec965.
- The teammate's original package was not available at the initial inspection.
  `tools/check_q20_ip.py` remains specific to that archived package, not local builds.

## Original handoff checklist (historical; local rebuild follows the report above)

1. Receive the deployment IP ZIP and run tools/check_q20_ip.py against it.
   A mismatch requires clarification, not bypassing the check. Do not use the
   diagnostic 13x17 IP or the old Q24.8 export.
2. Use a separate Vivado project with a short Windows path. Preserve the
   validated dummy project and all original results. Confirm the current
   upstream Vivado reproduction script before creating the new system.
3. Connect DMA and the kernel model-memory master to PS DDR; connect control,
   clocks and resets. Check address maps, 32-bit AXIS and DMA BTT=26. The
   model-memory master is essential: this is not just a replacement for dummy.
4. Validate, synthesize, implement and audit timing/DRC. Record the actual
   clock, WNS/TNS, hold timing and utilization. HLS estimates are not routed timing.
5. Export same-stem bit/hwh files from the same build, plus hashes and Tcl.
6. Adapt the formal host to Q20.12 and the new artifacts. Never reuse old
   artifact hashes or dummy length-register programming. Confirm registers from
   the new metadata. Use bounded waits and explicit DMA error handling.
7. Use the matching Q20.12 model/input/independent Golden contract (scale 4096,
   not Q24.8 scale 256). Check every output, restart, changed input/model and
   reload behavior on the board. Keep existing files intact.
8. Measure real SRCNN latency and image quality with a clearly stated timing
   boundary. Dummy DMA throughput is not SRCNN inference performance.
9. Save logs, Notebook, build provenance and final reporting artifacts.

## File organization

Keep board files under the user's existing Project folder. Before creating
additional folders, tell the user their names and purpose. Suggested separate
folder: srcnn_q20_12, containing the new overlay pair, matching model/vectors,
formal Notebook and logs. Do not change existing dummy files.

## Not completed by this preparation

The original preparation alone performed no builds. The subsequent local build
is recorded separately. No physical board test or push is claimed here.
