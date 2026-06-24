/*
 * Phase 2 — OV2640 single-frame capture smoke test.
 *
 * Hardware: XIAO ESP32-S3 Sense daughterboard (OV2640, DVP 8-bit, SCCB on
 * GPIO39/40). Frame buffers live in PSRAM; DMA descriptors stay in internal
 * SRAM (esp32-camera driver default).
 *
 * The first frame after sensor power-up is often partial or all-zero while
 * the AGC/AEC settles. Retry up to MAX_ATTEMPTS and accept the first frame
 * with a valid JPEG SOI marker (FF D8 FF) and reasonable size.
 */

#include "phase2_camera.h"

#include <inttypes.h>
#include <stdint.h>
#include <string.h>

#include "esp_camera.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "gpio_remap.h"

static const char *TAG = "sense_camera";

#define MAX_ATTEMPTS              5
#define MIN_VALID_JPEG_BYTES   2048u
#define INTER_FRAME_DELAY_MS    100

static const camera_config_t s_cam_cfg = {
    .pin_pwdn       = CAM_PIN_PWDN,
    .pin_reset      = CAM_PIN_RESET,
    .pin_xclk       = CAM_PIN_XCLK,
    .pin_sccb_sda   = CAM_PIN_SIOD,
    .pin_sccb_scl   = CAM_PIN_SIOC,
    .pin_d7         = CAM_PIN_D7,
    .pin_d6         = CAM_PIN_D6,
    .pin_d5         = CAM_PIN_D5,
    .pin_d4         = CAM_PIN_D4,
    .pin_d3         = CAM_PIN_D3,
    .pin_d2         = CAM_PIN_D2,
    .pin_d1         = CAM_PIN_D1,
    .pin_d0         = CAM_PIN_D0,
    .pin_vsync      = CAM_PIN_VSYNC,
    .pin_href       = CAM_PIN_HREF,
    .pin_pclk       = CAM_PIN_PCLK,

    .xclk_freq_hz   = 20 * 1000 * 1000,   /* 20 MHz: OV2640 datasheet typical */
    .ledc_timer     = LEDC_TIMER_0,
    .ledc_channel   = LEDC_CHANNEL_0,

    .pixel_format   = PIXFORMAT_JPEG,
    .frame_size     = FRAMESIZE_QVGA,     /* 320x240 — small, fast, fits easily */
    .jpeg_quality   = 12,                 /* 0=best, 63=worst; 12 = good quality */

    .fb_count       = 2,
    .fb_location    = CAMERA_FB_IN_PSRAM,
    .grab_mode      = CAMERA_GRAB_WHEN_EMPTY,
};

static bool jpeg_soi_ok(const uint8_t *buf, size_t len)
{
    return len >= 3 && buf[0] == 0xFF && buf[1] == 0xD8 && buf[2] == 0xFF;
}

static void log_psram_free(const char *when)
{
    size_t psram_free  = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
    size_t psram_lwm   = heap_caps_get_minimum_free_size(MALLOC_CAP_SPIRAM);
    ESP_LOGI(TAG, "psram %s: free=%u KiB, lwm=%u KiB",
             when, (unsigned)(psram_free / 1024), (unsigned)(psram_lwm / 1024));
}

esp_err_t phase2_camera_capture_one(void)
{
    log_psram_free("pre-init");

    int64_t t0 = esp_timer_get_time();
    esp_err_t err = esp_camera_init(&s_cam_cfg);
    int64_t init_us = esp_timer_get_time() - t0;
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_camera_init failed: 0x%x (%s)", err, esp_err_to_name(err));
        return err;
    }
    ESP_LOGI(TAG, "init OK in %" PRId64 " ms", init_us / 1000);

    log_psram_free("post-init");

    sensor_t *sensor = esp_camera_sensor_get();
    if (sensor != NULL) {
        ESP_LOGI(TAG,
                 "sensor PID=0x%02x VER=0x%02x MIDH=0x%02x MIDL=0x%02x",
                 sensor->id.PID, sensor->id.VER, sensor->id.MIDH, sensor->id.MIDL);
    }

    esp_err_t result = ESP_FAIL;

    for (int attempt = 1; attempt <= MAX_ATTEMPTS; ++attempt) {
        int64_t cap_t0 = esp_timer_get_time();
        camera_fb_t *fb = esp_camera_fb_get();
        int64_t cap_ms = (esp_timer_get_time() - cap_t0) / 1000;

        if (fb == NULL) {
            ESP_LOGW(TAG, "attempt %d: fb_get returned NULL (%" PRId64 " ms)",
                     attempt, cap_ms);
            vTaskDelay(pdMS_TO_TICKS(INTER_FRAME_DELAY_MS));
            continue;
        }

        const bool soi_ok = jpeg_soi_ok(fb->buf, fb->len);
        ESP_LOGI(TAG,
                 "attempt %d: fmt=%d size=%ux%u len=%u soi=%02X %02X %02X %s "
                 "(%" PRId64 " ms)",
                 attempt,
                 (int)fb->format,
                 (unsigned)fb->width,
                 (unsigned)fb->height,
                 (unsigned)fb->len,
                 fb->len >= 1 ? fb->buf[0] : 0u,
                 fb->len >= 2 ? fb->buf[1] : 0u,
                 fb->len >= 3 ? fb->buf[2] : 0u,
                 soi_ok ? "OK" : "BAD",
                 cap_ms);

        if (soi_ok && fb->len >= MIN_VALID_JPEG_BYTES) {
            ESP_LOGI(TAG, "first valid JPEG at attempt %d, len=%u bytes",
                     attempt, (unsigned)fb->len);
            esp_camera_fb_return(fb);
            result = ESP_OK;
            break;
        }

        esp_camera_fb_return(fb);
        vTaskDelay(pdMS_TO_TICKS(INTER_FRAME_DELAY_MS));
    }

    log_psram_free("post-capture");

    if (result != ESP_OK) {
        ESP_LOGE(TAG, "no valid JPEG within %d attempts", MAX_ATTEMPTS);
    }
    return result;
}
