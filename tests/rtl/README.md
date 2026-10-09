# Independent SRCNN RTL verification

`srcnn_axis_independent_tb.sv` drives existing synthesized RTL directly. It
does not use Vitis autotb/UVM, force signals, change FIFO depths, or synthesize
the design again. The frame is 13x17; the clock is 5 ns.

Run from PowerShell after generating the 13x17 mode-3 C vectors and synthesizing
the desired top:

```powershell
& .\hls\scripts\run_axis_independent_rtl.ps1 `
  -Component C:\fpga\vitis-workspace\srcnn_axis_dataflow_cosim_case3_dynamic_porttrace_5ns `
  -WorkDir C:\fpga\independent-rtl\dynamic

& .\hls\scripts\run_axis_independent_rtl.ps1 `
  -Component C:\fpga\vitis-workspace\srcnn_axis_dataflow_cosim_13x17_porttrace_5ns `
  -VectorComponent C:\fpga\vitis-workspace\srcnn_axis_dataflow_cosim_case3_dynamic_porttrace_5ns `
  -WorkDir C:\fpga\independent-rtl\fixed -Fixed13x17
```

Use a separate work directory for each top/run. The script reads only
`hls/syn/verilog` and `hls/sim/tv/cdatafile` from the component(s); all copied
RTL, converted vectors, XSIM files, manifest and logs go to `WorkDir`. Override
`-VivadoRoot` if Vivado is installed elsewhere. The vector reader validates
one transaction, frame depth, sidebands and the model binary header/trailer.
It supports the Vitis 2026.1 binary model-vector format verified by this project.
The golden vector comes from the existing C testbench, which checks equality
against the frozen OC4 implementation before generating co-sim vectors.

PASS requires:

- Successful AXI-Lite model pointer/start writes (also height/width for the dynamic top).
- 8,129 model reads with coverage of all 8,129 addresses; 32-bit aligned INCR bursts.
- Exactly 221 accepted inputs and outputs; every output word matches golden bit for bit.
- TKEEP/TSTRB 0xF; only the final output has TLAST.
- Observed output backpressure and stable output while stalled.
- Defined DUT controls after reset, a real DUT `ap_done`, and AXI-Lite done readback.
- Completion within six million clock cycles.

`start_to_rtl_done` counts from the first sampled DUT `ap_start`/non-idle
condition to the first sampled DUT `ap_done`. `polled_done_cycle` is the later
software-style AXI-Lite status readback and must not be reported as DUT latency.
One transaction is exercised per run. This small-frame functional simulation
does not verify routed timing, the 255x255 deployment top, or board behavior.

To prove the scoreboard rejects wrong output, repeat the dynamic command in a
separate directory with `-RejectCorruptGolden`. It must stop at output 0 with
an explicit mismatch; the script reports a successful negative check only for
that failure. Ordinary runs never change the expected output.

Only the verification sources and results Markdown belong in Git. Keep
converted vectors, copied RTL, WDBs, manifests and logs outside the repository.
