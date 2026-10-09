# Vivado 2026.1: KV260 PS + simple AXI DMA + fixed 255x255 SRCNN deployment IP.
# No HLS source edits. Refuses to replace an existing project in all/bd mode.
# Usage: vivado -mode batch -source run_srcnn_axis_vivado.tcl -tclargs PROJECT_DIR IP_DIR REPORT_DIR ?all|bd|implement? ?JOBS? ?RESTART_IMPL?
proc main {} {
    global argv
    if {[llength $argv] < 3} { error "Expected PROJECT_DIR IP_DIR REPORT_DIR" }
    set project_dir [file normalize [lindex $argv 0]]
    set ip_dir [file normalize [lindex $argv 1]]
    set report_dir [file normalize [lindex $argv 2]]
    set stage [expr {[llength $argv] > 3 ? [lindex $argv 3] : "all"}]
    set jobs [expr {[llength $argv] > 4 ? [lindex $argv 4] : 2}]
    set restart_impl [expr {[llength $argv] > 5 ? [lindex $argv 5] : 0}]
    if {$stage ni {all bd implement}} { error "Stage must be all, bd or implement" }
    if {$restart_impl && $stage ne "implement"} { error "RESTART_IMPL requires implement stage" }
    if {![file exists $ip_dir/component.xml]} { error "No exported HLS IP metadata" }
    file mkdir $report_dir
    set_param general.maxThreads 4
    set project_name srcnn_axis_kv260
    set xpr $project_dir/$project_name.xpr
    if {$stage ne "implement"} {
        if {[file exists $xpr]} { error "Existing project: choose a new directory or implement stage" }
        create_project $project_name $project_dir -part xck26-sfvc784-2LV-c
        set_property board_part xilinx.com:kv260_som:part0:2.0 [current_project]
        set_property board_connections {som240_1_connector xilinx.com:kv260_carrier:som240_1_connector:2.0} [current_project]
        set_property ip_repo_paths [list $ip_dir] [current_project]
        update_ip_catalog
        create_bd_design srcnn_system
        create_bd_cell -type ip -vlnv xilinx.com:ip:zynq_ultra_ps_e:* ps
        apply_bd_automation -rule xilinx.com:bd_rule:zynq_ultra_ps_e -config {apply_board_preset "1"} [get_bd_cells ps]
        set_property -dict [list \
            CONFIG.PSU__USE__M_AXI_GP0 1 CONFIG.PSU__USE__M_AXI_GP1 0 CONFIG.PSU__USE__M_AXI_GP2 0 \
            CONFIG.PSU__USE__S_AXI_GP2 1 CONFIG.PSU__SAXIGP2__DATA_WIDTH 64 \
            CONFIG.PSU__CRL_APB__PL0_REF_CTRL__SRCSEL RPLL \
            CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ 200 CONFIG.PSU__FPGA_PL1_ENABLE 0 \
            CONFIG.PSU__USE__IRQ0 1] [get_bd_cells ps]
        create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma:* dma
        set_property -dict [list CONFIG.c_include_sg 0 CONFIG.c_sg_length_width 26 \
            CONFIG.c_addr_width 64 CONFIG.c_m_axi_mm2s_data_width 64 CONFIG.c_m_axi_s2mm_data_width 64 \
            CONFIG.c_m_axis_mm2s_tdata_width 32 CONFIG.c_s_axis_s2mm_tdata_width 32 \
            CONFIG.c_include_mm2s_dre 1 CONFIG.c_include_s2mm_dre 1 \
            CONFIG.c_mm2s_burst_size 16 CONFIG.c_s2mm_burst_size 16] [get_bd_cells dma]
        create_bd_cell -type ip -vlnv xilinx.com:hls:srcnn_axis_dataflow_top:1.0 srcnn
        create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:* control_ic
        set_property -dict [list CONFIG.NUM_SI 1 CONFIG.NUM_MI 2] [get_bd_cells control_ic]
        create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:* memory_ic
        set_property -dict [list CONFIG.NUM_SI 3 CONFIG.NUM_MI 1] [get_bd_cells memory_ic]
        create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:* reset
        # Reset polarity and PS IRQ width propagate from the connected signals.
        create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:* zero
        set_property -dict [list CONFIG.CONST_WIDTH 1 CONFIG.CONST_VAL 0] [get_bd_cells zero]
        create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:* one
        set_property -dict [list CONFIG.CONST_WIDTH 1 CONFIG.CONST_VAL 1] [get_bd_cells one]
        create_bd_cell -type ip -vlnv xilinx.com:ip:xlconcat:* irq_concat
        set_property CONFIG.NUM_PORTS 3 [get_bd_cells irq_concat]

        connect_bd_intf_net [get_bd_intf_pins ps/M_AXI_HPM0_FPD] [get_bd_intf_pins control_ic/S00_AXI]
        connect_bd_intf_net [get_bd_intf_pins control_ic/M00_AXI] [get_bd_intf_pins dma/S_AXI_LITE]
        connect_bd_intf_net [get_bd_intf_pins control_ic/M01_AXI] [get_bd_intf_pins srcnn/s_axi_control]
        connect_bd_intf_net [get_bd_intf_pins dma/M_AXI_MM2S] [get_bd_intf_pins memory_ic/S00_AXI]
        connect_bd_intf_net [get_bd_intf_pins dma/M_AXI_S2MM] [get_bd_intf_pins memory_ic/S01_AXI]
        connect_bd_intf_net [get_bd_intf_pins srcnn/m_axi_model_mem] [get_bd_intf_pins memory_ic/S02_AXI]
        connect_bd_intf_net [get_bd_intf_pins memory_ic/M00_AXI] [get_bd_intf_pins ps/S_AXI_HP0_FPD]
        connect_bd_intf_net [get_bd_intf_pins dma/M_AXIS_MM2S] [get_bd_intf_pins srcnn/input_r]
        connect_bd_intf_net [get_bd_intf_pins srcnn/output_r] [get_bd_intf_pins dma/S_AXIS_S2MM]
        connect_bd_net [get_bd_pins ps/pl_clk0] \
            [get_bd_pins ps/maxihpm0_fpd_aclk] [get_bd_pins ps/saxihp0_fpd_aclk] \
            [get_bd_pins dma/s_axi_lite_aclk] [get_bd_pins dma/m_axi_mm2s_aclk] [get_bd_pins dma/m_axi_s2mm_aclk] \
            [get_bd_pins srcnn/ap_clk] [get_bd_pins control_ic/aclk] [get_bd_pins memory_ic/aclk] \
            [get_bd_pins reset/slowest_sync_clk]
        connect_bd_net [get_bd_pins ps/pl_resetn0] [get_bd_pins reset/ext_reset_in]
        connect_bd_net [get_bd_pins zero/dout] [get_bd_pins reset/aux_reset_in] [get_bd_pins reset/mb_debug_sys_rst]
        connect_bd_net [get_bd_pins one/dout] [get_bd_pins reset/dcm_locked]
        connect_bd_net [get_bd_pins reset/interconnect_aresetn] [get_bd_pins control_ic/aresetn] [get_bd_pins memory_ic/aresetn]
        connect_bd_net [get_bd_pins reset/peripheral_aresetn] [get_bd_pins srcnn/ap_rst_n] [get_bd_pins dma/axi_resetn]
        connect_bd_net [get_bd_pins dma/mm2s_introut] [get_bd_pins irq_concat/In0]
        connect_bd_net [get_bd_pins dma/s2mm_introut] [get_bd_pins irq_concat/In1]
        connect_bd_net [get_bd_pins srcnn/interrupt] [get_bd_pins irq_concat/In2]
        connect_bd_net [get_bd_pins irq_concat/dout] [get_bd_pins ps/pl_ps_irq0]
        assign_bd_address -offset 0xA0000000 -range 64K -target_address_space [get_bd_addr_spaces ps/Data] [get_bd_addr_segs dma/S_AXI_LITE/Reg]
        assign_bd_address -offset 0xA0010000 -range 64K -target_address_space [get_bd_addr_spaces ps/Data] [get_bd_addr_segs srcnn/s_axi_control/Reg]
        assign_bd_address
        validate_bd_design
        if {[get_property CONFIG.C_EXT_RESET_HIGH [get_bd_cells reset]] != 0} {
            error "Reset polarity did not propagate as active-low"
        }
        if {[get_property CONFIG.PSU__NUM_F2P0__INTR__INPUTS [get_bd_cells ps]] != 3} {
            error "PS interrupt width did not propagate as three inputs"
        }
        save_bd_design
        write_bd_tcl -force $report_dir/srcnn_system_bd.tcl
        set info [open $report_dir/integration_config.txt w]
        puts $info "Vivado [version -short]"
        puts $info "Part [get_property PART [current_project]]"
        puts $info "Board [get_property BOARD_PART [current_project]]"
        puts $info "PL0 requested MHz [get_property CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ [get_bd_cells ps]]"
        puts $info "PL0 actual MHz [get_property CONFIG.PSU__CRL_APB__PL0_REF_CTRL__ACT_FREQMHZ [get_bd_cells ps]]"
        puts $info "PL0 source [get_property CONFIG.PSU__CRL_APB__PL0_REF_CTRL__SRCSEL [get_bd_cells ps]]"
        puts $info "DDR enabled [get_property CONFIG.PSU__DDRC__ENABLE [get_bd_cells ps]]"
        puts $info "DMA length bits [get_property CONFIG.c_sg_length_width [get_bd_cells dma]]"
        foreach seg [get_bd_addr_segs -hier] {
            puts $info "ADDRESS $seg OFFSET=[get_property OFFSET $seg] RANGE=[get_property RANGE $seg]"
        }
        foreach c [get_bd_cells -hier] { puts $info "CELL $c [get_property VLNV $c]" }
        close $info
        set bd [get_files */srcnn_system.bd]
        generate_target all $bd
        set wrappers [make_wrapper -files $bd -top]
        add_files -norecurse $wrappers
        set_property top srcnn_system_wrapper [current_fileset]
        update_compile_order -fileset sources_1
        puts "GATE_BD_PASS"
        if {$stage eq "bd"} { return }
    } else {
        open_project $xpr
        if {$restart_impl} {
            puts "Explicitly restarting interrupted implementation; synthesis is retained."
            reset_run impl_1
        }
    }
    if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {
        launch_runs synth_1 -jobs $jobs
        wait_on_run synth_1
    }
    if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} { error "Synthesis failed: [get_property STATUS [get_runs synth_1]]" }
    open_run synth_1
    report_utilization -file $report_dir/post_synth_utilization.rpt
    report_timing_summary -report_unconstrained -file $report_dir/post_synth_timing.rpt
    close_design
    puts "GATE_SYNTH_PASS"
    if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {
        launch_runs impl_1 -to_step route_design -jobs $jobs
        wait_on_run impl_1
    }
    if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} { error "Implementation failed: [get_property STATUS [get_runs impl_1]]" }
    open_run impl_1
    report_utilization -file $report_dir/post_route_utilization.rpt
    report_utilization -hierarchical -file $report_dir/post_route_utilization_hierarchical.rpt
    report_timing_summary -delay_type min_max -report_unconstrained -max_paths 20 -file $report_dir/post_route_timing.rpt
    report_timing -delay_type max -max_paths 20 -file $report_dir/post_route_setup_paths.rpt
    report_timing -delay_type min -max_paths 20 -file $report_dir/post_route_hold_paths.rpt
    check_timing -verbose -file $report_dir/check_timing.rpt
    report_clocks -file $report_dir/clocks.rpt
    report_drc -file $report_dir/post_route_drc.rpt
    report_methodology -file $report_dir/post_route_methodology.rpt
    write_checkpoint -force $project_dir/srcnn_system_routed.dcp
    set wns [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
    set whs [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
    set gate [open $report_dir/implementation_gate.txt w]
    puts $gate "WNS $wns"
    puts $gate "WHS $whs"
    puts $gate "IMPL_STATUS [get_property STATUS [get_runs impl_1]]"
    set blockers 0
    foreach v [get_drc_violations -quiet] {
        set severity [get_property SEVERITY $v]
        puts $gate "DRC $severity [get_property NAME $v]"
        if {[regexp -nocase {error|critical} $severity]} { incr blockers }
    }
    puts $gate "DRC_BLOCKERS $blockers"
    close $gate
    if {$wns eq "" || $whs eq "" || $wns < 0 || $whs < 0 || $blockers > 0} {
        error "Routed timing/DRC gate failed; bitstream not generated. WNS=$wns WHS=$whs blockers=$blockers"
    }
    puts "GATE_ROUTE_PASS WNS=$wns WHS=$whs"
    # Use the managed run so write_hw_platform can locate its bitstream.
    close_design
    if {[get_property STATUS [get_runs impl_1]] ne "write_bitstream Complete!"} {
        launch_runs impl_1 -to_step write_bitstream -jobs $jobs
        wait_on_run impl_1
    }
    if {[get_property STATUS [get_runs impl_1]] ne "write_bitstream Complete!"} {
        error "Bitstream run failed: [get_property STATUS [get_runs impl_1]]"
    }
    set run_dir [get_property DIRECTORY [get_runs impl_1]]
    file copy -force $run_dir/srcnn_system_wrapper.bit $report_dir/srcnn_axis_255x255.bit
    set hwh $project_dir/${project_name}.gen/sources_1/bd/srcnn_system/hw_handoff/srcnn_system.hwh
    if {![file exists $hwh]} { error "Missing hardware handoff: $hwh" }
    file copy -force $hwh $report_dir/srcnn_axis_255x255.hwh
    write_hw_platform -fixed -include_bit -force -file $report_dir/srcnn_axis_255x255.xsa
    puts "GATE_BITSTREAM_PASS"
}
if {[catch {main} problem options]} {
    puts stderr "SRCNN_VIVADO_FAILED: $problem"
    puts stderr [dict get $options -errorinfo]
    exit 1
}
exit 0
