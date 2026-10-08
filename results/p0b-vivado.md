# P0b Vivado 2026.1 implementation result

Date: 2026-10-09  
Part: `xck26-sfvc784-2LV-c`  
Top: `design_1_wrapper`

## Tool versions

```text
Vivado v2026.1 (64-bit), SW Build 6511674
Vitis/vitis-run v2026.1, SW Build 6497934
```

## Flow status

```text
Block Design validation: PASS (no errors or critical warnings)
Output products:         PASS
HDL wrapper:             PASS
Synthesis:               PASS
Implementation:          PASS
Bitstream:               PASS
```

## Routed timing

```text
Clock: clk_pl_0
WNS:   +1.479 ns
TNS:   0.000 ns
WHS:   +0.011 ns
THS:   0.000 ns
Result: all user specified timing constraints are met
```

The implemented PL clock is 187.498 MHz. This is below the 200 MHz (5.0 ns)
HLS target, therefore it does not invalidate the HLS timing gate.

## Utilization

| Resource | Used | Available | Utilization |
|---|---:|---:|---:|
| LUT as logic | 3,373 | 117,120 | 2.88% |
| LUT as memory | 661 | 57,600 | 1.15% |
| BRAM tile | 2 | 144 | 1.39% |
| DSP | 0 | 1,248 | 0.00% |

## DRC

The routed DRC has no errors. It reports two `REQP-1935`
`RAMB36E2_nochange_collision_advisory` warnings inside the AXI DMA MM2S/S2MM
internal FIFO BRAMs. These are implementation advisories, not blocking DRCs.

Raw reports are retained in `results/p0b-vivado/`.
