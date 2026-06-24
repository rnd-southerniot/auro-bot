/*
 * system_config.h — board-wide constants and expected hardware identity.
 * Used by Phase 1 sanity report to fail loudly if reality disagrees.
 */

#pragma once

#include <stdint.h>

/* Identity of the N8R8 module fused at Espressif. */
#define BOARD_NAME                  "XIAO ESP32-S3 Sense"
#define BOARD_EXPECTED_FLASH_BYTES  (8u * 1024u * 1024u)
#define BOARD_EXPECTED_PSRAM_BYTES  (8u * 1024u * 1024u)
#define BOARD_EXPECTED_CPU_MHZ      240u
#define BOARD_EXPECTED_CORES        2u

/* Heartbeat */
#define HEARTBEAT_PERIOD_MS         1000u
