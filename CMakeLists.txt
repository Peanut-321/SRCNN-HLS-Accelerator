cmake_minimum_required(VERSION 3.16)
project(srcnn_golden LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Lock IEEE-754 semantics: forbid FMA contraction so the golden reference's
# binary32 results are bit-reproducible across compilers/platforms. This is the
# dominant source of cross-platform last-bit differences for pure MAC arithmetic
# (no transcendentals, no libm), so this one flag closes most of the gap.
add_compile_options(-ffp-contract=off)

# Reject non-IEEE "fast math" flags: they silently change the golden reference's
# numerics far more than FMA contraction does, and are easy to sneak in via
# CMAKE_CXX_FLAGS or an -Ofast build. Fail loudly at configure time instead.
foreach(_flag_var CMAKE_CXX_FLAGS CMAKE_CXX_FLAGS_RELEASE
                 CMAKE_CXX_FLAGS_RELWITHDEBINFO CMAKE_CXX_FLAGS_DEBUG)
    foreach(_bad -ffast-math -Ofast -funsafe-math-optimizations)
        string(FIND "${${_flag_var}}" "${_bad}" _pos)
        if(NOT _pos EQUAL -1)
            message(FATAL_ERROR
                "${_flag_var} contains forbidden '${_bad}' (non-IEEE): "
                "the golden reference requires strict IEEE-754")
        endif()
    endforeach()
endforeach()

# Toolchain fingerprint, embedded into every generated vector manifest so a
# teammate on another platform can immediately compare toolchains when a
# last-bit difference appears. Fields: compiler id+version, target arch,
# optimization level, FMA-contraction setting.
if(CMAKE_BUILD_TYPE STREQUAL "Release")
    set(SRCNN_OPT_LEVEL "O3")
elseif(CMAKE_BUILD_TYPE STREQUAL "RelWithDebInfo")
    set(SRCNN_OPT_LEVEL "O2")
elseif(CMAKE_BUILD_TYPE STREQUAL "Debug")
    set(SRCNN_OPT_LEVEL "O0")
else()
    set(SRCNN_OPT_LEVEL "unknown")
endif()

add_compile_definitions(
    SRCNN_COMPILER_ID="${CMAKE_CXX_COMPILER_ID}"
    SRCNN_COMPILER_VERSION="${CMAKE_CXX_COMPILER_VERSION}"
    SRCNN_TARGET_ARCH="${CMAKE_SYSTEM_PROCESSOR}"
    SRCNN_OPT_LEVEL="${SRCNN_OPT_LEVEL}"
    SRCNN_FP_CONTRACT="off"
)

add_library(srcnn_golden
    src/tensor_io.cpp
    src/srcnn.cpp
)
target_include_directories(srcnn_golden PUBLIC include)
target_compile_options(srcnn_golden PRIVATE -Wall -Wextra -Wpedantic)

add_executable(srcnn_run tools/srcnn_run.cpp)
target_link_libraries(srcnn_run PRIVATE srcnn_golden)

add_executable(srcnn_vector_gen tools/srcnn_vector_gen.cpp)
target_link_libraries(srcnn_vector_gen PRIVATE srcnn_golden)

enable_testing()
add_executable(srcnn_tests tests/test_srcnn.cpp)
target_link_libraries(srcnn_tests PRIVATE srcnn_golden)
target_compile_definitions(srcnn_tests PRIVATE
    SRCNN_VECTOR_GEN_PATH="$<TARGET_FILE:srcnn_vector_gen>")
add_test(NAME srcnn_tests COMMAND srcnn_tests)
set_tests_properties(srcnn_tests PROPERTIES LABELS "unit")

# P2.1 dual-target skeleton. The float target is always available and is kept
# separate from srcnn_golden so the frozen P1 implementation remains untouched.
function(add_srcnn_hls_library target_name fixed_point_mode)
    add_library(${target_name} STATIC hls/src/srcnn_hls.cpp)
    set_target_properties(${target_name} PROPERTIES
                          CXX_STANDARD 14
                          CXX_STANDARD_REQUIRED ON
                          CXX_EXTENSIONS OFF)
    target_include_directories(${target_name} PUBLIC hls/include)
    target_compile_definitions(${target_name}
                               PUBLIC SRCNN_HLS_FIXED_POINT=${fixed_point_mode})
    target_compile_options(${target_name} PRIVATE
                           -Wall -Wextra -Wpedantic -Wno-unknown-pragmas)
endfunction()

add_srcnn_hls_library(srcnn_hls_float 0)
add_executable(srcnn_hls_float_vectors tests/test_hls_float_vectors.cpp)
target_link_libraries(srcnn_hls_float_vectors PRIVATE
                      srcnn_hls_float srcnn_golden)
target_compile_definitions(srcnn_hls_float_vectors PRIVATE
                           SRCNN_PROJECT_ROOT="${CMAKE_SOURCE_DIR}")
add_test(NAME srcnn_hls_float_vectors COMMAND srcnn_hls_float_vectors)
set_tests_properties(srcnn_hls_float_vectors PROPERTIES
                     LABELS "p2_1;float_bitwise"
                     TIMEOUT 120)

add_executable(srcnn_hls_padding_modes tests/test_hls_padding_modes.cpp)
target_link_libraries(srcnn_hls_padding_modes PRIVATE srcnn_hls_float)
add_test(NAME srcnn_hls_padding_modes COMMAND srcnn_hls_padding_modes)
set_tests_properties(srcnn_hls_padding_modes PROPERTIES
                     LABELS "p2_2a;padding"
                     TIMEOUT 120)

# Mac/Linux fixed-point simulation uses Xilinx's open-source simulation-only
# AP types at an explicit path or a pinned commit. Vitis synthesis must instead
# use the vendor ap_fixed.h shipped with the selected Vitis version.
option(SRCNN_BUILD_HLS_FIXED_SIM
       "Build the P2.1 host ap_fixed instantiation/smoke test" OFF)
set(SRCNN_AP_TYPES_INCLUDE_DIR "" CACHE PATH
    "Directory containing the open-source ap_fixed.h for host simulation")
if(SRCNN_BUILD_HLS_FIXED_SIM)
    set(_srcnn_ap_include "${SRCNN_AP_TYPES_INCLUDE_DIR}")
    set(_srcnn_bundled_ap_include
        "${CMAKE_SOURCE_DIR}/third_party/HLS_arbitrary_Precision_Types/include")
    if(NOT _srcnn_ap_include AND
       EXISTS "${_srcnn_bundled_ap_include}/ap_fixed.h")
        set(_srcnn_ap_include "${_srcnn_bundled_ap_include}")
        message(STATUS
            "Using bundled Xilinx arbitrary-precision headers: "
            "${_srcnn_ap_include}")
    endif()
    if(NOT _srcnn_ap_include)
        include(FetchContent)
        FetchContent_Declare(
            xilinx_ap_types
            GIT_REPOSITORY https://github.com/Xilinx/HLS_arbitrary_Precision_Types.git
            GIT_TAG 200a9aecaadf471592558540dc5a88256cbf880f)
        FetchContent_MakeAvailable(xilinx_ap_types)
        FetchContent_GetProperties(xilinx_ap_types SOURCE_DIR _srcnn_ap_source)
        set(_srcnn_ap_include "${_srcnn_ap_source}/include")
    endif()
    if(NOT EXISTS "${_srcnn_ap_include}/ap_fixed.h")
        message(FATAL_ERROR
            "SRCNN_AP_TYPES_INCLUDE_DIR must contain ap_fixed.h; got "
            "'${_srcnn_ap_include}'")
    endif()

    add_srcnn_hls_library(srcnn_hls_fixed 1)
    target_include_directories(srcnn_hls_fixed SYSTEM PUBLIC
                               "${_srcnn_ap_include}")
    add_executable(srcnn_hls_fixed_smoke tests/test_hls_fixed_smoke.cpp)
    target_link_libraries(srcnn_hls_fixed_smoke PRIVATE srcnn_hls_fixed)
    add_test(NAME srcnn_hls_fixed_smoke COMMAND srcnn_hls_fixed_smoke)
    set_tests_properties(srcnn_hls_fixed_smoke PROPERTIES
                         LABELS "p2_1;fixed"
                         TIMEOUT 120)

    add_executable(srcnn_hls_fixed_vectors tests/test_hls_fixed_vectors.cpp)
    target_link_libraries(srcnn_hls_fixed_vectors PRIVATE
                          srcnn_hls_fixed srcnn_golden)
    target_compile_definitions(srcnn_hls_fixed_vectors PRIVATE
                               SRCNN_PROJECT_ROOT="${CMAKE_SOURCE_DIR}")
    add_test(NAME srcnn_hls_fixed_vectors COMMAND srcnn_hls_fixed_vectors)
    set_tests_properties(srcnn_hls_fixed_vectors PROPERTIES
                         LABELS "p2_2a;fixed"
                         TIMEOUT 120)
endif()

# Independent cross-validation oracle (pure-Python, stdlib only).
#
# CTest has no "registered but excluded from the default run, yet runnable by
# label" flag: labels only *filter*, they do not gate. To keep the daily
# `ctest` fast and unit-only while still exposing the oracle via `ctest -L
# oracle`, its registration is opt-in at configure time:
#
#     cmake -DSRCNN_ENABLE_ORACLE_TESTS=ON build
#     ctest -L oracle          # cross-validation (same + valid padding)
#     ctest -L unit            # unit tests only
#
# The oracle runs every committed vector set — the 13x17 fixed-seed pair plus the
# 33x29 cosim pair and the 15x13 naive micro vector — so nothing is gated on only
# the vectors that happen to pass. It stays fast (a few seconds): pure Python on
# modest tensors, largest layer ~61k elements.
option(SRCNN_ENABLE_ORACLE_TESTS
       "Register the independent cross-validation oracle as a CTest test" OFF)
if(SRCNN_ENABLE_ORACLE_TESTS)
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
    add_test(NAME srcnn_oracle
             COMMAND ${Python3_EXECUTABLE}
                     ${CMAKE_SOURCE_DIR}/tools/cross_validate_golden.py
                     ${CMAKE_SOURCE_DIR}/vectors/fixed_seed
                     ${CMAKE_SOURCE_DIR}/vectors/fixed_seed_valid
                     ${CMAKE_SOURCE_DIR}/vectors/cosim_33x29
                     ${CMAKE_SOURCE_DIR}/vectors/cosim_33x29_valid
                     ${CMAKE_SOURCE_DIR}/vectors/naive_15x13)
    set_tests_properties(srcnn_oracle PROPERTIES
                         LABELS "oracle"
                         TIMEOUT 120)
endif()
