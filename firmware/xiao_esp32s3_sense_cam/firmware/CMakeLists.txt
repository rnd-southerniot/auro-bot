cmake_minimum_required(VERSION 3.16)

# ESP-IDF top-level project file.
include($ENV{IDF_PATH}/tools/cmake/project.cmake)

# Add include/ to every component's search path so gpio_remap.h /
# system_config.h are visible without per-component plumbing.
idf_build_set_property(COMPILE_OPTIONS "-I${CMAKE_CURRENT_SOURCE_DIR}/include" APPEND)

project(xiao_esp32s3_sense)
