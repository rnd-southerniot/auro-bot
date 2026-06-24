/*
 * phase2_camera.h — Phase 2 OV2640 bring-up.
 *
 * Initializes the camera with pins from gpio_remap.h and captures a single
 * JPEG frame, validating the SOI marker and a minimum size. Designed to be
 * a one-shot smoke test, not a streaming pipeline.
 */

#pragma once

#include "esp_err.h"

/* Run the Phase 2 capture-one-frame smoke test.
 *
 * Returns ESP_OK if a valid JPEG was captured. The frame buffer is released
 * back to the camera driver before this function returns; callers don't
 * need to manage it.
 *
 * Logs (TAG = "sense_camera"):
 *   - init status
 *   - per-attempt frame size + header bytes
 *   - PSRAM free before/after
 */
esp_err_t phase2_camera_capture_one(void);
