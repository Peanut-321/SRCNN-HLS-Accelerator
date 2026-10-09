# SRCNN Golden Reference (W1)

Sequential C++17 golden reference for the three-layer SRCNN network:

```text
CHW input -> Conv1 1x9x9x64 + bias + ReLU
          -> Conv2 64x1x1x32 + bias + ReLU
          -> Conv3 32x5x5x1 + bias
```

Weights use logical `OIHW` order and convolution uses cross-correlation (the kernel is
not flipped). Each layer can be called independently with `SRCNN::run_layer`.

This frozen internal Golden predates the now-confirmed course boundary contract:
its `same` mode means stride 1 with zero padding 4/0/2, while `valid` means zero
padding 0/0/0. Those modes remain unchanged for P1 regression compatibility. The
deployment HLS path separately implements the official 255×255 replicate-edge
contract. No normalization, image conversion, clamp, or rounding is performed by
the internal Golden.

## Build and test

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
ctest --test-dir build --output-on-failure
```

The test executable prints every required case separately. It includes zero, bias,
all-ones hand calculations, asymmetric impulse, sparse OIHW routing, signed/ReLU,
centre/edge/corner, minimum dimensions, full 13x13 valid SRCNN, fixed-seed random,
independent-layer, dump round-trip, and malformed parameter file cases.

## Generate reusable fixed-seed vectors

```sh
./build/srcnn_vector_gen vectors/fixed_seed same 13 17 1592594996
./build/srcnn_vector_gen vectors/fixed_seed_valid valid 13 17 1592594996
```

The default seed is `0x5EED1234` (`1592594996`). The two sets share the seed, so the
input and weights are identical and only the padding (4/0/2 vs 0/0/0) differs.
Generation writes:

```text
vectors/fixed_seed/
  manifest.txt
  model/conv{1,2,3}_{weights,bias}.tensor
  dumps/input.tensor
  dumps/conv{1,2,3}.tensor
  dumps/output.tensor
  dumps/run_manifest.txt
```

`conv3.tensor` and `output.tensor` intentionally contain identical values: the former
is the named layer output and the latter is the stable final-output filename used by
downstream testbenches.

### Cosimulation vectors (33×29) and naive micro vector (15×13)

```sh
./build/srcnn_vector_gen vectors/cosim_33x29       same  33 29 20260910
./build/srcnn_vector_gen vectors/cosim_33x29_valid valid 33 29 20260910
./build/srcnn_vector_gen vectors/naive_15x13       same  15 13 987654321
```

The `33×29` pair is the HLS cosimulation stimulus (deliberately **not** 32×32: a
non-power-of-two spatial extent exercises the row/column edge handling that a clean
power-of-two would mask). The `same`/`valid` variants share seed `20260910`, so their
input and weights are identical and only the padding differs — the same property the
`fixed_seed` pair has. `15×13` is a minimal micro vector for the naive (unoptimized)
dual-target reference in P2, on its own seed `987654321` so its random draws are
independent of every other set. All three are regenerable from the commands above and
carry the toolchain fingerprint in their `manifest.txt`.

## Run with saved input and model

```sh
./build/srcnn_run \
  --input vectors/fixed_seed/dumps/input.tensor \
  --model-dir vectors/fixed_seed/model \
  --output-dir run_output \
  --padding same
```

The program reports each output shape and checksum. Any layout, shape, count,
short/extra data, or checksum mismatch fails with a file-specific error.

See [docs/tensor-format.md](docs/tensor-format.md) for the exact dump contract.

## Independent cross-validation oracle

The dumps under `vectors/fixed_seed*/dumps/` are produced by this codebase itself
(`srcnn_vector_gen` -> `SRCNN::run_and_dump`), so they are **not** an independent
oracle: a systematic convolution bug would be baked into them. `tools/cross_validate_golden.py`
re-derives every layer from the raw `.tensor` files using the spec formula directly
(cross-correlation, zero padding) — pure Python standard library, no torch/numpy, and
it never imports or calls the C++ side. Its independence contract (never adjust the
oracle to make it pass; if they disagree, check both sides) is written at the top of
the file.

It validates **every committed vector set** — `fixed_seed` (same) + `fixed_seed_valid`
(valid), the `cosim_33x29` pair (same + valid), and `naive_15x13` (same) — so the gate
is never run only on the vectors that happen to pass. Per layer it reports: dynamic
range (`min`/`max`/`abs_max`, the 99.9th percentile of `|value|`, and the pre-activation
accumulator range), `max_abs`/`max_rel` error, the count of elements violating
`|dut-ref| <= atol + rtol*|ref|` together with the worst element's `(c,h,w)`, and a
row/column histogram of *every* violating coordinate (a padding/edge bug clusters at the
border; accumulation noise does not).

**Tolerance is per-layer, not one global number.** Both sides are binary32, so the only
legitimate difference is accumulation-order noise, and its floor is structurally
determined by accumulation depth (`n`-term binary32 sums drift ~ `n·eps·|terms|`,
`eps≈1.2e-7`). A single `atol` was the bug: `1e-5` is ~0.04× conv3's floor (dead at
small `|ref|`) while `1e-3` is ~450× conv1's floor (a real conv1 bug at 1e-4 would pass
silently). The gate is set to ~10× each layer's cross-confirmed floor:

| layer | terms | measured `max_abs` | `atol` | `rtol` |
|---|---|---:|---:|---:|
| conv1 | 81 | 2.2e-6 | 2e-5 | 1e-4 |
| conv2 | 64 | 7.8e-6 | 1e-4 | 1e-4 |
| conv3 | 800 | 2.3e-4 | 2e-3 | 1e-4 |

`rtol=1e-4` is unchanged and fine everywhere (far above float32 relative precision);
only `atol` scales with the layer. These live in `TOL_ORACLE_FP32` in the script, kept
**separate from `TOL_IMPL_VS_GOLDEN`** — the P2/P3 fixed-point-vs-golden comparison,
whose difference is quantization error (orders of magnitude larger, width-dependent,
judged by PSNR + per-layer error distribution, not raw abs error). The two never share
constants; `TOL_IMPL_VS_GOLDEN` is a placeholder filled when the fixed-point path lands.

```sh
python3 tools/cross_validate_golden.py                    # all 5 committed vector sets
cmake -S . -B build -DSRCNN_ENABLE_ORACLE_TESTS=ON        # register the oracle (opt-in)
ctest --test-dir build -L oracle                          # cross-validation
ctest --test-dir build -L unit                            # unit tests only
```

**Result (2026-09-10):** all five sets pass. The only differences are accumulation-order
noise, and their magnitude grows exactly with accumulation depth (81 → 64 → 800 terms,
`max_abs` ≈ 2.2e-6 → 7.8e-6 → 2.3e-4) — growth that is monotonic with term count rather
than jumping to O(1) is independent evidence of rounding noise, not a semantic bug. The
measured per-layer floor is written back into each vector set's `manifest.txt` as
`noise_floor_conv{1,2,3}` lines, so a future toolchain/platform change can be checked for
numerical equivalence by re-running the oracle and diffing those lines.

A ReLU boundary guard is built in: elements where the reference is exactly 0 are counted
separately ("zero flips") rather than folded into `max_rel` or silently skipped, and
their coordinates are histogrammed apart from ordinary violations. In float32 there are
none; this counter becomes the P2 fixed-point diagnostic separating benign near-zero
flips from real quantization error. The per-layer dynamic range and 99.9th percentile
are the starting inputs for `ap_fixed` integer bit-width and accumulator sizing.

> **Fixed-point numbers are placeholders, not design inputs.** The dynamic-range
> pipeline above is fully wired and running, but the values it prints come from
> **random weights** (`srcnn_vector_gen` draws them from a fixed seed). Random weights
> are not representative of the trained SRCNN distribution, so these ranges and
> percentiles must **not** be used to size `ap_fixed` integer/accumulator widths yet —
> re-run the same pipeline after the official weights land. One further caveat: the
> 99.9th percentile is only meaningful when `n` (elements per layer) is comfortably
> above 1000; conv3 has at most 957 elements in the cosim set (and only 195 in the
> 15×13 micro vector), so its p99.9 is not a reliable tail estimate and should be read
> as `abs_max` for now.

**Reproducibility.** With `-ffp-contract=off`, the golden reference is bit-identical
across `-O0` and `-O3` on this ARM machine (verified by diffing the regenerated
checksums). That is a necessary condition only; the real cross-platform test is the
same generation run on the teammate's x86 machine, diffed against these checksums —
now a one-command check against the `toolchain`/`noise_floor` lines already in the
manifests.

## P2.1 dual-target HLS skeleton

The isolated `hls/` implementation now has a float compatibility target and an
`ap_fixed` host-simulation target. It keeps arithmetic/type policy separate from
the natural loop structure and contains no optimization pragmas. Build and run
the frozen five-vector bitwise gate with:

```sh
make host-float
```

The fixed host tests use the bundled Xilinx AP-types checkout pinned at
`200a9aecaadf471592558540dc5a88256cbf880f` by default. An alternate checkout
can still be selected explicitly:

```sh
make host-fixed
# Optional override:
make host-fixed AP_TYPES_INCLUDE_DIR=/path/to/HLS_arbitrary_Precision_Types/include
```

See [docs/p2_1-dual-target.md](docs/p2_1-dual-target.md) for the derived
accumulator-width equations, placeholder/TBD registry, float compatibility
exception, and Vitis entry point. The P2.2a random-vector quantization results
and their interpretation limits are recorded in
[results/p2_2a-fixed-random.md](results/p2_2a-fixed-random.md).

## P2.5 AXI-Stream + DATAFLOW checkpoint

The deployment branch connects the three layers with internal streams and
removes the full Conv1/Conv2 feature-map arrays. Run both Mac gates with:

```sh
make host-axis-dataflow
```

The fixed deployment wrapper accepts one 255x255 image through AXI4-Stream,
returns one 255x255 image through AXI4-Stream, and reads one contiguous runtime
model buffer from PS DDR. See
[docs/p2-axis-dataflow.md](docs/p2-axis-dataflow.md) for the exact beat, TLAST,
internal channel-order, and model-offset contracts. The Vitis 2026.1 synthesis
and RTL co-simulation gate is intentionally separate from the Mac result.
