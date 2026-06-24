/*
 * phase5_led.h — pattern-driven LED task.
 *
 * Replaces the inline `while(true) toggle; vTaskDelay` heartbeat that
 * ran in app_main during Phase 1–5.1. Reads phase5_motion_is_active()
 * once per LED half-period and picks between heartbeat (1 Hz) and
 * fast-blink (5 Hz).
 */

#pragma once

#include "esp_err.h"

esp_err_t phase5_led_start(void);
