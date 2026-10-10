# P3: supplied official asset offline precision gate

Date: 2026-10-10. Software base: c3f8f4e; asset commit:
6b9bba6dd4af86a8636960f53714937867cb4f79. Current unchanged HLS source:
fef8043; routed overlay: 571149b. Branch: deploy/srcnn-axis-dataflow.
Status: OFFLINE EVALUATION COMPLETE FOR SUPPLIED IMAGES; BOARD PENDING;
NUMERICAL QUALITY NEEDS REVIEW. This is not complete Set5/Set14 validation.

## Provenance and metric policy

course-assets/golden.zip: 9,016,093 bytes; Git blob
`e6f734404f31a7f2f1340fce5199c2c455f9bcec`; SHA-256
`58cc7228f97dd94ff3e4d8f4d7b06ebc171255b916e36cac0974d902fe9c608f`.
All ten recorded model/Butterfly sizes and hashes match Aero's 7902143
manifest. Model: six files, 8129 float32 elements. Images: 255x255, already
bicubic; input/GT uint8 are normalized by float32 /255. The archive supplies
only Butterfly from Set5 and thirteen Set14 cases. The other four Set5 cases
are absent; no results are invented for missing images.

All reported PSNR is dB, peak=1, full-frame/crop=0, unclamped output, no pixel
rounding. Reconstruction vs GT is separate from implementation error vs
Golden. Starter util.cpp casts image*255 to uint8 for PSNR; that different
helper is not the metric used here. Some outputs are outside [0,1], and no
portable out-of-range conversion/clamping convention is inferred.

## Cross-checks

- Float Butterfly vs official final: MSE 3.1660971422452726e-14,
  maximum absolute error 9.5367431640625e-7.
- Float Conv1 vs official Conv1: MSE 3.462543650707288e-15,
  maximum absolute error 9.5367431640625e-7.
- Existing independent 13x17 integer-vs-RTL-checked-vector gate is exact.
- Compiled unchanged current HLS AXIS source with host ap_fixed and called
  srcnn_axis_dataflow_top for the full official Butterfly frame. All 65,025
  raw output words match the independent integer reference exactly. Input
  consumption/output count and TKEEP/TSTRB/TLAST pass. This is HLS C++ host
  execution, not new RTL simulation or physical board execution.
- Zero accumulator/data saturations across all fourteen supplied cases.
  Official model maximum magnitudes fit the unchanged declared <=1 bounds.

## Reconstruction quality

| Dataset/image | Bicubic vs GT | Float vs GT | Q24.8 vs GT | Float to fixed loss |
|---|---:|---:|---:|---:|
| set5/butterfly | 24.0568 | 27.4770 | 25.1648 | 2.3123 |
| set14/baboon | 27.3618 | 27.9209 | 25.5621 | 2.3588 |
| set14/barbara | 24.8997 | 24.9916 | 23.3852 | 1.6064 |
| set14/bridge | 25.2317 | 26.2446 | 24.3892 | 1.8554 |
| set14/coastguard | 26.3000 | 26.8425 | 24.7847 | 2.0578 |
| set14/face | 32.6794 | 33.4277 | 29.7353 | 3.6925 |
| set14/flowers | 25.6995 | 27.3342 | 25.6374 | 1.6968 |
| set14/foreman | 33.2014 | 35.7473 | 26.1160 | 9.6314 |
| set14/lenna | 29.1689 | 30.8497 | 26.8774 | 3.9722 |
| set14/man | 26.0613 | 27.1221 | 25.4051 | 1.7170 |
| set14/monarch | 24.5799 | 27.9854 | 25.4949 | 2.4905 |
| set14/pepper | 32.0454 | 33.4880 | 27.1886 | 6.2994 |
| set14/ppt3 | 26.6842 | 29.4393 | 24.0123 | 5.4270 |
| set14/zebra | 24.7423 | 27.6666 | 25.5954 | 2.0712 |

Thirteen supplied Set14 images: mean float PSNR 29.158458 dB; Q24.8
25.706424 dB; mean loss 3.452033 dB. Means are per-image dB averages, not
PSNR from pooled MSE. In 11/14 supplied cases fixed output scores below
bicubic under this policy. Worst loss: foreman, 9.6314 dB. Butterfly loss:
2.3123 dB. Fixed-vs-official-Golden Butterfly MSE: 0.001298922282241205;
PSNR 28.86416833071326 dB.

## Interpretation and next gate

Current Q24.8 has eight fractional bits, step=1/256. Quantization changes
1205/5184 originally nonzero Conv1 weights to zero (23.24%), 464/2048 Conv2
weights (22.66%) and 55/800 Conv3 weights (6.875%). These effects are observed;
layer narrowing also contributes, so weight error alone is not proven to
explain the full loss. Full-frame HLS/reference agreement establishes
arithmetic consistency. It does not establish negligible precision loss.
No course pass/fail threshold is fabricated.

Keep the current overlay frozen as a functional deployment checkpoint.
Next investigate fractional precision/range choices offline and define an
acceptable official-model quality gate. Any subsequent numerical change
needs a versioned experiment and renewed HLS/RTL/implementation validation.
No DUT/FIFO/pragma/numeric type or bitstream changed in this gate.

## Reproduction and evidence

Python 3 + NumPy 2.3.5. C++ host: AMD bundled MinGW, C++14/O2,
ffp-contract=off, SRCNN_HLS_FIXED_POINT=1, SRCNN_AXIS_DATAFLOW_HOST_SIM=1.
See docs/p3-host-and-offline-evaluation.md for the C++ compile command.

```text
python tools/evaluate_course_assets.py --root PATH_TO_EXTRACTED_GOLDEN --out NEW_OUTPUT_DIRECTORY --source-commit 6b9bba6dd4af86a8636960f53714937867cb4f79
```

Full JSON/CSV metrics, raw expectations, executable, source hashes,
saturation counts and model ranges remain outside Git:
`C:\Users\xzype\Documents\Codex\2026-10-08\windows-codex-mac-github-windows-codex\outputs\formal-evaluation`.
Files: all-supplied-cases/evaluation.json, summary.csv, hls-host-check.json,
and the verified Butterfly deployment bundle. Ignored local data/butterfly_deploy
is available to the notebook. Generated binaries/arrays and extracted course
files are not committed by this evaluation gate.
