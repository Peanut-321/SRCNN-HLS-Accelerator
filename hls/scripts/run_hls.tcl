# P2.1 synthesis/export entry point. The exact part and clock are deliberately
# supplied by P0a; this file contains no optimization or interface directives.
if {![info exists ::env(SRCNN_HLS_PART)] || $::env(SRCNN_HLS_PART) eq ""} {
    error "SRCNN_HLS_PART is required"
}
if {![info exists ::env(SRCNN_HLS_CLOCK_NS)] ||
    $::env(SRCNN_HLS_CLOCK_NS) eq ""} {
    error "SRCNN_HLS_CLOCK_NS is required"
}
if {![info exists ::env(SRCNN_HLS_TOP)] || $::env(SRCNN_HLS_TOP) eq ""} {
    set selected_top "srcnn_hls_top"
} else {
    set selected_top $::env(SRCNN_HLS_TOP)
}
if {$selected_top ne "srcnn_hls_top" &&
    $selected_top ne "srcnn_hls_line_buffer_top"} {
    error "SRCNN_HLS_TOP must be srcnn_hls_top or srcnn_hls_line_buffer_top"
}

set script_dir [file dirname [file normalize [info script]]]
set project_dir [file normalize [file join $script_dir ../..]]
set natural_source [file join $project_dir hls/src/srcnn_hls.cpp]
set line_buffer_source [file join $project_dir hls/src/srcnn_hls_line_buffer.cpp]
set include_dir [file join $project_dir hls/include]
set compile_flags "-std=c++14 -I$include_dir -DSRCNN_HLS_FIXED_POINT=1"

open_project -reset [file join $project_dir build-vitis $selected_top]
set_top $selected_top
add_files -cflags $compile_flags $natural_source
if {$selected_top eq "srcnn_hls_line_buffer_top"} {
    add_files -cflags $compile_flags $line_buffer_source
}
open_solution -reset solution1
set_part $::env(SRCNN_HLS_PART)
create_clock -period $::env(SRCNN_HLS_CLOCK_NS) -name default
csynth_design
export_design -format ip_catalog
exit
