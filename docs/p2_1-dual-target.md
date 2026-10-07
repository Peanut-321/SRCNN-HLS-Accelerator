# P2.1 dual-target skeleton

Status: implemented for host verification; not yet synthesized. This phase has
no HLS optimization or interface pragmas and deliberately stops before the P2.2
fixed-vs-float error harness.

## Separation boundary

- `hls/include/srcnn_hls/project_config.hpp` is the single home for topology,
  unresolved deployment inputs, dynamic-range assumptions, and explicit width
  overrides.
- `hls/include/srcnn_hls/numeric_config.hpp` derives the fixed-point types and
  accumulator widths. Structural changes must not alter this arithmetic policy.
- `hls/include/srcnn_hls/arithmetic.hpp` owns MAC, activation, and narrowing
  semantics.
- `hls/src/srcnn_hls.cpp` owns only shape/indexing and the natural loop nest
  `o -> oh -> ow -> i -> kh -> kw`.

`SRCNN_HLS_FIXED_POINT=0` makes `data_t` and all three accumulator aliases
`float`, which is the frozen-P1 compatibility path. Value `1` instantiates
`data_t` as `ap_fixed<W,I,AP_RND_CONV,AP_SAT>` and each layer accumulator as
`ap_fixed<ACC_W,ACC_I,AP_TRN,AP_SAT>`; all four template parameters are
explicit.

## Width derivation

For layer `l`, the topology derives `N = Cin * Kh * Kw` (81, 64, 800). The
course formula is retained as the reported MAC-only bound:

```text
MAC_bound = N * Xmax * Wmax
```

The actual accumulator also contains bias, so its safe bound is:

```text
preactivation_bound = MAC_bound + Bmax
```

The compile-time implementation works in integer raw codes. With `Fd` data
fractional bits and `Facc = 2*Fd`:

```text
Mraw = N * Xraw_max * Wraw_max + (Braw_max << Fd)
raw_magnitude_bits = ceil_log2(Mraw + 1)
ACC_I = 1 + raw_magnitude_bits - Facc
ACC_W = ACC_I + Facc
```

The `+1` is an endpoint guard: signed `ap_fixed<W,I>` has positive maximum
`2^(I-1) - 2^-F`, so a bound exactly equal to a power of two needs the next
integer bit. The default path always uses this derived width. Each layer has a
separate `{enabled, integer_bits}` override; all overrides are off in P2.1.

Current placeholders (`data_t` 32/24, and unit input/weight/bias absolute
bounds) produce:

| layer | N | MAC bound | preactivation bound | derived `ACC_I` | `ACC_W` |
|---|---:|---:|---:|---:|---:|
| Conv1 | 81 | 81 | 82 | 8 | 24 |
| Conv2 | 64 | 5248 | 5249 | 14 | 30 |
| Conv3 | 800 | 4,199,200 | 4,199,201 | 24 | 40 |

These are safety placeholders, not an optimized quantization choice. Official
weights and the input contract must replace their range inputs before P2.2 can
be accepted. `AP_SAT` prevents wraparound but does not itself expose a
saturation counter; P2.2 must compare a wider shadow value before narrowing.

## Deployment inputs resolved after P2.1

- `kDeploymentInputHeight/Width = 255` and `kMaxInputHeight/Width = 255` now
  encode the confirmed already-bicubic-upsampled course input geometry.
- The deployment boundary mode is stride 1 with replicate-edge padding 4/0/2.
  Explicit zero-same and valid modes remain available only for the frozen P1
  regression vectors. The centralized stride/padding constants drive both
  shape and sample indexing.
- all unroll factors are placeholder 1 and unused by pragmas until P0a gives
  the implemented overlay budget.
- line-buffer rows are parameterized as `K-1`, but no line buffer exists yet.
- tile size is temporarily the whole test frame; it is not a deployment choice.

## Frozen-P1 compatibility exception

The written network contract says "MAC accumulation, then bias, then
activation", but the frozen C++ Golden and Python oracle seed the accumulator
with bias and then execute the MACs. Those orders are mathematically equivalent
but not bitwise equivalent in binary32. Because this phase's acceptance gate is
explicitly bitwise against frozen P1, P2.1 mirrors the frozen bias-seeded order
and documents it in `arithmetic.hpp`. Resolving the semantic wording requires a
deliberate future spec/P1 re-baseline; it is not hidden inside this HLS rewrite.
This is an explicit decision gate before P2.2: either adopt frozen bias-first as
the normative executable contract, or formally re-baseline spec, P1, and all
vectors together before any nonzero fixed-vs-float tolerance is calibrated.

## Build and gates

```sh
make host-float
make host-fixed
```

The float gate loads all five frozen vector sets, verifies each committed dump
against a hard-coded FNV-1a checksum, compares every output element bit-for-bit,
and prints `preactivation_bound / observed_abs_max` per vector and in aggregate.
The fixed target locks the derived-width edge cases and all four type parameters,
runs zero and a small exactly representable sparse arithmetic path, and executes
the P2.2a five-vector fixed-vs-float harness. Error distributions and saturation
counts are recorded in `results/p2_2a-fixed-random.md`; deployment tolerance and
image-quality decisions remain in P2.2b.

Host fixed simulation uses the pinned open-source Xilinx AP types commit
`200a9aecaadf471592558540dc5a88256cbf880f`. Vitis synthesis uses the vendor
headers from the selected x86 Vitis installation instead. The provided Tcl
entry point requires the exact P0a part and target clock and has not been run on
this Mac.
