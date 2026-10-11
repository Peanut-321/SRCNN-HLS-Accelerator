# Reset wiring audit - 2026-10-11

Historical V2 board attempts did not establish PASS. V2 is retired.

Confirmed design defect in both Q24.8 and Q20.12 v2 HPM1/HPC0
handoffs: `reset/C_AUX_RESET_HIGH=0`, while `aux_reset_in` is driven
by `zero/dout`. Generated top-level HDL confirms this constant connection.
This permanently asserts the auxiliary reset and prevents release of the
interconnect and peripheral reset outputs. This is a deployment integration
error, not a demonstrated numerical-core error or demonstrated broken board.

Actual Vivado XSim simulation of the generated `srcnn_system_reset_0`
functional netlist compares the bad constant-low auxiliary input with the
correct constant-high input. Both use the same clock, external reset pulse,
DCM locked high and debug reset low. After 200 clocks with external reset
released, bad interconnect/peripheral ARESETN remain 0; corrected outputs
are both 1. Result: `RESET_TIEOFF_PASS`. Testbench: `tests/aero_reset_tb.v`.
Simulation evidence is at `C:/fpga/aero-reset-audit/xsim.log`.

The board screenshot stops inside MMIO construction, before the explicit
status read. The reset defect explains an unresponsive AXI fabric, but the
precise OS-level blocking operation and any additional board-state issues
are not proven. Do not call the screenshot a successful inference test.

Build Tcl now explicitly sets both reset input polarities to active-low and
ties the unused auxiliary input HIGH. Packaging and offline board inspection
now check actual constant-driver wiring and reject both existing v2 builds.
Existing bitstreams are unchanged and must NOT be reused for physical tests.
Corrected hardware must be regenerated and validated before another upload.

## V3 rebuild completed

Both fresh projects `C:/fpga/aero-q248-resetfix-vivado` and
`C:/fpga/aero-q2012-resetfix-vivado` completed with Vivado exit 0 and
`GATE_BITSTREAM_PASS`. Generated HDL connects `aux_reset_in(one_dout)`;
generated HWH passes the active-low inactive-HIGH tie-off gate.
Q24.8 final WNS/WHS: 0.105/0.010 ns. Q20.12: 0.109/0.011 ns.
Both have zero blocking DRC findings and pass timing constraint coverage.
Nonblocking advisory warnings remain. BIT/HWH match the XSA contents.
This supersedes the earlier statement that corrected hardware is not yet
regenerated. Both V3 formats subsequently passed physical-board testing;
downloaded evidence is stored under `results/srcnn-board/`.

Regression suite: 17 `test_aero*.py` offline tests PASS, including rejection
of both actual v2 HWH files and positive/negative reset tie-off tests.
Offline tests are separate from physical evidence. Final V3 ZIPs are in
`deliverables/aero-local/`. Each format's 14 physical output arrays were
independently checked against its fixed-point Golden; all words match.
