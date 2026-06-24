/*
 * phase5_motion.h — Phase 5.3 frame-difference motion detection.
 *
 * Pulls latest JPEGs from phase5_cam_pump at MOTION_POLL_MS, decodes to a
 * small grayscale frame (320×240 → 80×60 via JPG_SCALE_4X), diffs against
 * the previous frame, and exposes an "active for the next HOLD_MS"
 * boolean to consumers (LED state machine, /status endpoint).
 */

#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"

/* Spawn the motion task. Returns ESP_ERR_INVALID_STATE if already running. */
esp_err_t phase5_motion_start(void);

/* True iff a motion event was detected within the last HOLD_MS. */
bool phase5_motion_is_active(void);

/* Seconds since the last detected motion sample.
 * Returns -1.0f if no motion has ever been seen. */
float phase5_motion_seconds_since_last(void);

/* Total rising-edge motion events since boot. */
uint32_t phase5_motion_event_count(void);

/* Runtime enable/disable. When disabled, phase5_motion_is_active() returns
 * false, no events are counted, and the previous frame buffer is dropped
 * so re-enabling does not produce a spurious comparison against a stale
 * frame. Default is enabled. */
void phase5_motion_set_enabled(bool enabled);
bool phase5_motion_get_enabled(void);

/* Register a callback fired on the rising edge of motion (idle → active).
 * Runs on the motion task — keep work non-blocking. NULL clears. */
typedef void (*phase5_motion_event_cb_t)(uint32_t event_count);
void phase5_motion_set_event_handler(phase5_motion_event_cb_t cb);
