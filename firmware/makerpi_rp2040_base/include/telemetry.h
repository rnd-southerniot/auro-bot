#ifndef NAVBOT_TELEMETRY_H
#define NAVBOT_TELEMETRY_H

#include <stdint.h>

#include "navbot_protocol.h"

struct wheel;
typedef struct wheel wheel_t;

struct cd_motor;
typedef struct cd_motor cd_motor_t;

void navbot_telemetry_send(const char *payload);
void navbot_telemetry_ack(navbot_command_type_t command_type);
void navbot_telemetry_ack_ping(void);
void navbot_telemetry_error(const char *code, const char *message);
void navbot_telemetry_state(const char *mode, const char *fault);
void navbot_telemetry_odom(uint32_t stamp_ms, const wheel_t *left, const wheel_t *right);
void navbot_telemetry_diag(uint32_t stamp_ms, const wheel_t *left, const wheel_t *right);
void navbot_telemetry_vbat(uint32_t stamp_ms, float motor_v, float lidar_v);
void navbot_telemetry_cdrive(uint32_t stamp_ms, const cd_motor_t *left, const cd_motor_t *right);

#endif
