# Formal delivery runner offline audit — 2026-10-11

Both uploaded formal deliveries pass offline inspection and the delivered host
control/failure tests. No delivery code repair is required by these results.
The Q24.8 and Q20.12 **physical SRCNN board gates remain PENDING**.

## Exact artifacts

GitHub was fetched again before the audit. Aero's latest branch remains
`deploy/vivado-pynq@8b87af8b789c8c788bf06396e4367564f050af85`.
The ZIPs were read from that exact Git object and extracted into independent
workspace directories. The original ZIPs, DUT and packaged scripts were unchanged.

| Profile | Frozen hardware source | Uploaded ZIP SHA-256 |
|---|---|---|
| Q24.8 | `5f0216704cdd7ba70e2c8a493469c2df97e32259` | `741a29830047d0402d9f7908dbdd5140a4f37b507e5e7e5e7913adf8b4f75d51` |
| Q20.12 | `18281e76b9070b6801620a8548c7ae8b72f47db5` | `96f7d47471e065dceb655c442ec2d854634b6eb6b5418c52d90e3e1e8ab40828` |

Paths on the Aero branch are `deliverables/aero-local/srcnn_q24_8.zip` and
`deliverables/aero-local/srcnn_q20_12.zip`. Prior CRC/file/XSA/RTL equivalence
checks are recorded in [the handoff](../docs/p3-q20-12-handoff.md).

| Checked object | SHA-256 |
|---|---|
| Q24.8 delivery manifest | `31a498b938615066c6f643db955f4c8382054a1c35f1e339b3b92717dbef33e6` |
| Q20.12 delivery manifest | `94e2e6384e31fc41b7e406aecb52f0fca0a644ded4cdecfd9063341f2098c630` |
| Delivered `srcnn_axis_host.py`, both profiles | `e74e96e8d658268b15ecec5490e1981aacddbf83e29a3e7598c938e39c735617` |
| Delivered `aero_board_test.py`, both profiles | `2ff17c13f893649a2b5f1c1ed2c4f0f9ade2898c6b2a96c738d70527bdefa084` |
| New offline audit script | `f6be6deb2d98b1268fd7b1f66b9b6c3bce204a2e569865d56d0699d0834bf0de` |

## Executed checks

Python 3.12.14, NumPy 2.3.5, Windows; each delivery ran in a fresh Python process.

| Gate | Result |
|---|---|
| Packaged CLI inspection, Q24.8 | PASS; file hashes, source/profile/build contract and both bundles |
| Packaged CLI inspection, Q20.12 | PASS; same checks using the packaged Q20.12 V2 reader |
| Aero's unchanged orchestration/packaging unit tests | 9/9 PASS |
| Actual delivered Runner and wrapper with fake PYNQ, Q24.8 | 13/13 PASS |
| Actual delivered Runner and wrapper with fake PYNQ, Q20.12 | 13/13 PASS |

The 26 additional tests execute the **actual packaged** `Runner.run`,
`wait_complete`, `reset_dma` and `aero_board_test.run_board`. They replace PYNQ's
Overlay, MMIO, allocator and PL clock with an offline fake. They do not replace
Runner with an object that simply returns PASS.

Covered behavior:

1. Upload input/model and flush buffers; preserve upper address bits using fake
   physical addresses above 4 GiB. RX is armed before kernel start, then TX is
   armed. The fake asserts the exact input/model case selected by those writes.
2. Run Butterfly, changed input/model, then restored Butterfly on one Runner
   without PL reload. Successful transfers invalidate the destination only after
   completion and release all allocations.
3. Execute the existing wrapper's warmup, three measured repeats, changed case,
   restored case and separate overlay-reload run; seven output artifacts are
   written and the wrapper retains no successful Runner.
4. Latch clear-on-read `ap_done` when it arrives one poll before DMA idle.
5. Reject a DMA length-register mismatch and any injected output mismatch.
6. Bound DMA reset timeout and transfer completion timeout.
7. On a DMA error/timeout, reload the whole PL and verify kernel idle plus both
   DMA halted bits before releasing buffers.
8. If reload throws **or returns without quiescent registers**, retain all three
   buffers. A further call is rejected before allocation/MMIO. The wrapper keeps
   the failed Runner alive and writes a FAIL report with the retained-buffer count.
9. Reject a wrong bit hash before Overlay creation, a corrupted model bundle
   checksum, and the other numeric profile's bundle format.

These are host-behavior tests. The fake fills the destination from the packaged
Golden array; it does **not** compute SRCNN. Mock timing is not an inference
benchmark. Real AXI handshakes, DMA length-register behavior, PL clocks, routing,
arithmetic, hardware reset/reload and performance still require their existing
RTL/implementation evidence and the pending physical board gate.

The initial unit-test attempts hit Windows sandbox permissions inside Python
temporary directories. The unchanged tests passed with normal execution
permissions and task-local TEMP/TMP. This was not a deployment-code failure.

## Reproduction without an FPGA

Use a Python environment with NumPy and the unmodified extracted delivery.
Run from any checkout containing the new audit helper, without switching the
hardware source or rebuilding the package:

```text
python tools/audit_delivered_board_runner.py --delivery /path/to/srcnn_q24_8 --out /path/to/audit-q24.json
python tools/audit_delivered_board_runner.py --delivery /path/to/srcnn_q20_12 --out /path/to/audit-q20.json
```

Run the two commands as separate processes. Results explicitly record
`audit_kind=OFFLINE_FAKE_PYNQ_ONLY`, `board_tested=false`,
`arithmetic_tested=false`, script/manifest hashes and test counts.
The helper never imports real PYNQ for Runner creation and never programs a board.

Local evidence below the Windows task workspace:

- `work/aero-board-audit/extracted.json`: immutable Git/ZIP identity.
- `work/aero-board-audit/{q24_8,q20_12}/srcnn_{q24_8,q20_12}`: extracted packages.
- `outputs/aero-board-audit/{q24_8,q20_12}.json`: final 13-test proofs.
- `outputs/aero-board-audit-{q24_8,q20_12}.log`: final test names/results.

Generated packages/bit/HWH/NPYs/mock run artifacts were not added to Git.

## Remaining formal board gate

Use each **complete matched Aero delivery** with its existing notebook. Start a
fresh notebook kernel when changing profiles; the wrapper intentionally rejects
an already-imported host module from a different delivery directory. Inspect the
package first, then explicitly enable the notebook's existing board operation.

For each profile preserve the executed notebook, `board_results.json`, all seven
per-frame outputs, actual overlay hashes/PL clock, DMA/control snapshots, and
the real transfer-window median/P95/FPS. All 65,025 output words must match in
every phase. Keep the notebook process alive after a failed PL reset because it
owns the retained DMA/model buffers; follow the runner's reset/power-cycle message.

Only those physical results can close the board gate and support a release
baseline/performance comparison. No additional HLS/Vivado build, Conv2 change or
duplicate board runner is needed from this audit.
