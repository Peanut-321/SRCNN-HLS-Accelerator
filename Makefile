PROJECT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
AP_TYPES_INCLUDE_DIR ?= $(PROJECT_DIR)/third_party/HLS_arbitrary_Precision_Types/include
AP_TYPES_CMAKE_ARG := $(if $(strip $(AP_TYPES_INCLUDE_DIR)),-DSRCNN_AP_TYPES_INCLUDE_DIR=$(abspath $(AP_TYPES_INCLUDE_DIR)),)
VITIS_HLS ?= vitis_hls
SRCNN_HLS_TOP ?= srcnn_hls_top

.PHONY: host-float host-fixed host-axis-dummy vitis-export \
	vitis-axis-dummy-export

host-float:
	cmake -S $(PROJECT_DIR) -B $(PROJECT_DIR)/build-p2-float \
		-DCMAKE_BUILD_TYPE=Release -DSRCNN_ENABLE_ORACLE_TESTS=OFF
	cmake --build $(PROJECT_DIR)/build-p2-float --parallel
	ctest --test-dir $(PROJECT_DIR)/build-p2-float -L unit --output-on-failure
	ctest --test-dir $(PROJECT_DIR)/build-p2-float -L float_bitwise --output-on-failure

host-fixed:
	cmake -S $(PROJECT_DIR) -B $(PROJECT_DIR)/build-p2-fixed \
		-DCMAKE_BUILD_TYPE=Release -DSRCNN_ENABLE_ORACLE_TESTS=OFF \
		-DSRCNN_BUILD_HLS_FIXED_SIM=ON $(AP_TYPES_CMAKE_ARG)
	cmake --build $(PROJECT_DIR)/build-p2-fixed --parallel
	ctest --test-dir $(PROJECT_DIR)/build-p2-fixed -L fixed --output-on-failure

host-axis-dummy:
	cmake -S $(PROJECT_DIR) -B $(PROJECT_DIR)/build-p0-axis-dummy \
		-DCMAKE_BUILD_TYPE=Release -DSRCNN_ENABLE_ORACLE_TESTS=OFF
	cmake --build $(PROJECT_DIR)/build-p0-axis-dummy --parallel \
		--target srcnn_axis_dummy_test
	ctest --test-dir $(PROJECT_DIR)/build-p0-axis-dummy \
		-L axis_dummy --output-on-failure

# Example:
# Natural baseline:
# make vitis-export SRCNN_HLS_PART=<exact-part-from-P0a> SRCNN_HLS_CLOCK_NS=5.0
# Line-buffer checkpoint: add SRCNN_HLS_TOP=srcnn_hls_line_buffer_top
# MAC-A replicate specialization:
# SRCNN_HLS_TOP=srcnn_hls_line_buffer_replicate_top
# Conv1 two-output-channel throughput experiment:
# SRCNN_HLS_TOP=srcnn_hls_line_buffer_replicate_oc2_top
# Conv1 four-output-channel throughput experiment:
# SRCNN_HLS_TOP=srcnn_hls_line_buffer_replicate_oc4_top
vitis-export:
	@test -n "$(SRCNN_HLS_PART)" || \
		(echo "SRCNN_HLS_PART is required (use the exact P0a part)"; exit 2)
	@test -n "$(SRCNN_HLS_CLOCK_NS)" || \
		(echo "SRCNN_HLS_CLOCK_NS is required (use the confirmed P0a target)"; exit 2)
	SRCNN_HLS_PART="$(SRCNN_HLS_PART)" \
	SRCNN_HLS_CLOCK_NS="$(SRCNN_HLS_CLOCK_NS)" \
	SRCNN_HLS_TOP="$(SRCNN_HLS_TOP)" \
		$(VITIS_HLS) -f $(PROJECT_DIR)/hls/scripts/run_hls.tcl

vitis-axis-dummy-export:
	@test -n "$(SRCNN_HLS_PART)" || \
		(echo "SRCNN_HLS_PART is required (use the exact P0a part)"; exit 2)
	@test -n "$(SRCNN_HLS_CLOCK_NS)" || \
		(echo "SRCNN_HLS_CLOCK_NS is required (use the confirmed P0a target)"; exit 2)
	SRCNN_HLS_PART="$(SRCNN_HLS_PART)" \
	SRCNN_HLS_CLOCK_NS="$(SRCNN_HLS_CLOCK_NS)" \
		$(VITIS_HLS) -f $(PROJECT_DIR)/hls/scripts/run_axis_dummy_hls.tcl
