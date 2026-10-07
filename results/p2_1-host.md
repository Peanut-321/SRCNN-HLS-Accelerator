# P2.1 host verification record

Date: 2026-09-11 (Australia/Melbourne)

Version identity: `results/p2_1-source.sha256`. The repository has no Git
metadata, so this source-hash list is the independent checkpoint for the P2.1
version. A separate pre-edit inventory of every frozen P1 source, dump, vector,
manifest, tolerance/oracle file, and `spec.md` was captured before P2.1 and
rechecked after it; every entry reported `OK`. That baseline is preserved as
`results/p1-frozen-before-p2_1.sha256`.

Because this directory is not a Git repository, the complete source state
(including frozen P1, vectors, and P2.1) is also saved as the recoverable
`results/p2_1-complete-source.tar.gz`; its adjacent `.sha256` file authenticates
the archive.

## Environment

- host: macOS arm64
- compiler: Apple clang 17.0.0 (`clang-1700.0.13.5`)
- host language mode: C++17; synthesizable source also compiled separately as
  C++14
- floating-point contraction: off
- host fixed simulation headers: Xilinx
  `HLS_arbitrary_Precision_Types`, commit
  `200a9aecaadf471592558540dc5a88256cbf880f`

## Correctness gates

| Gate | Result |
|---|---|
| frozen P1 unit executable (14 internal cases) | PASS |
| `fixed_seed`, same 13x17, all three layers + final output | bitwise PASS |
| `fixed_seed_valid`, valid 13x17, all three layers + final output | bitwise PASS |
| `cosim_33x29`, same 33x29, all three layers + final output | bitwise PASS |
| `cosim_33x29_valid`, valid 33x29, all three layers + final output | bitwise PASS |
| `naive_15x13`, same 15x13, all three layers + final output | bitwise PASS |
| fixed aliases/modes + width edge regressions + zero/sparse paths + synthesizable top | PASS |
| ASan + UBSan, unit and five-vector float gate | PASS |
| fixed synthesizable source, AppleClang C++14 syntax compile | PASS |
| optimization-pragma audit under `hls/` | PASS: zero `#pragma HLS` lines |

The vector gate checks both the loaded dump's frozen FNV-1a checksum and every
float's 32-bit representation. It uses independent output buffers for the
diagnostic natural path and actual `srcnn_hls_top`; top buffers begin as NaNs so
an unwritten element cannot inherit a passing value. Every loaded operand is
also checked against the dynamic-range configuration before a bound is called
"worst case".

## Bound gap from all five vectors

| layer | MAC-only bound | bias-inclusive bound | observed preactivation `abs_max` | bound / observed |
|---|---:|---:|---:|---:|
| Conv1 | 81 | 82 | 13.45200 | 6.095749x |
| Conv2 | 5,248 | 5,249 | 44.20818 | 118.7337x |
| Conv3 | 4,199,200 | 4,199,201 | 341.9849 | 12,278.91x |

These gaps come from synthetic random weights and are placeholders only. They
demonstrate that the reporting path works; they are not permission to tighten
the default worst-case accumulator widths. Official weights and the confirmed
input range must be measured again before OPT-D.

## HLS metrics ledger

| Metric | P2.1 value |
|---|---|
| target part | NOT CONFIRMED (P0a dependency) |
| target clock | NOT CONFIRMED (P0a dependency) |
| latency | NOT MEASURED (requires x86 Vitis csynth) |
| II | NOT MEASURED (requires x86 Vitis schedule report) |
| LUT / FF / DSP / BRAM | NOT MEASURED (requires x86 Vitis csynth) |
| timing closure | NOT RUN (P0b/post-implementation) |

No estimate is substituted for a tool report. The provided Vitis Tcl entry
requires the exact P0a part and clock explicitly, so it cannot silently produce
a report against an invented target.

## Recheck commands

```sh
shasum -a 256 -c results/p1-frozen-before-p2_1.sha256
shasum -a 256 -c results/p2_1-source.sha256
make host-float
make host-fixed AP_TYPES_INCLUDE_DIR=/path/to/HLS_arbitrary_Precision_Types/include
```

## Known semantic exception

The frozen P1 implementation seeds each float accumulator with bias, whereas
the prose formula states MAC first and bias second. Reordering bias changes many
binary32 low bits and makes the required frozen-vector bitwise gate impossible.
P2.1 therefore preserves the frozen order and makes the exception explicit in
the arithmetic header and design note. This must be resolved explicitly before
P2.2: either freeze bias-first as the executable contract or formally
re-baseline spec, P1, and vectors together. No P1 file or tolerance was changed.
