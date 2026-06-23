#include "telemetry.h"

#include <stdio.h>
#include <string.h>

#include "counter_drive.h"
#include "serial_parser.h"
#include "wheel.h"

void navbot_telemetry_send(const char *payload) {
    size_t len = strlen(payload);
    uint8_t csum = navbot_checksum_xor(payload, len);
    printf("%s*%02X\n", payload, csum);
}

void navbot_telemetry_ack(navbot_command_type_t command_type) {
    char buf[NAVBOT_PROTOCOL_MAX_LINE];
    snprintf(buf, sizeof(buf), "ACK %s", navbot_command_name(command_type));
    navbot_telemetry_send(buf);
}

void navbot_telemetry_ack_ping(void) {
    char buf[NAVBOT_PROTOCOL_MAX_LINE];
    snprintf(buf, sizeof(buf), "ACK PING %s", FIRMWARE_VERSION);
    navbot_telemetry_send(buf);
}

void navbot_telemetry_error(const char *code, const char *message) {
    char buf[NAVBOT_PROTOCOL_MAX_LINE];
    snprintf(buf, sizeof(buf), "ERR %s %s", code, message);
    navbot_telemetry_send(buf);
}

void navbot_telemetry_state(const char *mode, const char *fault) {
    char buf[NAVBOT_PROTOCOL_MAX_LINE];
    snprintf(buf, sizeof(buf), "STATE %s %s", mode, fault);
    navbot_telemetry_send(buf);
}

void navbot_telemetry_odom(uint32_t stamp_ms, const wheel_t *left, const wheel_t *right) {
    char buf[NAVBOT_PROTOCOL_MAX_LINE];
    snprintf(
        buf, sizeof(buf),
        "ODOM %lu %lld %lld %.4f %.4f",
        (unsigned long)stamp_ms,
        (long long)left->enc_count,
        (long long)right->enc_count,
        (double)wheel_cps_to_mps(left, left->speed_filtered),
        (double)wheel_cps_to_mps(right, right->speed_filtered)
    );
    navbot_telemetry_send(buf);
}

void navbot_telemetry_vbat(uint32_t stamp_ms, float motor_v, float lidar_v) {
    char buf[NAVBOT_PROTOCOL_MAX_LINE];
    snprintf(buf, sizeof(buf), "VBAT %lu %.3f %.3f",
        (unsigned long)stamp_ms, (double)motor_v, (double)lidar_v);
    navbot_telemetry_send(buf);
}

void navbot_telemetry_cdrive(uint32_t stamp_ms, const cd_motor_t *left, const cd_motor_t *right) {
    /*
     * CDRIVE <stamp_ms> <l_state> <l_pwm> <l_dur_ms> <l_fault>
     *                   <r_state> <r_pwm> <r_dur_ms> <r_fault>
     *
     * state : 0=IDLE 1=NORMAL 2=DECEL_MON 3=ACTIVE 4=FAULT
     * pwm   : last CD-applied PWM (signed, -999..+999; 0 unless ACTIVE)
     * dur_ms: ms elapsed in ACTIVE (0 otherwise)
     * fault : 0=none 1=watchdog 2=anomaly 3=shared_abort
     *
     * RECOVERY from CD_STATE_FAULT (l_state==4 OR r_state==4):
     *   Send "STOP\n" over serial. counter_drive_reset() is invoked
     *   for both motors: cd_state returns to IDLE (0), last_fault
     *   clears to 0, watchdog alarm is disarmed, and shared_abort is
     *   dropped iff both motors are non-FAULT. "RESET\n" works the
     *   same way and additionally clears a latched safety fault
     *   (ESTOP / STALL / RUN_TIMEOUT).
     *
     * Emitted at the telemetry interval; this is observational only,
     * not on the safety path.
     */
    char buf[NAVBOT_PROTOCOL_MAX_LINE];
    snprintf(
        buf, sizeof(buf),
        "CDRIVE %lu %u %d %lu %u %u %d %lu %u",
        (unsigned long)stamp_ms,
        (unsigned)cd_state_wire(left->state),
        (int)left->current_pwm,
        (unsigned long)cd_duration_ms(left),
        (unsigned)cd_fault_wire(left->last_fault),
        (unsigned)cd_state_wire(right->state),
        (int)right->current_pwm,
        (unsigned long)cd_duration_ms(right),
        (unsigned)cd_fault_wire(right->last_fault)
    );
    navbot_telemetry_send(buf);
}

void navbot_telemetry_diag(uint32_t stamp_ms, const wheel_t *left, const wheel_t *right) {
    char buf[NAVBOT_PROTOCOL_MAX_LINE];
    snprintf(
        buf, sizeof(buf),
        "DIAG %lu L:%d,%.1f,%.1f,%.1f,%.1f,%.1f,%lu R:%d,%.1f,%.1f,%.1f,%.1f,%.1f,%lu",
        (unsigned long)stamp_ms,
        (int)left->duty,
        (double)left->speed_setpoint_cps,
        (double)left->speed_filtered,
        (double)left->speed_pid.last_p_term,
        (double)left->speed_pid.last_i_term,
        (double)left->speed_pid.last_d_term,
        (unsigned long)left->stall_timer_ms,
        (int)right->duty,
        (double)right->speed_setpoint_cps,
        (double)right->speed_filtered,
        (double)right->speed_pid.last_p_term,
        (double)right->speed_pid.last_i_term,
        (double)right->speed_pid.last_d_term,
        (unsigned long)right->stall_timer_ms
    );
    navbot_telemetry_send(buf);
}
