/*
 * phase6_settings.h — thin NVS-backed key/value store.
 *
 * Single namespace ("siot_p6"). Modules read defaults at startup and
 * write back on every successful runtime change so the device boots
 * into the operator's last-known-good config.
 *
 * Keys (max 15 chars per NVS rule):
 *   cam_fs     str  framesize name ("QVGA", "CIF", …)
 *   cam_q      i32  JPEG quality (6-30, lower = better)
 *   motion_en  u8   motion detection enabled (0/1)
 *   mqtt_uri   str  broker URI ("mqtt://host:1883" / "mqtts://…")
 *   mqtt_topic str  publish topic
 *   mqtt_user  str  optional username
 *   mqtt_pass  str  optional password (plaintext)
 *   mqtt_qos   i32  0|1|2
 *   mqtt_retain u8  0/1
 *   mqtt_en    u8   MQTT client should connect (0/1)
 */

#pragma once

#include <stdbool.h>
#include <stddef.h>

#include "esp_err.h"

/* Open the NVS handle. Idempotent. */
esp_err_t phase6_settings_init(void);

/* Typed accessors. Returning the default on missing key keeps callers
 * branch-free. set_* always commits before returning. */
esp_err_t phase6_settings_get_str(const char *key, char *out, size_t maxlen, const char *def);
esp_err_t phase6_settings_set_str(const char *key, const char *val);
int       phase6_settings_get_int(const char *key, int def);
esp_err_t phase6_settings_set_int(const char *key, int val);
bool      phase6_settings_get_bool(const char *key, bool def);
esp_err_t phase6_settings_set_bool(const char *key, bool val);
