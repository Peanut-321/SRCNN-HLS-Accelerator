# `SRCNN_TENSOR_V1` dump format

The golden reference, HLS testbench, and board test use the same UTF-8 text format.
Whitespace separates tokens; line wrapping inside `data` is insignificant.

```text
SRCNN_TENSOR_V1
name conv1_weights
dtype float32
layout OIHW
ndim 4
shape 64 1 9 9
count 5184
checksum_fnv1a64 0123456789abcdef
data
0.25 -0.5 ...
```

Fields have a fixed order:

1. `name` is a whitespace-free descriptive identifier.
2. `dtype` is exactly `float32` in W1.
3. `layout` is `CHW` for feature maps, `OIHW` for weights, or `O` for bias.
4. `ndim` is the number of extents following `shape`.
5. `count` must equal the product of all shape extents.
6. `checksum_fnv1a64` is lower-case, 16-digit FNV-1a over each float's IEEE-754
   binary32 bytes in least-significant-byte-first order. It detects accidental file
   or transfer corruption; it is not a cryptographic signature.
7. `data` contains exactly `count` finite or non-finite C++ float tokens in flattened
   row-major layout. Writers use `max_digits10`, so finite float32 values round-trip
   exactly.

Flattening formulas are:

```text
CHW:  ((c * H) + h) * W + w
OIHW: (((o * I) + i) * KH + kh) * KW + kw
O:    o
```

`run_manifest.txt` records operation semantics, every layer's channels, kernel,
stride, padding and activation, plus checksums for the input and all three outputs.
The separate vector-set `manifest.txt` also records the random seed.

