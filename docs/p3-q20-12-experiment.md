# Official Q20.12 host experiment

This is an opt-in numerical experiment. The default Q24.8 build, V1 bundles,
PYNQ runner, existing RTL checkpoints and routed overlay retain their original
contract. This branch does not provide a Q20.12 bitstream or board runner.

## Numerical contract

Enable **both** `SRCNN_HLS_FIXED_POINT=1` and
`SRCNN_HLS_OFFICIAL_Q20_12=1` in every design and testbench translation unit.
The second switch defaults to zero; enabling it in a float build is rejected.

| Quantity | Contract |
|---|---|
| Data/model word | Signed 32-bit Q20.12; integer count includes sign |
| Data rounding / saturation | AP_RND_CONV / AP_SAT |
| Conv1/2/3 accumulators | 31/37/44 total bits, 7/13/20 integer bits |
| Accumulator fractional bits | 24, retaining full product precision |
| Accumulator rounding / saturation | AP_TRN / AP_SAT |
| Host input domain | Finite normalized floats in [0,1] |
| Padding, model order, MAC order | Existing replicate-edge OC4/DATAFLOW behavior |

The six upward-rounded official model bounds are, in model-buffer order:

| Block | Absolute bound | Conservative quantized raw bound |
|---|---:|---:|
| Conv1 weights | 600/1000 | 2458 |
| Conv1 bias | 383/1000 | 1569 |
| Conv2 weights | 852/1000 | 3490 |
| Conv2 bias | 85/1000 | 349 |
| Conv3 weights | 163/1000 | 668 |
| Conv3 bias | 29/1000 | 119 |

These are the conservative official-model bounds examined in
[the precision study](../results/p3-official-precision-study.md). Each raw
bound uses ceil(bound * 4096), also covering rounding at the boundary. The
derived preactivation bounds are 48.9909668, 2671.6238632 and 348563.4758606.
All fit Q20.12; accumulator overrides remain disabled and
`kAllowWorstCaseDataSaturation` remains false. Arbitrary/all-ones models are
outside this experiment's contract and continue to use the legacy tests.

Preparation checks the original floating values and their float32
representations before quantization. Bounds use strict rational comparisons;
a float32 value slightly above a rational boundary is rejected. The RTL has
no runtime range checker: a future runner must enforce this host contract.

## Host build and regression

```text
cmake -S . -B build-q20-12 -DCMAKE_BUILD_TYPE=Release -DSRCNN_BUILD_HLS_FIXED_SIM=ON -DSRCNN_BUILD_HLS_OFFICIAL_Q20_12_HOST=ON
cmake --build build-q20-12
ctest --test-dir build-q20-12 --output-on-failure
python tests/test_q20_12_bundle.py
python tests/test_precision_study.py
python tests/test_deployment_host.py
```

The new CMake option builds a separate HLS library and three executables:
`srcnn_hls_official_q20_12_contract`, `srcnn_axis_dataflow_official_q20_12`,
and `srcnn_axis_q20_12_raw_host`. Legacy fixed targets still compile Q24.8.
The candidate stream fixture uses normalized inputs and a Conv3 bias within
the new bound; the legacy fixture and all its assertions remain unchanged.

On this Windows installation, use the AMD bundled g++ with the CMake
`MinGW Makefiles` generator and `mingw32-make.exe`. Ninja stalled during the
compiler ABI probe. If a test reports missing `libgcc_s_seh-1.dll`, place
`libgcc_s_seh-1.dll`, `libstdc++-6.dll` and `libwinpthread-1.dll` from that same
compiler's bin directory beside the test executables. This is a local runtime
setup step; do not commit the DLLs.

## Separate V2 bundle

```text
python tools/prepare_srcnn_q20_12.py --input data/butterfly_float/input_float.npy --model data/butterfly_float/model_float.npy --golden data/butterfly_float/course_golden.npy --ground-truth data/butterfly_float/ground_truth.npy --out data/butterfly_q20_12
python pynq/srcnn_q20_12_bundle.py --bundle data/butterfly_q20_12
```

The destination must be new. Files are little-endian uint32 raw words:
65,025 input, 8,129 model and 65,025 expected output words. The schema is
`SRCNN_DEPLOYMENT_BUNDLE_V2`, profile `official_q20_12_v1`. The manifest
records the exact numeric contract, model layout, source hashes, artifact
hashes and counts. The reader checks these plus semantic raw input/model
ranges. Output is signed and decoded by division by 4096 without clamping.

The old Q24.8 runner rejects V2; the new reader rejects V1. The new module
only inspects bundles and does not program hardware. SHA checks provide
integrity; they do not certify that an arbitrary bundle matches a bitstream.

For independent host comparison, the raw runner takes float32 binary input
and model files and writes raw output:

```text
build-q20-12/srcnn_axis_q20_12_raw_host input_float.bin model_float.bin output_q20_12.bin 255 255
```

It validates input/model ranges, calls the real fixed deployment top, checks
stream counts and TKEEP/TSTRB/TLAST, and emits the active widths. Compare its
65,025 words with the V2 `expected.npy`, without using the Q24.8 decoder.

## Vitis and independent RTL reproduction

The Windows checkpoint is recorded in
[p3-q20-12-vitis.md](../results/p3-q20-12-vitis.md). Vitis C simulation,
two independent fixed 13x17 RTL cases and deployment synthesis/export
completed. The initial Conv1 MAC II regression from 1 to 2 is resolved by
[direct accumulator writeback](../results/p3-q20-12-conv1-writeback.md):
fresh synthesis restores II=1, independent RTL outputs remain identical,
and the full-frame host output is unchanged. Q20.12 remains opt-in; the
existing Q24.8 overlay and deployment default are not replaced.

From the repository root in PowerShell, use new output directories:

```powershell
$q20Root = 'C:\fpga\q20-12-validation'
& .\hls\scripts\run_axis_q20_12_hls.ps1 -WorkRoot $q20Root
python .\tools\prepare_q20_12_rtl_vectors.py --out "$q20Root\vectors-fixture"
python .\tools\prepare_q20_12_rtl_vectors.py --input .\data\butterfly_float\input_float.npy --model .\data\butterfly_float\model_float.npy --out "$q20Root\vectors-official"
& .\hls\scripts\run_axis_q20_12_rtl.ps1 -Component "$q20Root\small_13x17_5ns" -Vectors "$q20Root\vectors-fixture" -WorkDir "$q20Root\rtl-fixture"
& .\hls\scripts\run_axis_q20_12_rtl.ps1 -Component "$q20Root\small_13x17_5ns" -Vectors "$q20Root\vectors-official" -WorkDir "$q20Root\rtl-official"
& .\hls\scripts\run_axis_q20_12_rtl.ps1 -Component "$q20Root\small_13x17_5ns" -Vectors "$q20Root\vectors-fixture" -WorkDir "$q20Root\rtl-negative" -RejectCorruptGolden
```

These helpers default to AMD tools under `C:\AMDDesignTools\2026.1`;
override `-VitisRoot` / `-VivadoRoot` if needed. Python requires NumPy.
The HLS helper creates both components, runs small C simulation, synthesizes
both tops, and records source hashes. `-Stage prepare` only writes configs.
The RTL helper reuses the existing independent SV scoreboard, validates
source/vector hashes and profile before running XSim, and records RTL
hashes. It does not run the Vitis automatic UVM co-sim harness.

The official case is a 13x17 input crop with a freshly computed replicate
Golden for that small frame. It is not a full-frame RTL test. The negative
run must reject a corrupted first expected word. Source changes after
component preparation require a new component. Existing output directories
are rejected rather than overwritten.

Only the IP under `deployment_255x255_5ns` has the fixed deployment top.
Ignore the diagnostic IP automatically generated for `small_13x17_5ns`.
Keep all build outputs, RTL/WDB and export ZIP files outside Git.

## Full-frame and consecutive-start RTL reproduction

[The full-frame checkpoint](../results/p3-q20-12-full-frame-rtl.md) passes
two complete fixed 255x255 transactions without resetting the DUT. The
second transaction changes every input pixel and one legal model bias.
All 130,050 outputs match independent integer Golden; the existing RTL
is reused without another synthesis or DUT change.

Prepare the V2 bundle above first, then use new work directories:

```powershell
python .\tools\prepare_q20_12_rtl_vectors.py --input .\data\butterfly_float\input_float.npy --model .\data\butterfly_float\model_float.npy --restart --out "$q20Root\vectors-restart-small"
& .\hls\scripts\run_axis_q20_12_rtl.ps1 -Component "$q20Root\small_13x17_5ns" -Vectors "$q20Root\vectors-restart-small" -WorkDir "$q20Root\rtl-restart-small" -FrameCount 2
& .\hls\scripts\run_axis_q20_12_rtl.ps1 -Component "$q20Root\small_13x17_5ns" -Vectors "$q20Root\vectors-restart-small" -WorkDir "$q20Root\rtl-restart-negative" -FrameCount 2 -RejectSecondFrameGolden
python .\tools\prepare_q20_12_rtl_vectors.py --bundle .\data\butterfly_q20_12 --deployment --restart --out "$q20Root\vectors-restart-full"
& .\hls\scripts\run_axis_q20_12_rtl.ps1 -Component "$q20Root\deployment_255x255_5ns" -Vectors "$q20Root\vectors-restart-full" -WorkDir "$q20Root\rtl-restart-full" -Deployment -FrameCount 2
```

The full run took approximately 83 minutes on this Windows machine and
prints progress every two million cycles. Each frame must read all 8,129
model words, match every output and complete real DUT `ap_done`; the
negative run must finish frame one before rejecting frame two's output 0.
The runner saves port WDBs and source/RTL/vector manifests. These tests use
the independent SV harness, not Vitis autotb/UVM.

## Next gate

The host checkpoint is in
[p3-q20-12-host-checkpoint.md](../results/p3-q20-12-host-checkpoint.md).
The direct-writeback checkpoint establishes II=1, resource estimates and
small-frame RTL correctness without changing the numeric contract. Full-frame
and no-reset restart coverage now pass as recorded above. Next verify the
candidate's integration and routed timing, then its matching Q20.12 runner.
Any deployment export must use `srcnn_axis_dataflow_top`. Existing Q24.8
components/RTL/overlays remain separate. Routed implementation and board
validation have not been completed for Q20.12; estimated top slack remains
zero. Use short work paths to avoid Windows RTL-generator path limits.
