# P0a AXI4-Stream toolchain probe. This component is intentionally independent
# of the SRCNN compute core so export/BD/DMA failures cannot be misdiagnosed as
# convolution failures.
if {![info exists ::env(SRCNN_HLS_PART)] || $::env(SRCNN_HLS_PART) eq ""} {
    error "SRCNN_HLS_PART is required"
}
if {![info exists ::env(SRCNN_HLS_CLOCK_NS)] ||
    $::env(SRCNN_HLS_CLOCK_NS) eq ""} {
    error "SRCNN_HLS_CLOCK_NS is required"
}

set script_dir [file dirname [file normalize [info script]]]
set project_dir [file normalize [file join $script_dir ../..]]
set dummy_dir [file join $project_dir hls/dummy]
set source_file [file join $dummy_dir axis_dummy.cpp]
set testbench_file [file join $dummy_dir test_axis_dummy.cpp]
set compile_flags "-std=c++14 -I$dummy_dir"

open_project -reset [file join $project_dir build-vitis axis_dummy_top]
set_top axis_dummy_top
add_files -cflags $compile_flags $source_file
add_files -tb -cflags $compile_flags $testbench_file
open_solution -reset solution1
set_part $::env(SRCNN_HLS_PART)
create_clock -period $::env(SRCNN_HLS_CLOCK_NS) -name default
csim_design
csynth_design
export_design -format ip_catalog
exit
