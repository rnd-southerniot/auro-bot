/*
 * phase4_sd.h — Phase 4 microSD bring-up.
 *
 * Mounts the Sense expansion's microSD slot via SDMMC 1-bit (CLK=GPIO7,
 * CMD=GPIO9, D0=GPIO8), prints card identity, writes and reads back a
 * small test file, and unmounts. One-shot smoke test, not a persistent
 * filesystem mount.
 */

#pragma once

#include "esp_err.h"

esp_err_t phase4_sd_capture_one(void);
