#ifndef NAVBOT_PROTOCOL_H
#define NAVBOT_PROTOCOL_H

#include <stddef.h>
#include <stdint.h>

/*
 * navbot_protocol.h
 *
 * Line-based serial protocol between the Raspberry Pi ROS 2 stack
 * and the Maker Pi RP2040 base controller.
 *
 * Commands from Pi to RP2040:
 *   PING
 *   STOP
 *   RESET
 *   ESTOP
 *   CMD_VEL <linear_mps> <angular_rps>
 *   WHEEL_VEL <left_mps> <right_mps>
 *   DIAG
 *   TEST_PWM <left_duty> <right_duty>
 *     Bench-only. Applies raw signed PWM to each motor for a fixed
 *     1000 ms pulse, then coasts. Duty range: -999..+999 (the PWM
 *     wrap). Blocks in the command handler while petting the HW
 *     watchdog. Rejected if safety is faulted. Guarded at the command
 *     handler by TEST_PWM_ENABLED; the parser recognises the command
 *     regardless so a disabled build emits a clear error.
 *
 * Telemetry from RP2040 to Pi:
 *   ACK PING <firmware_version>
 *   ACK <command>
 *   ERR <code> <message>
 *   STATE <mode> <fault>
 *   ODOM <stamp_ms> <left_count> <right_count> <left_vel_mps> <right_vel_mps>
 *
 * Integrity:
 *   Every line may carry an XOR checksum suffix: *XX
 *   where XX is the two-digit uppercase hex XOR of all bytes before '*'.
 *   If '*' is present, the checksum is validated; if absent, the line is
 *   accepted as-is (backward compatibility for bench terminals).
 *
 * Design goals:
 *   - human-readable and easy to test with a serial terminal
 *   - deterministic enough for an MVP robot
 *   - simple for Python parsing on the Pi side
 */

#define NAVBOT_PROTOCOL_BAUDRATE 115200
#define NAVBOT_PROTOCOL_MAX_LINE 192
#define FIRMWARE_VERSION "1.3.0"

typedef enum navbot_command_type {
    NAVBOT_CMD_UNKNOWN = 0,
    NAVBOT_CMD_PING,
    NAVBOT_CMD_STOP,
    NAVBOT_CMD_RESET,
    NAVBOT_CMD_ESTOP,
    NAVBOT_CMD_CMD_VEL,
    NAVBOT_CMD_WHEEL_VEL,
    NAVBOT_CMD_DIAG,
    NAVBOT_CMD_TEST_PWM,
} navbot_command_type_t;

typedef struct navbot_command {
    navbot_command_type_t type;
    float value_1;
    float value_2;
} navbot_command_t;

/*
 * Compute XOR checksum of a byte buffer.
 * Returns the XOR of all bytes in data[0..len-1].
 */
static inline uint8_t navbot_checksum_xor(const char *data, size_t len) {
    uint8_t csum = 0;
    for (size_t i = 0; i < len; ++i) {
        csum ^= (uint8_t)data[i];
    }
    return csum;
}

#endif
