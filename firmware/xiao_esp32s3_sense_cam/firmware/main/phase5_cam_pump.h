/*
 * phase5_cam_pump.h — Phase 5.2 single-producer camera frame pump.
 *
 * Owns the OV3660 camera lifecycle for app mode. Initialises the sensor
 * once, runs a producer task that grabs frames from the esp32-camera
 * pool, validates the JPEG SOI marker, copies the bytes into a single
 * PSRAM-backed "latest" buffer, and bumps a sequence counter.
 *
 * Multiple consumers (HTTP stream handlers, motion detection task) can
 * sample the latest frame via phase5_cam_pump_copy_latest() without
 * touching the camera pool themselves — keeps the fb pool usage
 * deterministic and decouples consumer pacing from camera pacing.
 */

#pragma once

#include <stddef.h>
#include <stdint.h>

#include "esp_err.h"

/* Initialise the camera and start the pump task.
 * Idempotent guard: returns ESP_ERR_INVALID_STATE if already started. */
esp_err_t phase5_cam_pump_start(void);

/* Copy the latest validated JPEG into `out`. On success, `*len` and
 * `*seq` are populated; `seq` is monotonic and lets consumers detect a
 * fresh frame.
 *
 * Returns:
 *   ESP_OK             — frame copied
 *   ESP_ERR_NOT_FOUND  — no frame produced yet (still warming up)
 *   ESP_ERR_INVALID_SIZE — `max` is smaller than the latest frame
 */
esp_err_t phase5_cam_pump_copy_latest(uint8_t *out, size_t max,
                                      size_t *len, uint32_t *seq);

/* Average frames-per-second over the last logging window (5 s). */
float phase5_cam_pump_fps(void);

/* Runtime camera control. Phase 6.2.
 *
 * Frame-size strings accepted: "QQVGA", "QVGA", "CIF", "VGA", "SVGA",
 * "XGA", "HD", "UXGA". Quality range 6–30 (lower = better, smaller
 * range than esp32-camera's 0–63 to keep the slider usable).
 *
 * Changes are queued and applied by the cam_pump task at the next loop
 * iteration; quality alone is hot-tweaked via sensor->set_quality with
 * no reinit, frame-size triggers a deinit + reinit (~340 ms freeze).
 *
 * Returns ESP_OK on accepted, ESP_ERR_INVALID_ARG on bad name/value,
 * ESP_ERR_INVALID_STATE if pump not yet started. */
esp_err_t phase5_cam_pump_request_framesize(const char *name);
esp_err_t phase5_cam_pump_request_quality(int q);

/* Read current values (for /status JSON). */
const char *phase5_cam_pump_get_framesize_name(void);
int         phase5_cam_pump_get_quality(void);
