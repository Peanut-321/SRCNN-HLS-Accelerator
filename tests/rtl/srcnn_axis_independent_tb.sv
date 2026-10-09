`timescale 1ns/1ps
// Independent AXI agents. No Vitis UVM/autotb code or forced DUT signals.
`ifdef FIXED_13X17
`define SRCNN_DUT srcnn_axis_dataflow_cosim_13x17_top
`define CONTROL_ADDR_BITS 5
`else
`define SRCNN_DUT srcnn_axis_dataflow_cosim_top
`define CONTROL_ADDR_BITS 6
`endif
module srcnn_axis_independent_tb;
  localparam integer PIXELS=221, MODEL_WORDS=8129, TIMEOUT_CYCLES=6000000;
  localparam [63:0] MODEL_BASE=64'h10000000;
  reg ap_clk=0;
  always #2.5 ap_clk=~ap_clk;
  reg ap_rst_n=0;
  reg [31:0] model_words[0:MODEL_WORDS-1], input_words[0:PIXELS-1], expected_words[0:PIXELS-1];
  reg model_seen[0:MODEL_WORDS-1];
  integer cycle=0, input_count=0, output_count=0, model_reads=0, unique_model_reads=0, ar_count=0;
  integer start_cycle=-1, done_cycle=-1, rtl_done_cycle=-1, output_stall_cycles=0;
  reg started=0, completed=0;
  reg [`CONTROL_ADDR_BITS-1:0] awaddr=0, araddr=0;
  reg awvalid=0, wvalid=0, arvalid=0;
  reg [31:0] wdata=0;
  wire awready,wready,bvalid,arready,rvalid;
  wire [1:0] bresp,rresp;
  wire [31:0] rdata;
  reg [31:0] input_data=0;
  reg input_valid=0,input_last=0;
  wire input_ready;
  wire [31:0] output_data;
  wire [3:0] output_keep,output_strb;
  wire output_valid,output_last;
  reg output_ready=0;
  always @(negedge ap_clk) output_ready=ap_rst_n && ((cycle%17)!=0);
  wire mem_arvalid,mem_rready,mem_awvalid,mem_wvalid;
  wire [63:0] mem_araddr;
  wire [63:0] unused_mem_awaddr;
  wire [7:0] mem_arlen;
  wire [2:0] mem_arsize;
  wire [1:0] mem_arburst;
  wire [0:0] mem_arid;
  reg mem_active=0;
  integer mem_index=0,beats_left=0;
  reg [0:0] mem_rid=0;
  wire mem_arready=ap_rst_n && !mem_active;
  wire [31:0] mem_rdata=mem_active ? model_words[mem_index] : 32'b0;
  `SRCNN_DUT dut (
    .ap_clk(ap_clk),.ap_rst_n(ap_rst_n),
    .s_axi_control_AWADDR(awaddr),.s_axi_control_AWVALID(awvalid),.s_axi_control_AWREADY(awready),
    .s_axi_control_WDATA(wdata),.s_axi_control_WSTRB(4'hf),.s_axi_control_WVALID(wvalid),.s_axi_control_WREADY(wready),
    .s_axi_control_BVALID(bvalid),.s_axi_control_BREADY(1'b1),.s_axi_control_BRESP(bresp),
    .s_axi_control_ARADDR(araddr),.s_axi_control_ARVALID(arvalid),.s_axi_control_ARREADY(arready),
    .s_axi_control_RDATA(rdata),.s_axi_control_RVALID(rvalid),.s_axi_control_RREADY(1'b1),.s_axi_control_RRESP(rresp),
    .input_r_TDATA(input_data),.input_r_TVALID(input_valid),.input_r_TREADY(input_ready),
    .input_r_TKEEP(4'hf),.input_r_TSTRB(4'hf),.input_r_TLAST(input_last),
    .output_r_TDATA(output_data),.output_r_TVALID(output_valid),.output_r_TREADY(output_ready),
    .output_r_TKEEP(output_keep),.output_r_TSTRB(output_strb),.output_r_TLAST(output_last),
    .m_axi_model_mem_ARVALID(mem_arvalid),.m_axi_model_mem_ARREADY(mem_arready),
    .m_axi_model_mem_ARADDR(mem_araddr),.m_axi_model_mem_ARLEN(mem_arlen),
    .m_axi_model_mem_ARSIZE(mem_arsize),.m_axi_model_mem_ARBURST(mem_arburst),.m_axi_model_mem_ARID(mem_arid),
    .m_axi_model_mem_RVALID(mem_active),.m_axi_model_mem_RREADY(mem_rready),.m_axi_model_mem_RDATA(mem_rdata),
    .m_axi_model_mem_RLAST(mem_active && beats_left==1),.m_axi_model_mem_RRESP(2'b00),
    .m_axi_model_mem_RID(mem_rid),.m_axi_model_mem_RUSER(1'b0),
    .m_axi_model_mem_AWVALID(mem_awvalid),.m_axi_model_mem_AWADDR(unused_mem_awaddr),.m_axi_model_mem_AWREADY(1'b0),
    .m_axi_model_mem_WVALID(mem_wvalid),.m_axi_model_mem_WREADY(1'b0),
    .m_axi_model_mem_BVALID(1'b0),.m_axi_model_mem_BRESP(2'b00),
    .m_axi_model_mem_BID(1'b0),.m_axi_model_mem_BUSER(1'b0)
  );
  // Single outstanding INCR burst. RVALID/data/last hold until RREADY.
  always @(posedge ap_clk) begin
    if(!ap_rst_n) begin mem_active<=0;mem_index<=0;beats_left<=0;end
    else begin
      if(mem_awvalid!==0 || mem_wvalid!==0) $fatal(1,"Unexpected model write/unknown write control");
      if($isunknown({mem_arvalid,mem_rready})) $fatal(1,"Unknown model read control cycle=%0d",cycle);
      if(mem_arvalid && mem_arready) begin
        if($isunknown({mem_araddr,mem_arlen,mem_arsize,mem_arburst,mem_arid}) ||
           mem_arsize!=2 || mem_arburst!=1 || mem_araddr[1:0]!=0 || mem_araddr<MODEL_BASE ||
           ((mem_araddr-MODEL_BASE)/4+mem_arlen)>=MODEL_WORDS)
          $fatal(1,"Invalid model AR address=%h len=%d size=%d burst=%d",mem_araddr,mem_arlen,mem_arsize,mem_arburst);
        mem_index<=(mem_araddr-MODEL_BASE)/4;beats_left<=mem_arlen+1;mem_rid<=mem_arid;mem_active<=1;
        ar_count=ar_count+1;
        if(ar_count==1) $display("EVENT first_model_AR cycle=%0d time=%0t",cycle,$time);
      end
      if(mem_active && mem_rready) begin
        model_reads=model_reads+1;
        if(!model_seen[mem_index]) begin model_seen[mem_index]=1;unique_model_reads=unique_model_reads+1;end
        if(beats_left==1) mem_active<=0;
        else begin beats_left<=beats_left-1;mem_index<=mem_index+1;end
        if(unique_model_reads==MODEL_WORDS && model_reads==MODEL_WORDS)
          $display("EVENT model_loaded cycle=%0d time=%0t",cycle,$time);
      end
    end
  end
  reg output_stalled=0;
  reg [40:0] held_output;
  always @(posedge ap_clk) begin
    cycle=cycle+1;
    if(cycle>TIMEOUT_CYCLES)
      $fatal(1,"Timeout in=%0d out=%0d model=%0d unique=%0d start=%b done=%b idle=%b",input_count,output_count,model_reads,unique_model_reads,dut.ap_start,dut.ap_done,dut.ap_idle);
    if(ap_rst_n) begin
      if($isunknown({awready,wready,bvalid,arready,rvalid,input_ready,output_valid,dut.ap_start,dut.ap_done,dut.ap_idle,dut.ap_ready}))
        $fatal(1,"Unknown DUT control cycle=%0d",cycle);
      if(started && start_cycle<0 && dut.ap_start && !dut.ap_idle) begin
        start_cycle=cycle;$display("EVENT start_accepted cycle=%0d time=%0t",cycle,$time);
      end
      if(started && rtl_done_cycle<0 && dut.ap_done) begin
        rtl_done_cycle=cycle;
        $display("EVENT rtl_ap_done cycle=%0d time=%0t",cycle,$time);
      end
      if(input_valid && input_ready) begin
        if(input_count>=PIXELS) $fatal(1,"Extra input accepted");
        if(input_count==0) $display("EVENT first_input cycle=%0d time=%0t",cycle,$time);
        input_count=input_count+1;
      end
      if(output_stalled && (output_valid!==1 || {output_data,output_keep,output_strb,output_last}!==held_output))
        $fatal(1,"AXIS output changed under backpressure");
      output_stalled=output_valid && !output_ready;
      if(output_stalled) output_stall_cycles=output_stall_cycles+1;
      held_output={output_data,output_keep,output_strb,output_last};
      if(output_valid && output_ready) begin
        if(output_count>=PIXELS) $fatal(1,"Extra output");
        if(output_data!==expected_words[output_count]) $fatal(1,"Output %0d expected=%h actual=%h",output_count,expected_words[output_count],output_data);
        if(output_keep!==4'hf || output_strb!==4'hf || output_last!==(output_count==PIXELS-1))
          $fatal(1,"Invalid output sideband index=%0d",output_count);
        if(output_count==0) $display("EVENT first_output cycle=%0d time=%0t",cycle,$time);
        output_count=output_count+1;
      end
      if(cycle%500000==0) $display("PROGRESS cycle=%0d in=%0d out=%0d model=%0d",cycle,input_count,output_count,model_reads);
    end
  end
  task automatic axi_write(input [5:0] address,input [31:0] value);
    begin
      @(negedge ap_clk);awaddr=address;awvalid=1;
      do @(posedge ap_clk);while(awready!==1);
      @(negedge ap_clk);awvalid=0;wdata=value;wvalid=1;
      do @(posedge ap_clk);while(wready!==1);
      @(negedge ap_clk);wvalid=0;
      do @(posedge ap_clk);while(bvalid!==1);
      if(bresp!==0) $fatal(1,"AXI-Lite B response %b",bresp);
      $display("EVENT control_write addr=%h data=%h cycle=%0d",address,value,cycle);
      @(negedge ap_clk);
    end
  endtask
  task automatic axi_read(input [5:0] address,output [31:0] value);
    begin
      @(negedge ap_clk);araddr=address;arvalid=1;
      do @(posedge ap_clk);while(arready!==1);
      @(negedge ap_clk);arvalid=0;
      do @(posedge ap_clk);while(rvalid!==1);
      if(rresp!==0 || $isunknown(rdata)) $fatal(1,"Invalid AXI-Lite R response");
      value=rdata;@(negedge ap_clk);
    end
  endtask
  task automatic send_frame;
    integer i;
    begin
      for(i=0;i<PIXELS;i=i+1) begin
        @(negedge ap_clk);input_valid=1;input_data=input_words[i];input_last=(i==PIXELS-1);
        do @(posedge ap_clk);while(input_ready!==1);
        @(negedge ap_clk);input_valid=0;
      end
    end
  endtask
  integer i;
  reg [31:0] status;
  initial begin
    $readmemh("model.hex",model_words);$readmemh("input.hex",input_words);$readmemh("expected.hex",expected_words);
    for(i=0;i<MODEL_WORDS;i=i+1) begin
      model_seen[i]=0;if($isunknown(model_words[i])) $fatal(1,"Missing model word %0d",i);
    end
    for(i=0;i<PIXELS;i=i+1) if($isunknown(input_words[i]) || $isunknown(expected_words[i])) $fatal(1,"Missing input/golden word %0d",i);
    repeat(20) @(negedge ap_clk);ap_rst_n=1;$display("EVENT reset_released time=%0t",$time);
    repeat(4) @(negedge ap_clk);
    axi_write(6'h10,MODEL_BASE[31:0]);axi_write(6'h14,MODEL_BASE[63:32]);
`ifndef FIXED_13X17
    axi_write(6'h1c,13);axi_write(6'h24,17);
`endif
    started=1;axi_write(6'h00,1);
    fork
      send_frame();
      begin
        status=0;
        while(!status[1]) begin repeat(1000) @(negedge ap_clk);axi_read(0,status);end
        done_cycle=cycle;completed=1;$display("EVENT ap_done cycle=%0d time=%0t",cycle,$time);
      end
    join
    repeat(20) @(negedge ap_clk);
    if(!completed || start_cycle<0 || rtl_done_cycle<0 || input_count!=PIXELS || output_count!=PIXELS ||
       model_reads!=MODEL_WORDS || unique_model_reads!=MODEL_WORDS || mem_active || output_stall_cycles==0)
      $fatal(1,"Incomplete start=%0d in=%0d out=%0d model=%0d unique=%0d",start_cycle,input_count,output_count,model_reads,unique_model_reads);
    $display("PASS independent RTL: transactions=1 inputs=%0d outputs=%0d model_reads=%0d unique=%0d AR_bursts=%0d cycles=%0d start_to_rtl_done=%0d polled_done_cycle=%0d output_stall_cycles=%0d time=%0t",input_count,output_count,model_reads,unique_model_reads,ar_count,cycle,rtl_done_cycle-start_cycle,done_cycle,output_stall_cycles,$time);
    $finish;
  end
endmodule
