`timescale 1ns/1ps
module aero_reset_tb;
  reg clk = 0;
  always #2.5 clk = ~clk;
  reg ext_n = 0;
  wire [0:0] bad_ic, bad_per, good_ic, good_per;
  srcnn_system_reset_0 bad(.slowest_sync_clk(clk), .ext_reset_in(ext_n),
    .aux_reset_in(1'b0), .mb_debug_sys_rst(1'b0), .dcm_locked(1'b1),
    .interconnect_aresetn(bad_ic), .peripheral_aresetn(bad_per));
  srcnn_system_reset_0 good(.slowest_sync_clk(clk), .ext_reset_in(ext_n),
    .aux_reset_in(1'b1), .mb_debug_sys_rst(1'b0), .dcm_locked(1'b1),
    .interconnect_aresetn(good_ic), .peripheral_aresetn(good_per));
  initial begin
    repeat (40) @(negedge clk);
    ext_n = 1;
    repeat (200) @(negedge clk);
    if (bad_ic !== 1'b0 || bad_per !== 1'b0)
      $fatal(1, "Bad auxiliary tie-off did not hold reset");
    if (good_ic !== 1'b1 || good_per !== 1'b1)
      $fatal(1, "Correct auxiliary tie-off did not release reset");
    $display("RESET_TIEOFF_PASS: aux=0 holds AXI reset; aux=1 releases AXI reset");
    $finish;
  end
endmodule
