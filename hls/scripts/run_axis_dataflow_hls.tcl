# AXIS/DATAFLOW SRCNN C simulation, synthesis, and IP export.
if {![info exists ::env(SRCNN_HLS_PART)] || $::env(SRCNN_HLS_PART) eq ""} {
    error "SRCNN_HLS_PART is required"
}
if {![info exists ::env(SRCNN_HLS_CLOCK_NS)] ||
    $::env(SRCNN_HLS_CLOCK_NS) eq ""} {
    error "SRCNN_HLS_CLOCK_NS is required"
}

set script_dir [file dirname [file normalize [info script]]]
set project_dir [file normalize [file join $script_dir ../..]]
set include_dir [file join $project_dir hls/include]
set compile_flags "-std=c++14 -I$include_dir -DSRCNN_HLS_FIXED_POINT=1"
set cosim_test_case 0
if {[info exists ::env(SRCNN_AXIS_DATAFLOW_TEST_CASE)] &&
    $::env(SRCNN_AXIS_DATAFLOW_TEST_CASE) ne ""} {
    set cosim_test_case $::env(SRCNN_AXIS_DATAFLOW_TEST_CASE)
}
if {![string is integer -strict $cosim_test_case] ||
    $cosim_test_case < 0 || $cosim_test_case > 5} {
    error "SRCNN_AXIS_DATAFLOW_TEST_CASE must be an integer in 0..5"
}
set tb_compile_flags \
    "$compile_flags -DSRCNN_AXIS_DATAFLOW_TEST_CASE=$cosim_test_case"

open_project -reset [file join $project_dir build-vitis srcnn_axis_dataflow_top]
set_top srcnn_axis_dataflow_cosim_top
add_files -cflags $compile_flags \
    [file join $project_dir hls/src/srcnn_axis_dataflow.cpp]
add_files -cflags $compile_flags \
    [file join $project_dir hls/src/srcnn_hls.cpp]
add_files -cflags $compile_flags \
    [file join $project_dir hls/src/srcnn_hls_line_buffer.cpp]
add_files -tb -cflags $tb_compile_flags \
    [file join $project_dir tests/test_srcnn_axis_dataflow.cpp]

open_solution -reset cosim_small
set_part $::env(SRCNN_HLS_PART)
create_clock -period $::env(SRCNN_HLS_CLOCK_NS) -name default
csim_design
csynth_design
cosim_design

close_solution
set_top srcnn_axis_dataflow_top
open_solution -reset deployment_255x255
set_part $::env(SRCNN_HLS_PART)
create_clock -period $::env(SRCNN_HLS_CLOCK_NS) -name default
csynth_design
export_design -format ip_catalog
exit
