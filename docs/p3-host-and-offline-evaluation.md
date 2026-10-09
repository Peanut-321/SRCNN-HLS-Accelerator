# P3 host preparation and offline image evaluation

Status: software prepared; official assets and physical KV260 execution pending.
Hardware checkpoint: `571149b`, source `fef8043`, fixed 255x255, 200 MHz.
No HLS/DUT/pragma/numeric changes are part of this work.

## Local dependencies and tests

Python 3 + NumPy. Board execution additionally needs PYNQ on the actual KV260
image. Run from the repository root:

```text
python tests/test_deployment_host.py -v
python tests/test_deployment_host.py --rtl-vectors PATH_TO_EXISTING_FIXED_RUN -v
```

The optional existing `input.hex/model.hex/expected.hex` gate checks the
independent integer reference against all 221 words previously validated in
XSIM. It is not a new RTL simulation or proof of full-frame board correctness.

## Import the recorded official Butterfly case

The raw course files stay local. `tools/course_asset_hashes.json` records the
ten sizes/checksums copied from Aero's `7902143` asset manifest. Import rejects
any missing/mismatched file, including the recorded Conv1 intermediate.

```text
python tools/import_course_assets.py --root PATH_TO_GOLDEN_ROOT --out data/butterfly_float
python tools/prepare_srcnn_deployment.py --input data/butterfly_float/input_float.npy --model data/butterfly_float/model_float.npy --golden data/butterfly_float/course_golden.npy --ground-truth data/butterfly_float/ground_truth.npy --crop 0 --out data/butterfly_deploy
```

Input u8 and ground truth u8 are divided by 255 in float32. The recorded LR
input is already bicubic-interpolated; importing does not resize it again.
Course Golden output stays float32. Butterfly alone is one case, not Set5 PASS.
For other official images, prepare normalized float32 `.npy` files with their
source provenance, then use the same bundle command. The deployed IP accepts
only 255x255; do not silently resize/crop arbitrary Set5 images to fit it.

## Arithmetic and quality policy

The current frozen hardware uses signed Q24.8 with convergent ties-to-even
rounding and signed saturation. Model order is Conv1 W/B, Conv2 W/B, Conv3 W/B:
offsets 0/5184/5248/7296/7328/8128, 8129 words total. Sending float32 bit patterns
as model words is incorrect. `deployment_numeric.py` uses integer products,
bias-first accumulation, replicate edges, exact accumulator widths 24/30/40,
and a layer-output narrow after Conv1/2 ReLU. Float reference rounds every
multiply/add separately in OIHW order and leaves Conv3 unclamped.

Bundles store input/model/expected as little-endian uint32 raw codes, with
SHA-256 checksums. Data and accumulator saturations are counted. Saturation or
quality loss is reported without changing the frozen Q24.8 format. The numeric
header's range assumptions are placeholders; official-model quality remains
an actual gate even though hardware timing already passes.

MSE/PSNR uses normalized floats, peak=1. Crop is explicit (default 0). No output
clamp or pixel rounding is used in these metrics. Perfect match is represented
by `perfect_match=true, psnr_db=null` (mathematically +infinity), not zero dB.
Report separately: fixed-vs-float/course-Golden implementation error, and
fixed/float-vs-HR reconstruction quality. No course threshold is invented.
Border-crop/postprocessing policy still requires the actual course convention.

`summarize_set5.py` accepts a JSON mapping of all five named case directories:
baby, bird, butterfly, head, woman. It rejects missing cases and inconsistent
crop/peak. Its mean PSNR is the mean of per-image dB values, not PSNR computed
from mean MSE. This is offline inference, not a measured FPGA score.

## Board runner and notebook

Open `pynq/srcnn_axis_255x255.ipynb`. Preparation and board execution switches
default to false; its unexecuted board cells contain no invented results.
Transfer the matching `.bit/.hwh`, three `.npy` files and `manifest.json` to
the board, together with `pynq/srcnn_axis_host.py`.

```text
python pynq/srcnn_axis_host.py --bit /home/xilinx/srcnn_axis_255x255.bit --bundle data/butterfly_deploy --out board-results/run-001 --iterations 3 --timeout 120
```

The runner locks the bit/HWH hashes to the validated 200 MHz checkpoint;
checks actual IP names `dma` / `srcnn`, simple DMA length capacity and 32-bit
AXIS, and observes the PL0 clock without retuning it. It writes model address
low/high at 0x10/0x14. These registers are not the dummy's length register.
It flushes separate input/output/model buffers, arms S2MM first, starts SRCNN,
then MM2S. Bounded polling checks DMA errors, both completed byte counts and
latched ap_done before invalidating output and comparing every raw code.

On an unfinished transfer it reloads the overlay to reset the entire PL before
freeing allocations. Reset failure retains buffers; in a notebook keep the
runner alive and reset/power-cycle the board before releasing it. Do not exit
a failed session until outstanding memory masters are quiescent. Success and
failure CLI results are written to a new result directory to avoid stale PASS.
Linux/PYNQ availability, PLL boot behavior and physical DMA remain untested.

Timing labels distinguish allocate-to-compare from transfer-start-to-done;
the latter includes model loading and DMA. Neither is pure kernel-only timing
or camera/preprocessing end-to-end FPS. Host cannot directly observe AXIS
TKEEP/TSTRB/TLAST; existing RTL covers those sidebands, and board DMA byte count
is an additional completion check, not an equivalent waveform observation.
