/*
 * phase3_mic.h — Phase 3 PDM microphone bring-up.
 *
 * Initializes I²S0 in PDM RX mode against the Sense expansion's MEMS mic
 * (GPIO42 = CLK, GPIO41 = DATA), captures ~1 s of 16-bit mono @ 16 kHz,
 * and reports peak, RMS, and DC offset. Designed to fail loudly if the
 * mic is dead (all-zero buffer) or stuck (DC-only).
 */

#pragma once

#include "esp_err.h"

esp_err_t phase3_mic_capture_one(void);
