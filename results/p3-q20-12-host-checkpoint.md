# P3: opt-in official Q20.12 host checkpoint

Date: 2026-10-10. Branch: `optimize/official-q20-12`.
Base: `5f0216704cdd7ba70e2c8a493469c2df97e32259`.
Official asset source: `6b9bba6dd4af86a8636960f53714937867cb4f79`.
Status: **HOST VERIFIED; Q20.12 HLS/RTL/IMPLEMENTATION/BOARD GATES PENDING**.

## Change

The default fixed configuration remains Q24.8. Explicitly enabling
`SRCNN_HLS_OFFICIAL_Q20_12=1` selects signed 32/20/12 data and the conservative
official model bounds. Existing range derivation produces 31/37/44-bit
accumulators with 24 fractional bits. No accumulator override, saturation
guard relaxation, convolution change, padding/layout change, FIFO change or
new pragma was made. The Q20.12 profile requires a fixed-point build.

Host preparation and decoding use a separate V2 bundle/profile. All six model
blocks and normalized inputs are checked before quantization. The old runner
rejects V2; the new reader rejects V1 and checks hashes, lengths, dtype,
layout, the full numerical contract and raw ranges. Existing routed Q24.8
hardware is not compatible with this experiment's words.

## Verification

Windows GNU g++ 9.5.0 bundled with AMD tools 2026.1, CMake 4.0.1,
MinGW Makefiles, Release build, FMA contraction disabled. The HLS host
targets use C++14 and the pinned simulation AP types commit
`200a9aecaadf471592558540dc5a88256cbf880f`. Python uses NumPy 2.3.5.
This is host compilation using simulation AP types, not Vitis C Simulation.

| Check | Result |
|---|---|
| CMake build and CTest, legacy plus candidate | 19/19 PASS |
| Candidate codec/bundle/range/worst-case tests | 9/9 PASS |
| Existing precision study tests | 6/6 PASS |
| Existing deployment tests with old XSIM-checked vectors | 12/12 PASS |
| Candidate stream top vs OC4, 1x1 / 5x7 / 13x17 | 3/3 frames exactly equal |
| Real candidate deployment top, Butterfly 255x255 | 65,025/65,025 raw words exactly equal to independent integer reference |
| All supplied images, independent reference with 31/37/44-bit accumulators | 14/14 exactly equal to earlier Q20.12 sweep output |
| Observed reference accumulator/data saturation | 0 across all 14 images |
| Invalid switch / candidate float build | Rejected at compile time |
| Out-of-range input / all-ones model passed to candidate raw runner | Rejected before calling the top |

The candidate C++ contract test checks widths, static range guards,
signed nearest/even half-way rounding, raw codec scale and saturation
endpoints. The independent integer worst-case test uses input raw 4096 and
ceil-rounded positive weight/bias bounds, reaches an output above 348,000,
and agrees with wider accumulators without saturation. Legacy regression
targets retain their original wider model domain and assertions.

Initial CTest launches encountered missing MinGW runtime DLLs. Supplying the
three matching compiler runtime DLLs beside the executables resolved this;
the complete 19-test run then passed. The failed Ninja ABI probe was replaced
by the MinGW Makefiles generator; no source workaround was needed.

## Numerical quality

Metric policy: normalized peak 1, crop 0, no output clamp or pixel rounding.
There is one supplied Set5 image and thirteen supplied Set14 images; these
are not complete benchmark sets.

| Metric | Result |
|---|---:|
| Butterfly candidate vs float MSE | 5.4344149900874e-7 |
| Butterfly candidate vs float PSNR | 62.648472 dB |
| Butterfly maximum absolute candidate/float difference | 0.002535522 |
| Butterfly candidate vs GT PSNR | 27.473972 dB |
| Butterfly float vs GT PSNR | 27.477042 dB |
| Supplied Set14 candidate mean GT PSNR | 29.157484 dB |
| Supplied Set14 float mean GT PSNR | 29.158458 dB |
| Maximum absolute per-image reconstruction PSNR change, 14 images | 0.004187 dB |
| Minimum candidate vs float PSNR, 14 images | 60.621163 dB |

The all-image quality values carry forward the earlier precision study
because the new derived-width outputs were checked bit-for-bit against all
14 earlier Q20.12 outputs. The full Butterfly bundle was independently
regenerated with the new widths and checked against the actual HLS host top.
Host success establishes neither new hardware throughput nor timing.

## Local artifacts

Root:
`C:\Users\xzype\Documents\Codex\2026-10-08\windows-codex-mac-github-windows-codex\outputs\q20-12-profile`

- `cmake-make-host/Testing/Temporary/LastTest.log`: complete 19-test pass.
- `butterfly-bundle-v2/`: V2 input/model/expected, manifest and metrics.
- `butterfly_hls_raw.bin`: real deployment-top host output.
- `all14-derived-accumulators.json`: per-image equality and saturation diagnostics.
- `negative-gates.json`: compile/runtime rejection evidence.

Generated bundles, raw files, binaries and build directories are not committed.
See [reproduction instructions](../docs/p3-q20-12-experiment.md).

## Next step

Run separate Q20.12 Vitis C simulation and synthesis, then verify generated
RTL and compare timing/resources against Q24.8. The present branch does not
promote Q20.12 to the default, change the old hardware runner or enter Vivado
integration/board testing.
