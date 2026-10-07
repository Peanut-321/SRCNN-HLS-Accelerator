# P2.2a fixed-point harness results — random regression vectors

Date: 2026-10-06  
Status: **PASS for P2.2a mechanism validation; not a deployment-quality result**

## Configuration

- DUT arithmetic: `ap_fixed<32,24,AP_RND_CONV,AP_SAT>` (`Q24.8`)
- Accumulators: per-layer widths derived from the declared operand bounds and
  MAC counts (`81`, `64`, `800`); no three manually selected integer widths
- Activation order: bias-first accumulator initialization, MAC accumulation,
  then ReLU for Conv1/Conv2; Conv3 has no activation or clamp
- Regression padding: the frozen five-vector suite retains zero-same and valid
  modes. A separate synthetic test checks the official replicate-edge mode.
- Reference: frozen float32 Golden dumps
- PSNR convention in this file only: `10 log10(1 / MSE)`, i.e. `R=1`

The vectors use random weights in approximately `[-1,1]`. Their Conv3 output
magnitude can exceed 300, so `R=1` PSNR is not a perceptual image-quality score.
For this suite, relative-L2 is the meaningful scale-normalized summary. Final
PSNR/SSIM requires the official trained weights, course images and the agreed
image-domain peak/range convention.

## Aggregate results

The table reports the worst value across the five cases unless a range is shown.

| Layer | max abs | max p99 abs | max MAE | max RMSE | relative-L2 range | minimum PSNR, R=1 | zero flips |
|---|---:|---:|---:|---:|---:|---:|---:|
| Conv1 | 0.0340617 | 0.0192304 | 0.00328683 | 0.00585480 | 0.25499%–0.27560% | 44.6498 dB | 40 |
| Conv2 | 0.146804 | 0.0758133 | 0.0135622 | 0.0232854 | 0.28420%–0.35468% | 32.6583 dB | 28 |
| Conv3 | 1.94983 | 1.58160 | 0.591728 | 0.690314 | 0.27088%–0.62282% | 3.21906 dB | 0 |

Across every case:

- source/input/weight/bias quantization saturation events: **0**;
- Conv1/Conv2/Conv3 narrowing saturation events: **0 / 0 / 0**;
- maximum observed pre-activation magnitude: **13.4417 / 44.1651 / 341.645**.

Large maximum-relative errors occur at reference values close to zero and must
not be treated as the main quality metric. The harness retains them for failure
diagnosis together with nearest-rank p50/p95/p99 absolute-error distribution,
max-absolute error and worst CHW coordinate.

## Cases executed

1. `fixed_seed`, 13×17, zero-same
2. `fixed_seed_valid`, 13×17, valid
3. `cosim_33x29`, 33×29, zero-same
4. `cosim_33x29_valid`, 33×29, valid
5. `naive_15x13`, 15×13, zero-same

The official deployment geometry is separately configured as 255×255 with
replicate-edge padding. `srcnn_hls_padding_modes` confirms that a 9×9 all-one
Conv1 applied to a 1×1 input produces corner output `81` under replicate-edge,
versus `1` under zero padding, and rejects an invalid padding selector.

## Reproduction

```sh
make host-fixed
./build-p2-fixed/srcnn_hls_fixed_vectors
```

The host AP-type headers come from Xilinx
`HLS_arbitrary_Precision_Types`, pinned to commit
`200a9aecaadf471592558540dc5a88256cbf880f`. Vitis synthesis must use the
vendor headers shipped with the selected Vitis version.

## Remaining P2.2b gate

P2.2 is not complete. The formal weights and course images/reference outputs
used during Golden validation are not present in the current working tree.
After they are restored locally, rerun the same harness with:

- official trained weights and their checksums;
- `[0,1]` bicubic-upsampled 255×255 course input;
- official float Golden layer/output dumps;
- a frozen image-domain PSNR/SSIM convention and pass threshold;
- per-source and per-layer saturation checks.

Only that run may freeze deployment `data_t`, implementation tolerances, and
claim image-quality preservation. No latency, II, FPGA resource, clock, or
throughput conclusion is made by this Mac host test.
