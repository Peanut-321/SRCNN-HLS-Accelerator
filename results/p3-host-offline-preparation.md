# P3 offline reference and host preparation

Date: 2026-10-10. Base checkpoint: `571149b`, branch `deploy/srcnn-axis-dataflow`.
Status: SOFTWARE_PREPARED; FORMAL_ASSETS_PENDING; BOARD_PENDING.

No DUT source, HLS pragma, FIFO, padding or numerical type changed. Existing
Vivado 200 MHz overlay hashes remain the identities required by the new host.
Unrelated local tool logs and the teammate branch were not modified.

## Added software

- `tools/deployment_numeric.py`: independent NumPy bias-first float32 and raw
  integer reference, replicate padding, Q24.8 AP_RND_CONV/AP_SAT, 24/30/40-bit
  layer accumulators; layer and accumulator saturation counters.
- `tools/import_course_assets.py` + `course_asset_hashes.json`: checksum/size
  verification of Aero's recorded ten raw assets from `7902143`, input/GT u8
  normalization and model concatenation. Course raw files remain outside Git.
- `tools/prepare_srcnn_deployment.py`: current fixed-size normalized input,
  model, independent reference output, offline metrics, checksummed bundles.
- `tools/summarize_set5.py`: all-five-case requirement, consistent peak/crop,
  mean of per-image PSNR separate from mean MSE.
- `pynq/srcnn_axis_host.py`: matching frozen bit/HWH checks, model pointer,
  receive-first DMA, bounded polling, DMA error/byte count/ap_done checks,
  cache synchronization, exact output comparison and failure logs. Failure
  resets the whole PL before freeing outstanding model/frame allocations.
- `pynq/srcnn_axis_255x255.ipynb`: offline/physical stages kept separate;
  board/preparation switches false and physical outputs unexecuted.

## Verification

Python 3 with NumPy 2.x from the bundled runtime. Run:

```text
python tests/test_deployment_host.py --rtl-vectors PATH_TO_EXISTING_FIXED_RUN -v
```

**12/12 software tests PASS**, covering ties/sign/saturation, replicate padding
and channel layout, metrics/crop, bundle corruption, full Set5 completeness,
64-bit AXI addresses, byte counts, DMA errors, timeout, non-finite timeout
rejection, receive/start/send order, model pointer, and whole-PL reset before
buffer release after an incomplete transfer.

The independent integer reference exactly matched all 221 output raw words
from the existing fixed 13x17 vectors already exercised successfully by XSIM.
This is a new reference-vs-RTL-checked-vector gate, not a new RTL run.

Full 255x255 **synthetic offline** inference/pack/read smoke check passed:
65,025 input words, 8,129 model words, 65,025 expected output words; all saved
artifact checksums validated. It uses the prior deterministic model and a
normalized synthetic ramp, not the official trained model or Set5 imagery.
The synthetic check had zero layer-data/accumulator saturations. Its precision
numbers are diagnostic only and are not formal image-quality results.

Notebook code cells compile and default offline execution passes without
importing PYNQ or downloading hardware. The notebook has no fabricated board
outputs. Syntax/JSON checks and `git diff --check` pass.

External verification artifacts reside at:
`C:\Users\xzype\Documents\Codex\2026-10-08\windows-codex-mac-github-windows-codex\outputs\host-preparation`.

## What remains

Official raw model/Butterfly/remaining Set5 assets were not found in the local
repository or inspected course directories. Aero's manifest identifies files
on his computer, not a directory available here. **No official-model PSNR,
full Set5 aggregate, FPGA FPS, or physical board PASS is claimed.**

Once files are supplied locally, import/verify first, prepare each supported
255x255 case, compare float outputs against course Golden and fixed outputs
against float/HR, and inspect saturation and quality loss before board use.
The course's final crop/postprocessing convention and accuracy threshold are
not inferred; default crop=0, peak=1, unclamped output is recorded explicitly.

The physical runner still needs the actual KV260 Linux/PYNQ image and board
verification. Mock MMIO tests validate sequencing/error handling only. All
run timing includes model loading/DMA; it is not pure kernel-only FPS.

See `docs/p3-host-and-offline-evaluation.md` for reproduction commands.
