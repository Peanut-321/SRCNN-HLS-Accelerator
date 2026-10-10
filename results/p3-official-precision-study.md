# P3: official-model fractional precision study

Date: 2026-10-10. Base commit: 72480ef; official asset commit:
6b9bba6dd4af86a8636960f53714937867cb4f79. Hardware source fef8043 and routed
overlay 571149b remain unchanged. Status: OFFLINE STUDY COMPLETE; NO NEW HLS,
RTL, IMPLEMENTATION OR BOARD RESULT. Candidate formats are not deployed.

## Scope and criteria

All fourteen supplied 255x255 frames: Butterfly from Set5 and thirteen Set14
cases. This is not a complete Set5/Set14 evaluation. The ten recorded asset
hashes are verified; additional input/GT and all six model hashes are saved in
study.json. Model/padding/channel order, bias-first MAC order, ReLU, rounding
and saturation are unchanged. All candidates retain signed 32-bit data/model
words; only the interpreted fractional count varies offline.

PSNR policy matches the previous official evaluation: normalized data,
peak=1, crop=0, no clamping or pixel rounding. Mean PSNR averages per-image dB.
Negative float-to-fixed loss means a small reconstruction improvement from
quantization; it is not proof of closer implementation agreement.

The proposed **engineering** screening criteria, not course requirements:

- Every supplied image: absolute float-vs-fixed reconstruction PSNR difference
  <=0.1 dB.
- Every supplied image: fixed-vs-float reference PSNR >=50 dB.
- No observed accumulator/data saturations, and an integer interval proof of
  no saturation for the exact quantized official model with inputs in [0,1].

These criteria are provisional and do not establish accuracy on missing or
unseen images. The minimum passing format refers only to the tested set;
9/11/13/etc. fractional bits were not tested.

## Results

| Data format (W=32) | Butterfly PSNR | Supplied Set14 mean PSNR | Max absolute per-image PSNR difference | Minimum fixed-vs-float PSNR | Engineering screen |
|---|---:|---:|---:|---:|---|
| Q24.8 | 25.164763 | 25.706424 | 9.631357 | 25.621040 | FAIL |
| Q22.10 | 27.475312 | 29.127641 | 0.140636 | 50.212929 | FAIL |
| Q20.12 | 27.473972 | 29.157484 | 0.004187 | 60.621163 | PASS |
| Q18.14 | 27.476547 | 29.158250 | 0.001065 | 77.116276 | PASS |
| Q16.16 | 27.476996 | 29.158668 | 0.001483 | 77.335911 | PASS |
| Q14.18 | 27.477111 | 29.158386 | 0.000508 | 89.733776 | PASS |
| Q12.20 | 27.477045 | 29.158460 | 0.000017 | 115.501195 | PASS |

Float reference: Butterfly 27.477042 dB, supplied Set14 mean 29.158458 dB.
All 98 image/format evaluations have zero accumulator and data saturations.
Each format's exact-official-model interval proof passes for all three layers.

Q22.10 fails on Foreman: float 35.747342 dB, fixed 35.606706 dB, loss
0.140636 dB. Q20.12's largest absolute difference is Bridge, 0.004187 dB.
Its lowest fixed-vs-float reference PSNR is ppt3, 60.621163 dB.

| Image | Float PSNR | Q20.12 PSNR | Float-to-fixed loss |
|---|---:|---:|---:|
| Butterfly | 27.477042 | 27.473972 | +0.003070 |
| Baboon | 27.920917 | 27.919903 | +0.001014 |
| Barbara | 24.991611 | 24.991580 | +0.000030 |
| Bridge | 26.244551 | 26.240364 | +0.004187 |
| Coastguard | 26.842501 | 26.840644 | +0.001857 |
| Face | 33.427739 | 33.423746 | +0.003994 |
| Flowers | 27.334236 | 27.333060 | +0.001176 |
| Foreman | 35.747342 | 35.749071 | -0.001729 |
| Lenna | 30.849669 | 30.848848 | +0.000821 |
| Man | 27.122054 | 27.121426 | +0.000628 |
| Monarch | 27.985379 | 27.981797 | +0.003582 |
| Pepper | 33.487997 | 33.489009 | -0.001012 |
| ppt3 | 29.439329 | 29.441998 | -0.002669 |
| Zebra | 27.666623 | 27.665850 | +0.000773 |

Q20.12 newly zeros 117/5184 Conv1 weights, 33/2048 Conv2 weights and 4/800
Conv3 weights, compared with 1205/464/55 at Q24.8. Its quantization step is
1/4096. More fractional bits do not guarantee monotonic reconstruction or
implementation error because the multiple layer errors interact.

## Observed and proven ranges

Q20.12 ranges across all supplied frames, including every partial MAC sum:

| Layer | Observed partial accumulator min/max | Observed layer output min/max | Exact-model interval output min/max | Exact-model absolute partial MAC bound |
|---|---|---|---|---:|
| Conv1 | -1.791992 / 1.999727 | 0 / 1.872559 | 0 / 7.224121 | 14.485107 |
| Conv2 | -0.972659 / 3.487642 | 0 / 3.487549 | 0 / 31.642822 | 63.111415 |
| Conv3 | -0.322138 / 1.080976 | 0.002441 / 1.038574 | -106.781738 / 100.414551 | 207.225115 |

The interval proof uses exact integer parameter codes, round-to-even at layer
boundaries and conservative per-channel intervals. It discards correlations
and covers replicate-edge samples at any spatial size, not just observed
pixels. It is conditional on this exact model and normalized inputs.

The current header declares all weights/biases <=1 and permits no worst-case
data saturation. Under that old contract only Q24.8 passes the current static
range guard. Increasing fractional bits alone will fail the guard; the all-ones
host stress case correctly saturates in the narrower integer ranges.

A separate **proposed**, upward-rounded official-model contract is:

| Layer | Weight absolute bound | Bias absolute bound | Derived Q20.12 preactivation absolute bound | Accumulator total / integer bits |
|---|---:|---:|---:|---|
| Conv1 | 600/1000 | 383/1000 | 48.990967 | 31 / 7 |
| Conv2 | 852/1000 | 85/1000 | 2671.623863 | 37 / 13 |
| Conv3 | 163/1000 | 29/1000 | 348563.475861 | 44 / 20 |

Input absolute bound is 1. Rational bounds are converted upward to raw codes,
exactly as numeric_config.hpp does. All official quantized parameters fit
these limits. Even the conservative generic whole-class chain fits Q20.12's
positive limit 524288-1/4096; no disabling of the range guard is needed under
this proposed contract. It is not a valid contract for all-ones weights or
arbitrary runtime models. Runtime input/model validation and separate legacy
wide-format regression configuration would be required before adoption.

The actual sweep and scalar host checks retain the **old** accumulator sizing:
for Q20.12, 32/38/48 total bits, all with 24 fractional bits. The proposed
31/37/44-bit accumulators were derived offline, not applied/compiled in HLS.
Their worst-case bound proof is separate from future implementation gates.

## Cross-checks

- Frozen Q24.8 compatibility: all fourteen final raw outputs and PSNR values
  match the previous evaluation exactly, 910350 output words in total.
- New numerical tests: 6/6 PASS, including old-guard preservation, signed
  halfway rounding, actual narrowing saturation and interval coverage.
- Existing deployment tests with RTL-checked vectors: 12/12 PASS. This
  reuses prior XSIM-validated vectors; no RTL simulation was run here.
- Separate scalar C++ ap_fixed check: all seven formats, 10008 quantizer
  values per format, five three-layer cases per format (35 cases). Signed
  random, ties, endpoint saturation, all-ones stress, and official 1x1/5x7/
  13x17 crops match all layer raw codes exactly.
- Additional Q20.12 full 255x255 Butterfly and Foreman scalar checks: each
  verifies 6307425 layer words, including 65025 final words, with zero
  mismatches. These call the scalar ap_fixed reference, not a changed HLS top.

## Recommendation and next hardware gate

Use **Q20.12 as the first numerical HLS experiment**, with explicitly reviewed
official-model range bounds and a separately versioned host/bundle format.
It is the lowest tested passing fractional count and has substantial accuracy
margin over the provisional 0.1 dB limit. Do not infer DSP, BRAM, latency, II,
5 ns timing or FPS from this offline study.

Preserve the current overlay and Q24.8 bundle/runner. A new candidate needs
explicit source configuration and host scaling/versioning, official-model
range checks, C-sim regression against the measured Q20.12 reference, fresh
RTL validation, synthesis and routed 5 ns timing/resource checks. Retain the
old wide-format regression for all-ones tests rather than silently weakening
its numerical assertions. No Conv, padding, FIFO or new pragma is proposed.

## Reproduction and evidence

Python 3 + NumPy 2.3.5:

```text
python tests/test_precision_study.py -v
python tools/study_official_precision.py --root PATH_TO_GOLDEN --out NEW_DIRECTORY --source-commit 6b9bba6dd4af86a8636960f53714937867cb4f79
```

Scalar host check (AMD bundled MinGW C++14, O2, no FMA):

```text
g++ -std=c++14 -O2 -ffp-contract=off -Ithird_party/HLS_arbitrary_Precision_Types/include tools/precision_host_check.cpp -o precision_host_check.exe
python tests/check_precision_ap_fixed.py --exe PATH_TO_EXE --root PATH_TO_GOLDEN --out NEW_CHECK_DIRECTORY
precision_host_check.exe 12 255 255 input_float.bin model_float.bin output_prefix
```

The last command writes output_prefix.conv1.bin / .conv2.bin / .conv3.bin as
signed raw int32 codes. Compare to infer_fixed(..., FixedFormat(32,12)) for
each layer. The main summary CSV is committed next to this report.

Full metrics, raw expectations, scalar output arrays, checksums and check
JSONs remain outside Git:
`C:\Users\xzype\Documents\Codex\2026-10-08\windows-codex-mac-github-windows-codex\outputs\precision-study`.
Files: sweep-even/study.json, sweep-even/summary.csv,
ap-fixed-check/check.json, full-ap-fixed-check.json. Generated binary assets,
executables and temporary projects are not committed.
