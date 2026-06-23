cmake_minimum_required(VERSION 3.13)

set(PICO_BOARD pico)

include(pico_sdk_import.cmake)

project(makerpi_rp2040_base C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

add_executable(firmware
    src/main.c
    src/pid.c
    src/wheel.c
    src/safety.c
    src/serial_parser.c
    src/telemetry.c
    src/counter_drive.c
)

pico_generate_pio_header(firmware ${CMAKE_CURRENT_LIST_DIR}/pio/quadrature_encoder.pio)
target_include_directories(firmware PRIVATE include)
target_link_libraries(firmware pico_stdlib hardware_pwm hardware_pio hardware_watchdog hardware_adc hardware_timer)
pico_enable_stdio_usb(firmware 1)
pico_enable_stdio_uart(firmware 0)
pico_add_extra_outputs(firmware)
