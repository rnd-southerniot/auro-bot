/*
 * gpio_remap.h — single source of truth for board pin assignment.
 *
 * Board: Seeed Studio XIAO ESP32-S3 Sense (with Sense expansion).
 * Mirrors docs/PIN_MAP.md. Any disagreement is a bug — fix the code, not docs.
 */

#pragma once

#include <assert.h>

/* ============================================================================
 *  Feature flags — flip per phase / per app build.
 * ============================================================================ */

/* Phase 5 (app mode) owns the camera continuously and brings up Wi-Fi.
 * The Phase 2/3/4 boot-time smoke tests are disabled by default; flip
 * them back to 1 to re-run as regression checks. */
#define BOARD_LED_ENABLED        1

#define SENSE_CAMERA_ENABLED     0   /* Phase 2 smoke test         (was: bring-up) */
#define SENSE_PDM_MIC_ENABLED    0   /* Phase 3 smoke test         (was: bring-up) */
#define SENSE_SD_ENABLED         0   /* Phase 4 smoke test         (was: bring-up) */
#define HEADER_SPI2_ENABLED      0   /* External SPI on D8/D9/D10            */

#define PHASE5_NET_ENABLED       1   /* Wi-Fi STA bring-up         (Phase 5.1) */
#define PHASE5_STREAM_ENABLED    1   /* HTTP MJPEG stream          (Phase 5.2) */
#define PHASE5_MOTION_ENABLED    1   /* Motion detect + LED state  (Phase 5.3) */
#define PHASE6_MQTT_ENABLED      1   /* NVS settings + MQTT publish (Phase 6.3) */

/* ============================================================================
 *  XIAO header — silk → GPIO
 * ============================================================================ */

#define XIAO_D0_GPIO              1   /* A0  / ADC1_CH0 */
#define XIAO_D1_GPIO              2   /* A1  / ADC1_CH1 */
#define XIAO_D2_GPIO              3   /* A2  / ADC1_CH2 — STRAPPING, careful */
#define XIAO_D3_GPIO              4   /* A3  / ADC1_CH3 */
#define XIAO_D4_GPIO              5   /* SDA / ADC1_CH4 */
#define XIAO_D5_GPIO              6   /* SCL / ADC1_CH5 */
#define XIAO_D6_GPIO             43   /* TX0 */
#define XIAO_D7_GPIO             44   /* RX0 */
#define XIAO_D8_GPIO              7   /* SPI2 SCK  — shared with Sense SD CLK */
#define XIAO_D9_GPIO              8   /* SPI2 MISO — shared with Sense SD D0  */
#define XIAO_D10_GPIO             9   /* SPI2 MOSI — shared with Sense SD CMD */

/* On-board */
#define BOARD_LED_GPIO           21
#define BOARD_LED_ACTIVE_LOW      1   /* drive LOW to light */

/* ============================================================================
 *  Sense expansion — camera (OV2640, DVP)
 * ============================================================================ */

#define CAM_PIN_PWDN             -1   /* not connected on Sense */
#define CAM_PIN_RESET            -1
#define CAM_PIN_XCLK             10
#define CAM_PIN_SIOD             40   /* SCCB SDA */
#define CAM_PIN_SIOC             39   /* SCCB SCL */
#define CAM_PIN_VSYNC            38
#define CAM_PIN_HREF             47
#define CAM_PIN_PCLK             13
#define CAM_PIN_D0               15   /* Y2 */
#define CAM_PIN_D1               17   /* Y3 */
#define CAM_PIN_D2               18   /* Y4 */
#define CAM_PIN_D3               16   /* Y5 */
#define CAM_PIN_D4               14   /* Y6 */
#define CAM_PIN_D5               12   /* Y7 */
#define CAM_PIN_D6               11   /* Y8 */
#define CAM_PIN_D7               48   /* Y9 */

/* ============================================================================
 *  Sense expansion — PDM microphone
 * ============================================================================ */

#define PDM_MIC_CLK_GPIO         42
#define PDM_MIC_DATA_GPIO        41

/* ============================================================================
 *  Sense expansion — microSD (1-bit SDMMC)
 * ============================================================================ */

#define SD_CLK_GPIO               7   /* aliases XIAO_D8_GPIO  */
#define SD_CMD_GPIO               9   /* aliases XIAO_D10_GPIO */
#define SD_D0_GPIO                8   /* aliases XIAO_D9_GPIO  */

/* ============================================================================
 *  Compile-time conflict guards
 * ============================================================================ */

#if SENSE_SD_ENABLED && HEADER_SPI2_ENABLED
#error "Pin conflict: Sense SD card and external SPI2 on D8/D9/D10 cannot be enabled at the same time. " \
       "See docs/PIN_MAP.md §2.3."
#endif

_Static_assert(SD_CLK_GPIO == XIAO_D8_GPIO,  "SD CLK must alias XIAO D8 — fix gpio_remap.h or PIN_MAP.md");
_Static_assert(SD_CMD_GPIO == XIAO_D10_GPIO, "SD CMD must alias XIAO D10");
_Static_assert(SD_D0_GPIO  == XIAO_D9_GPIO,  "SD D0 must alias XIAO D9");
