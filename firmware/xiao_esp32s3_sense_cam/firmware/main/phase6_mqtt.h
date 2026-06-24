/*
 * phase6_mqtt.h — esp-mqtt client wrapper that publishes on motion.
 *
 * Designed to be safe to call from the motion task: publish() is
 * non-blocking (esp-mqtt queues internally to its own client task).
 * Connection state is exposed atomically so /status can render it.
 */

#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"

typedef enum {
    PHASE6_MQTT_DISABLED   = 0,
    PHASE6_MQTT_CONNECTING = 1,
    PHASE6_MQTT_CONNECTED  = 2,
    PHASE6_MQTT_ERROR      = 3,
} phase6_mqtt_state_t;

/* Loads NVS settings, starts the client iff `mqtt_en` is set and
 * `mqtt_uri` is non-empty. Idempotent. */
esp_err_t phase6_mqtt_init(void);

/* Apply a fresh config (URI + creds + topic + QoS + retain + enabled).
 * If the client is already running, it is stopped and restarted; if
 * `enabled=false`, the client is stopped and state goes to DISABLED. */
esp_err_t phase6_mqtt_apply_config(const char *uri,
                                   const char *user,
                                   const char *pass,
                                   const char *topic,
                                   int qos, bool retain, bool enabled);

/* Publish a single MQTT message to the configured topic. Returns
 * ESP_OK if the message was queued, an error otherwise. Safe to call
 * from any task. No-op when not connected. */
esp_err_t phase6_mqtt_publish_motion_event(uint32_t event_count);

/* Publish a hand-crafted "test" payload, used by the /mqtt-test
 * endpoint. */
esp_err_t phase6_mqtt_publish_test(void);

/* Read state for /status. */
phase6_mqtt_state_t phase6_mqtt_state(void);
const char         *phase6_mqtt_state_name(void);
uint32_t            phase6_mqtt_publish_count(void);
