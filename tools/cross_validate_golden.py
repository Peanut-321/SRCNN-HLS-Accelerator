#!/usr/bin/env python3
"""Cross-validate the golden dumps against an independent reference.

The dumps under vectors/*/dumps/ are produced by srcnn.cpp itself (via
tools/srcnn_vector_gen.cpp -> SRCNN::run_and_dump), so they are NOT an
independent oracle: any systematic convolution-semantics bug in srcnn.cpp is
baked into them. This script re-derives each layer from the raw SRCNN_TENSOR_V1
files using the spec formula (section 3.1) -- cross-correlation with zero
padding, which is exactly what torch.nn.functional.conv2d computes by default:

    Y[o,h,w] = b[o] + sum_{c,i,j} W[o,c,i,j] * X[c, h*S+i-P, w*S+j-P]
    (X is zero outside [0,H)x[0,W))

It is deliberately written from the formula and from the frozen network in
spec.md, not from srcnn.cpp, so it shares none of that code's indexing / layout
/ orientation conventions. A systematic bug shows up as O(1) element errors;
the only legitimate difference is ~1e-6..1e-4 floating-point noise from a
different accumulation order, whose magnitude grows with accumulation depth.

Dependencies: Python 3 standard library only (no torch/numpy needed).

Usage:
    python3 tools/cross_validate_golden.py [VECTOR_SET_DIR ...]

With no arguments it validates every committed vector set:
    vectors/fixed_seed          (same, 13x17)
    vectors/fixed_seed_valid    (valid, 13x17)
    vectors/cosim_33x29         (same, 33x29)
    vectors/cosim_33x29_valid   (valid, 33x29)
    vectors/naive_15x13         (same, 15x13)
"""

# =============================================================================
# 独立性禁令 (INDEPENDENCE CONTRACT — DO NOT VIOLATE)
# -----------------------------------------------------------------------------
# 1. 本脚本禁止 import / 调用 / 执行任何 C++ 侧代码（srcnn_golden 库、srcnn_run、
#    srcnn_vector_gen），也禁止把 C++ 侧产生的计算产物当作 oracle。它只能读取
#    vectors/ 下的 .tensor 数据文件作为输入与待比较对象。
# 2. 禁止为了让本脚本通过而修改 oracle 逻辑。若 oracle 与 dump 不一致，两边都要查：
#    要么 C++ 实现有 bug，要么本脚本的公式有 bug，要么 spec 本身需要修改。
#    绝不能把 oracle 改成"迁就"实现。
# 本脚本唯一的价值就是独立性；违反上面任何一条，它就退化为一个昂贵的恒真断言。
# =============================================================================

import argparse
import math
import os
import struct
import sys

FNV_OFFSET = 14695981039346656037
FNV_PRIME = 1099511628211
FNV_MASK = 0xFFFFFFFFFFFFFFFF

# Frozen SRCNN structure from spec.md section 3.2: cross-correlation, OIHW
# weights, stride 1 everywhere. "same" pads conv1/conv2/conv3 by 4/0/2; "valid"
# pads 0/0/0. Each entry: (in_channels, out_channels, kh, kw, stride, relu).
LAYERS = [
    (1, 64, 9, 9, 1, True),
    (64, 32, 1, 1, 1, True),
    (32, 1, 5, 5, 1, False),
]
PADS = {"same": [4, 0, 2], "valid": [0, 0, 0]}


# =============================================================================
# 容差集 (tolerance sets) — 两套, 各回答不同问题, 永不共用同一组常量
# -----------------------------------------------------------------------------
# 比较 A 和比较 B 的误差模型完全不同, 混用同一组冻结常量是 spec 的设计缺陷。
# 前者检验"实现是否符合语义"(差异=累加顺序噪声), 后者检验"定点实现是否逼近
# golden"(差异=量化误差, 由 ap_fixed 位宽决定, 数量级大得多, 且应以 PSNR 和
# 逐层误差分布为主体判据, 而不是 raw abs error)。
# =============================================================================

# --- A. Golden vs independent oracle: 两边都是 binary32, 合法差异只有累加顺序噪声。
#     容差 = 该层实测噪声底噪 (noise floor) 的约 10 倍。
#
# 噪声底噪是逐层结构性决定的, 不是全局一个数。n 项 binary32 乘积和的误差约
# n * eps * |terms|, eps ≈ 1.19e-7 (2^-23), 随累加深度和动态范围增长:
#
#   layer  累加项数  实测 max_abs (三套向量交叉确认)    atol ≈ 10×底噪
#   conv1    81       2.24e-6                           2e-5
#   conv2    64       7.84e-6 (输入已带 conv1 误差)     1e-4
#   conv3   800       ~2.3e-4 (800 项, |out| 达 ~342)   2e-3
#
# rtol=1e-4 三层都不动: 它远高于 float32 相对精度 (~1.2e-7), 作为相对界本就合适;
# 需要随层缩放的是 atol。spec 5.3 将 atol/rtol 标为"建议初始门禁", 并明确"若累加
# 顺序导致合理差异则必须基于证据调整" —— 下表就是那次基于证据的调整。全局单一
# atol 是 bug 的根源: 1e-5 只有 conv3 底噪的 ~0.04 倍 (在 |ref| 小的区域形同虚设),
# 而 1e-3 又是 conv1 底噪的 ~450 倍 (conv1 里一个 1e-4 量级的真 bug 会被静默放过)。
TOL_ORACLE_FP32 = {
    1: (2e-5, 1e-4),   # conv1
    2: (1e-4, 1e-4),   # conv2
    3: (2e-3, 1e-4),   # conv3
}

# --- B. HLS/板上 (定点) 输出 vs golden (P2/P3)。占位, 定点通路落地时填。
#     判据主体是 PSNR + 逐层误差分布, 不是 raw abs error; 位宽一经选择, 这组
#     容差就随之确定。现在把结构立起来, 是为了 P2 一开工不必再动比对代码。
TOL_IMPL_VS_GOLDEN = {
    # placeholder — populated when the fixed-point path lands
}


def f32(x):
    """Round a Python float to the nearest IEEE-754 binary32 value."""
    return struct.unpack("f", struct.pack("f", x))[0]


def fnv1a64(values_f32):
    """FNV-1a 64-bit over each float's binary32 bytes, LSB first (matches C++)."""
    h = FNV_OFFSET
    for v in values_f32:
        for byte in struct.pack("f", v):  # little-endian -> LSB first
            h ^= byte
            h = (h * FNV_PRIME) & FNV_MASK
    return format(h, "016x")


def parse_tensor(path):
    """Parse an SRCNN_TENSOR_V1 file -> (name, layout, shape, data).

    Values are rounded to binary32 so the reference operates on the exact
    float32 numbers the C++ code produced/consumed. The FNV-1a checksum is
    recomputed and asserted, which both proves the file is intact and proves
    this parser recovers the float32 values bit-exactly.
    """
    toks = open(path, "r", encoding="utf-8").read().split()
    assert toks and toks[0] == "SRCNN_TENSOR_V1", (path, toks[:1])

    name = layout = None
    ndim = 0
    shape = []
    count = 0
    declared_checksum = None

    i = 1
    while toks[i] != "data":
        k = toks[i]
        if k == "name":
            name, i = toks[i + 1], i + 2
        elif k == "dtype":
            assert toks[i + 1] == "float32", (path, toks[i + 1])
            i += 2
        elif k == "layout":
            layout, i = toks[i + 1], i + 2
        elif k == "ndim":
            ndim, i = int(toks[i + 1]), i + 2
        elif k == "shape":
            shape = [int(x) for x in toks[i + 1:i + 1 + ndim]]
            i += 1 + ndim
        elif k == "count":
            count, i = int(toks[i + 1]), i + 2
        elif k == "checksum_fnv1a64":
            declared_checksum, i = toks[i + 1], i + 2
        else:
            raise ValueError("unexpected key %r in %s" % (k, path))
    i += 1  # step past 'data'

    data = [f32(float(t)) for t in toks[i:i + count]]
    assert len(data) == count, (path, len(data), count)
    assert count == math.prod(shape), (path, count, shape)

    actual_checksum = fnv1a64(data)
    assert actual_checksum == declared_checksum, (
        "checksum mismatch in %s: header %s vs computed %s"
        % (path, declared_checksum, actual_checksum))
    return name, layout, shape, data


def read_vector_set_meta(root):
    """Return (padding_mode, seed) from manifest.txt."""
    meta = {}
    for line in open(os.path.join(root, "manifest.txt"), encoding="utf-8"):
        parts = line.split()
        if len(parts) == 2:
            meta[parts[0]] = parts[1]
    padding = meta.get("padding")
    assert padding in PADS, ("unknown padding mode %r in %s" % (padding, root))
    return padding, meta.get("seed")


def record_noise_floor(root, noise_floors):
    """Append the measured per-layer accumulation-noise floor (max_abs) to the
    vector set's manifest.txt. Idempotent: strips any prior noise_floor_* lines
    before writing, so re-running the oracle after a toolchain change re-measures
    the value in place rather than stacking stale lines. The floor is a measured
    property of the set (C++ vs this independent reference), so the oracle — not
    srcnn_vector_gen, which is the DUT itself — is the only side that can record
    it.
    """
    path = os.path.join(root, "manifest.txt")
    lines = open(path, encoding="utf-8").read().splitlines()
    kept = [ln for ln in lines if not ln.startswith("noise_floor_")]
    for idx in sorted(noise_floors):
        kept.append("noise_floor_conv%d %.6e" % (idx, noise_floors[idx]))
    open(path, "w", encoding="utf-8").write("\n".join(kept) + "\n")


def cross_correlation(x, w, b, stride, pad, relu):
    """Independent conv2d (cross-correlation, zero padding).

    x: nested list (C, H, W)   w: nested list (O, I, KH, KW)   b: flat (O,)
    Returns (out (O, OH, OW), (OH, OW), pre_activation sums flattened (O, OH, OW)).
    """
    C, H, W = len(x), len(x[0]), len(x[0][0])
    O, I, KH, KW = len(w), len(w[0]), len(w[0][0]), len(w[0][0][0])
    assert I == C, (I, C)
    OH = (H + 2 * pad - KH) // stride + 1
    OW = (W + 2 * pad - KW) // stride + 1

    out = [[[0.0] * OW for _ in range(OH)] for _ in range(O)]
    pre = []
    for o in range(O):
        bo = b[o]
        for oh in range(OH):
            for ow in range(OW):
                s = bo
                for i in range(I):
                    xi = x[i]
                    for kh in range(KH):
                        ih = oh * stride + kh - pad
                        if ih < 0 or ih >= H:
                            continue
                        row = xi[ih]
                        for kw in range(KW):
                            iw = ow * stride + kw - pad
                            if iw < 0 or iw >= W:
                                continue
                            s += w[o][i][kh][kw] * row[iw]
                pre.append(s)
                out[o][oh][ow] = max(0.0, s) if relu else s
    return out, (OH, OW), pre


def flat(mat):
    return [v for ch in mat for row in ch for v in row]


def coords(idx, shape):
    C, H, W = shape
    c = idx // (H * W)
    rem = idx % (H * W)
    return c, rem // W, rem % W


def coord_histogram(coords_list, shape):
    """Compact row/column count histogram of violation coordinates.

    A real bug in the padding/edge handling concentrates violations at the
    border; accumulation noise does not. Printing per-row and per-column counts
    (not just the single worst element) exposes that clustering, and becomes far
    more valuable in the fixed-point phase where violations number in the
    hundreds.
    """
    if not coords_list:
        return "(none)"
    _, OH, OW = shape
    rows = [0] * OH
    cols = [0] * OW
    for (c, h, w) in coords_list:
        rows[h] += 1
        cols[w] += 1

    def runs(counter):
        return " ".join("%d:%d" % (i, v) for i, v in enumerate(counter) if v)

    return "rows[%s] cols[%s]" % (runs(rows), runs(cols))


def pct_abs(values, p):
    a = sorted(abs(v) for v in values)
    k = max(0, int(round(p * (len(a) - 1))))
    return a[k]


def compare_layer(tag, ref, dut, shape, atol, rtol):
    """Per-element comparison. Returns a dict of diagnostics."""
    n = len(ref)
    assert len(dut) == n, (tag, len(dut), n)

    max_abs = 0.0
    max_rel = 0.0
    regular_viol = 0
    flip_viol = 0
    zero_flip_total = 0
    worst_regular = None   # (err, idx)
    worst_flip = None      # (err, idx)
    worst_abs_idx = -1
    viol_coords = []       # (c,h,w) of regular violations
    flip_coords = []       # (c,h,w) of zero-flip violations

    for idx, (r, d) in enumerate(zip(ref, dut)):
        e = abs(d - r)
        if e > max_abs:
            max_abs = e
            worst_abs_idx = idx
        if r != 0.0:
            max_rel = max(max_rel, e / abs(r))

        tol = atol + rtol * abs(r)
        violated = e > tol

        if r == 0.0 and d != 0.0:
            zero_flip_total += 1
            if violated:
                flip_viol += 1
                flip_coords.append(coords(idx, shape))
                if worst_flip is None or e > worst_flip[0]:
                    worst_flip = (e, idx)
        elif d == 0.0 and r != 0.0:
            zero_flip_total += 1
            if violated:
                flip_viol += 1
                flip_coords.append(coords(idx, shape))
                if worst_flip is None or e > worst_flip[0]:
                    worst_flip = (e, idx)
        elif violated:
            regular_viol += 1
            viol_coords.append(coords(idx, shape))
            if worst_regular is None or e > worst_regular[0]:
                worst_regular = (e, idx)

    # Which branch of the gate does the worst-absolute-error element pass/fail
    # through? (Diagnostic for the "atol vs rtol" question.)
    r_worst = ref[worst_abs_idx]
    d_worst = dut[worst_abs_idx]
    e_worst = max_abs
    tol_worst = atol + rtol * abs(r_worst)
    branch = ("atol" if e_worst <= atol
              else "rtol" if e_worst <= rtol * abs(r_worst)
              else "FAIL")

    return {
        "tag": tag, "n": n, "shape": shape,
        "max_abs": max_abs, "max_rel": max_rel,
        "regular_viol": regular_viol, "flip_viol": flip_viol,
        "zero_flip_total": zero_flip_total,
        "viol_coords": viol_coords, "flip_coords": flip_coords,
        "worst_regular": (worst_regular, coords(worst_regular[1], shape))
                         if worst_regular else None,
        "worst_flip": (worst_flip, coords(worst_flip[1], shape))
                       if worst_flip else None,
        "worst_abs": (e_worst, r_worst, d_worst, tol_worst, branch,
                      coords(worst_abs_idx, shape)),
        "violations": regular_viol + flip_viol,
    }


def run_vector_set(root):
    padding, seed = read_vector_set_meta(root)
    model_dir = os.path.join(root, "model")
    dumps_dir = os.path.join(root, "dumps")

    _, _, x_shape, x_flat = parse_tensor(os.path.join(dumps_dir, "input.tensor"))
    C, H, W = x_shape
    x = [[[x_flat[(c * H + h) * W + w] for w in range(W)]
          for h in range(H)] for c in range(C)]

    print("=== %s  (padding=%s, seed=%s) ===" % (root, padding, seed))
    print("input CHW = %d x %d x %d" % (C, H, W))

    pads = PADS[padding]
    ok = True
    noise_floors = {}
    y = x
    for li, (cin, cout, kh, kw, stride, relu) in enumerate(LAYERS, start=1):
        pad = pads[li - 1]
        atol, rtol = TOL_ORACLE_FP32[li]

        wname, _, w_shape, w_flat = parse_tensor(
            os.path.join(model_dir, "conv%d_weights.tensor" % li))
        bname, _, b_shape, b_flat = parse_tensor(
            os.path.join(model_dir, "conv%d_bias.tensor" % li))
        assert w_shape == [cout, cin, kh, kw], (wname, w_shape)
        assert b_shape == [cout], (bname, b_shape)

        O, I, KH, KW = w_shape
        w = [[[[w_flat[(((o * I + i) * KH + kh) * KW + kw)]
                for kw in range(KW)] for kh in range(KH)]
              for i in range(I)] for o in range(O)]

        y, (OH, OW), pre = cross_correlation(y, w, b_flat, stride, pad, relu)

        gname, _, g_shape, g_flat = parse_tensor(
            os.path.join(dumps_dir, "conv%d.tensor" % li))
        assert g_shape == [O, OH, OW], (gname, g_shape, (O, OH, OW))

        dut = flat(y)
        diag = compare_layer("conv%d" % li, g_flat, dut, g_shape, atol, rtol)
        noise_floors[li] = diag["max_abs"]

        out_mn = min(dut); out_mx = max(dut)
        out_amax = max(abs(v) for v in dut)
        out_p999 = pct_abs(dut, 0.999)
        pre_mn = min(pre); pre_mx = max(pre)
        pre_amax = max(abs(v) for v in pre)

        print("  %-6s shape %-14s n=%-6d (atol=%.1e rtol=%.1e)"
              % (diag["tag"], str(g_shape), diag["n"], atol, rtol))
        print("        output  min=%.5e max=%.5e abs_max=%.5e "
              "p99.9|.|=%.5e (p99.9/abs_max=%.3f)"
              % (out_mn, out_mx, out_amax, out_p999,
                 out_p999 / out_amax if out_amax else 1.0))
        print("        pre-act min=%.5e max=%.5e abs_max=%.5e"
              % (pre_mn, pre_mx, pre_amax))
        print("        max_abs=%.3e  max_rel(|ref|>0)=%.3e"
              % (diag["max_abs"], diag["max_rel"]))
        print("        violations=%d (regular=%d, zero-boundary-flip=%d)  "
              "zero-flips[any]=%d"
              % (diag["violations"], diag["regular_viol"],
                 diag["flip_viol"], diag["zero_flip_total"]))
        if diag["worst_regular"]:
            (err, idx), (c, h, w) = diag["worst_regular"]
            print("        worst regular at (c,h,w)=(%d,%d,%d) err=%.3e"
                  % (c, h, w, err))
        if diag["worst_flip"]:
            (err, idx), (c, h, w) = diag["worst_flip"]
            print("        worst zero-flip at (c,h,w)=(%d,%d,%d) err=%.3e"
                  % (c, h, w, err))
        if diag["regular_viol"]:
            print("        regular-viol coords  %s"
                  % coord_histogram(diag["viol_coords"], g_shape))
        if diag["flip_viol"]:
            print("        flip-viol coords     %s"
                  % coord_histogram(diag["flip_coords"], g_shape))
        e_w, r_w, d_w, tol_w, branch, (c, h, w) = diag["worst_abs"]
        print("        worst-abs elem (c,h,w)=(%d,%d,%d): |dut-ref|=%.3e "
              "gate=%.3e -> %s" % (c, h, w, e_w, tol_w, branch))
        passed = diag["violations"] == 0
        ok = ok and passed
        print("        -> %s" % ("PASS" if passed else "FAIL"))

    record_noise_floor(root, noise_floors)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="*",
                    help="vector-set directories (default: all committed sets)")
    args = ap.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_dirs = [
        os.path.join(script_dir, "..", "vectors", "fixed_seed"),
        os.path.join(script_dir, "..", "vectors", "fixed_seed_valid"),
        os.path.join(script_dir, "..", "vectors", "cosim_33x29"),
        os.path.join(script_dir, "..", "vectors", "cosim_33x29_valid"),
        os.path.join(script_dir, "..", "vectors", "naive_15x13"),
    ]
    dirs = [os.path.abspath(d) for d in args.dirs] or default_dirs

    all_ok = True
    for d in dirs:
        all_ok = run_vector_set(d) and all_ok

    print("\nOVERALL: %s" % ("PASS — all dumps agree with the independent "
                             "reference" if all_ok else
                             "FAIL — see per-layer violations above"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
