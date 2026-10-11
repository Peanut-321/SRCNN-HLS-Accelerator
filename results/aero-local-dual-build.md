# Final Aero dual-format deployment — V3 resetfix

Both final deliveries were built and physically validated on 2026-10-11.
Canonical archives: `deliverables/aero-local/`; physical evidence:
`results/srcnn-board/`. Original/V2 packages are retired, not valid alternatives.
Failure diagnosis remains in `aero-reset-audit.md`.

| Format | Frozen source commit | WNS ns | WHS ns | Blocking DRC |
|---|---|---:|---:|---:|
| Q24.8 | 5f0216704cdd7ba70e2c8a493469c2df97e32259 | 0.105 | 0.010 | 0 |
| Q20.12 | 18281e76b9070b6801620a8548c7ae8b72f47db5 | 0.109 | 0.011 | 0 |

Both Vivado processes exited 0 and passed `GATE_BITSTREAM_PASS`, timing
constraint coverage and BIT/HWH/XSA consistency gates. Nonblocking advisory
warnings remain. Requested PL0 is 200 MHz; runtime reports 199.998 MHz, a
register-derived value rather than independent waveform measurement.

## Artifact identity

Q24.8 BIT: `7bb51e96b6288c8fd72e895228c978c78a26110306a0c5f5ca0660383d1c1cc9`

Q24.8 HWH: `4a2d76dde8e3e651a5cfb6ed811545f682c520a79a32a0ac7488357afb437579`

Q20.12 BIT: `24914ab05e129866847a9903dbd4fff5942b27f1d0da1b4aea28dc5776f96725`

Q20.12 HWH: `2049f2a5bc5d5c4272e3de540a7ffe5611307bac7b9b5da65ac99d60b675ce77`

Build Tcl: `tools/run_aero_hpm1_vivado.tcl`; packager:
`tools/package_aero_delivery.py`. Active-low auxiliary reset is tied HIGH;
DCM locked HIGH and debug reset LOW. Generated HWH checks control/DDR routing.
XSA is under build_reports, not a runtime BIT sibling. Mutable notebooks are
excluded from immutable hashes; Python, bitstreams and bundles stay protected.
Reports/provenance are inside each ZIP. Projects:
`C:/fpga/aero-q248-resetfix-vivado`, `C:/fpga/aero-q2012-resetfix-vivado`;
export roots use `resetfix-delivery`. Vivado/Vitis 2026.1.
Frozen HLS arithmetic is unchanged.

## Physical results

Each format passed warmup + 10 repeats + changed input/model + restored
original + overlay reload. All 14 downloaded arrays were independently compared
with the corresponding fixed-point Golden: all 65,025 words per frame match.
Source and hardware hashes match the final manifests. Recomputed median/P95
statistics are in `docs/aero-team-progress.md`. This is not a substitute for
float-error/quality studies or CPU same-boundary speedup.
