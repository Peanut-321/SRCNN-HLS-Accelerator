#!/usr/bin/env python3
"""Board-pending P0c validation for the AXI-stream dummy overlay.

Run this on the KV260 PYNQ image only.  It validates the independent dummy
kernel, not the SRCNN accelerator: each uint32 output word must equal its
input word plus one modulo 2**32.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Iterable

import numpy as np
from pynq import Overlay, allocate


CONTROL_OFFSET = 0x00
LENGTH_OFFSET = 0x10
DMA_NAME = "axi_dma_0"
KERNEL_NAME = "axis_dummy_top_0"
DEFAULT_LENGTHS = (1, 5, 257, 65025)


def require_hwh(bit_path: Path) -> None:
    """Fail early if PYNQ cannot discover the hardware hierarchy."""
    hwh_path = bit_path.with_suffix(".hwh")
    if not hwh_path.is_file():
        raise FileNotFoundError(
            f"Missing handoff file {hwh_path}. Copy the matching .bit and .hwh "
            "from the P0b delivery bundle to the same board directory."
        )


def deterministic_input(length: int, iteration: int) -> np.ndarray:
    """Create a repeatable uint32 payload and exercise arithmetic wraparound."""
    values = np.arange(length, dtype=np.uint32)
    values ^= np.uint32(0xA5A50000 | (iteration & 0xFFFF))
    if length:
        values[0] = np.uint32(0xFFFFFFFF)
    return values


def flush(buffer) -> None:
    """Explicitly flush cached PS writes before MM2S reads them."""
    if hasattr(buffer, "flush"):
        buffer.flush()


def invalidate(buffer) -> None:
    """Explicitly invalidate cached PS reads after S2MM writes them."""
    if hasattr(buffer, "invalidate"):
        buffer.invalidate()


def get_ip(overlay: Overlay, name: str):
    try:
        return getattr(overlay, name)
    except AttributeError as error:
        available = ", ".join(sorted(overlay.ip_dict))
        raise RuntimeError(
            f"Overlay does not expose {name!r}. Available IP: {available}"
        ) from error


def run_one(overlay: Overlay, length: int, iteration: int) -> dict:
    if length <= 0:
        raise ValueError("DMA P0c tests require a positive length")

    dma = get_ip(overlay, DMA_NAME)
    kernel = get_ip(overlay, KERNEL_NAME)
    source = deterministic_input(length, iteration)
    expected = source + np.uint32(1)
    input_buffer = allocate(shape=(length,), dtype=np.uint32)
    output_buffer = allocate(shape=(length,), dtype=np.uint32)

    try:
        input_buffer[:] = source
        output_buffer.fill(0)
        flush(input_buffer)
        flush(output_buffer)

        # Arm the receive channel before data may leave the kernel, configure
        # the AXI-Lite length register, and then release ap_ctrl_hs.
        dma.recvchannel.transfer(output_buffer)
        kernel.write(LENGTH_OFFSET, length)
        kernel.write(CONTROL_OFFSET, 0x01)
        dma.sendchannel.transfer(input_buffer)
        dma.sendchannel.wait()
        dma.recvchannel.wait()
        invalidate(output_buffer)

        actual = np.asarray(output_buffer, dtype=np.uint32).copy()
        mismatch = np.flatnonzero(actual != expected)
        if mismatch.size:
            index = int(mismatch[0])
            raise AssertionError(
                "dummy result mismatch at index "
                f"{index}: got 0x{int(actual[index]):08X}, "
                f"expected 0x{int(expected[index]):08X}"
            )
        return {"length": length, "iteration": iteration, "status": "PASS"}
    finally:
        input_buffer.freebuffer()
        output_buffer.freebuffer()


def load_overlay(bit_path: Path) -> Overlay:
    require_hwh(bit_path)
    return Overlay(str(bit_path), download=True)


def run_suite(bit_path: Path, lengths: Iterable[int], iterations: int,
              reloads: int) -> list[dict]:
    if iterations < 1 or reloads < 1:
        raise ValueError("iterations and reloads must both be positive")

    results: list[dict] = []
    lengths = tuple(lengths)
    for reload_index in range(reloads):
        overlay = load_overlay(bit_path)
        for iteration in range(iterations):
            for length in lengths:
                result = run_one(overlay, length, iteration)
                result["overlay_reload"] = reload_index
                results.append(result)
                print(
                    "PASS "
                    f"reload={reload_index} iteration={iteration} length={length}"
                )
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bit",
        type=Path,
        default=Path("axis_dummy_overlay.bit"),
        help="Path to the P0b .bit file; matching .hwh must be adjacent.",
    )
    parser.add_argument(
        "--lengths",
        type=int,
        nargs="+",
        default=DEFAULT_LENGTHS,
        help="Positive uint32-word counts to test.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=1,
        help="Number of complete test suites per overlay load.",
    )
    parser.add_argument(
        "--reloads",
        type=int,
        default=1,
        help="Number of overlay reloads to test.",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=Path("axis_dummy_p0c_log.json"),
        help="JSON result log path on the board.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    bit_path = args.bit.expanduser().resolve()
    if not bit_path.is_file():
        raise FileNotFoundError(f"Overlay bitstream not found: {bit_path}")
    if any(length <= 0 for length in args.lengths):
        raise ValueError("all --lengths entries must be positive")

    start = time.perf_counter()
    results = run_suite(bit_path, args.lengths, args.iterations, args.reloads)
    payload = {
        "status": "PASS",
        "bitstream": str(bit_path),
        "lengths": list(args.lengths),
        "iterations": args.iterations,
        "reloads": args.reloads,
        "elapsed_seconds": time.perf_counter() - start,
        "results": results,
    }
    args.log.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote PASS log to {args.log}")


if __name__ == "__main__":
    main()
