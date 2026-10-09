# P0c KV260/PYNQ dummy-overlay procedure

Status: board-pending. This procedure must only be marked PASS after running
on a physical KV260.

## Files to copy to the board

From the Windows P0b delivery bundle, copy these files to one directory on the
board, for example `/home/xilinx/axis_dummy/`:

```text
axis_dummy_overlay.bit
axis_dummy_overlay.hwh
axis_dummy_p0c.py
```

The `.bit` and `.hwh` names must have the same stem. The `.hwh` lets PYNQ
discover `axi_dma_0` and `axis_dummy_top_0`.

## One-shot correctness test

On the board, run:

```bash
python3 axis_dummy_p0c.py --bit axis_dummy_overlay.bit
```

This checks lengths 1, 5, 257, and 65,025 32-bit words. Each transfer checks
the complete result against `input + 1`, including a `0xFFFFFFFF` input word
to exercise uint32 wraparound.

The script explicitly flushes source buffers and invalidates destination
buffers around DMA. It starts S2MM before starting the HLS kernel and MM2S.

## Required stability test

After the one-shot run passes:

```bash
python3 axis_dummy_p0c.py --bit axis_dummy_overlay.bit --iterations 100 --reloads 3
```

This performs 100 full suites after each of three overlay downloads. It writes
`axis_dummy_p0c_log.json`; retain that log as the P0c board evidence.

## Scope boundary

This script validates the dummy deployment chain only. It does not test SRCNN,
does not measure formal SRCNN performance, and does not establish a board-level
claim until the commands have run successfully on the KV260.
