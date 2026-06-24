/*
 * Phase 5.2 — camera frame pump.
 *
 * One task pinned to APP CPU (core 1) does:
 *   esp_camera_fb_get() → SOI check → memcpy into PSRAM latest_buf
 *   → seq++ → esp_camera_fb_return() → log fps every 5 s.
 *
 * Camera config mirrors phase2_camera.c with two tweaks for streaming:
 *   - fb_count    = 3   (was 2; gives the sensor more elasticity when a
 *                        consumer briefly stalls)
 *   - grab_mode   = CAMERA_GRAB_LATEST  (drop stale frames so consumers
 *                                        always see fresh data)
 */

#include "phase5_cam_pump.h"

#include <inttypes.h>
#include <string.h>

#include "esp_camera.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#include "gpio_remap.h"
#if PHASE6_MQTT_ENABLED
#include "phase6_settings.h"
#endif

static const char *TAG = "sense_cam_pump";

/* 256 kB latest_buf holds any JPEG up to UXGA q6 comfortably. */
#define LATEST_BUF_BYTES   (256u * 1024u)
#define MIN_VALID_BYTES    256u
#define FPS_LOG_INTERVAL_S 5

static SemaphoreHandle_t s_mutex;
static uint8_t          *s_latest_buf;
static size_t            s_latest_len;
static uint32_t          s_latest_seq;
static volatile float    s_fps_avg;
static bool              s_started;

/* --- Runtime config (Phase 6.2) --- */

/* Sizes accepted at runtime. VGA and above currently panic with FB-OVF
 * because PSRAM-DMA mode is not enabled in this IDF v6 build of
 * esp32-camera (CAMERA_FB_DMA_PSRAM Kconfig route). Re-enable larger
 * sizes here once that path is available. */
typedef struct { const char *name; framesize_t fs; } fs_entry_t;
static const fs_entry_t FS_TABLE[] = {
    {"QQVGA", FRAMESIZE_QQVGA},
    {"QVGA",  FRAMESIZE_QVGA},
    {"CIF",   FRAMESIZE_CIF},
};
#define FS_TABLE_LEN (sizeof(FS_TABLE) / sizeof(FS_TABLE[0]))

static const char *fs_to_name(framesize_t fs)
{
    for (size_t i = 0; i < FS_TABLE_LEN; ++i) {
        if (FS_TABLE[i].fs == fs) return FS_TABLE[i].name;
    }
    return "?";
}

static framesize_t name_to_fs(const char *name)
{
    for (size_t i = 0; i < FS_TABLE_LEN; ++i) {
        if (strcmp(name, FS_TABLE[i].name) == 0) return FS_TABLE[i].fs;
    }
    return (framesize_t)-1;
}

typedef struct {
    bool        dirty;
    framesize_t framesize;
    int         quality;
} cam_pending_t;

static SemaphoreHandle_t s_cfg_mutex;
static cam_pending_t     s_pending;
static framesize_t       s_cur_fs      = FRAMESIZE_QVGA;
static int               s_cur_quality = 12;

static camera_config_t s_cam_cfg = {
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

    .xclk_freq_hz   = 20 * 1000 * 1000,
    .ledc_timer     = LEDC_TIMER_0,
    .ledc_channel   = LEDC_CHANNEL_0,

    .pixel_format   = PIXFORMAT_JPEG,
    .frame_size     = FRAMESIZE_QVGA,
    .jpeg_quality   = 12,

    .fb_count       = 3,
    .fb_location    = CAMERA_FB_IN_PSRAM,
    .grab_mode      = CAMERA_GRAB_LATEST,
};

static void apply_pending_config_locked(void)
{
    cam_pending_t pend;
    xSemaphoreTake(s_cfg_mutex, portMAX_DELAY);
    pend = s_pending;
    s_pending.dirty = false;
    xSemaphoreGive(s_cfg_mutex);
    if (!pend.dirty) return;

    /* Quality-only change: hot-swap, no reinit. */
    if (pend.framesize == s_cur_fs && pend.quality != s_cur_quality) {
        sensor_t *s = esp_camera_sensor_get();
        if (s != NULL && s->set_quality != NULL) {
            s->set_quality(s, pend.quality);
            s_cur_quality      = pend.quality;
            s_cam_cfg.jpeg_quality = pend.quality;
            ESP_LOGI(TAG, "quality -> %d (no reinit)", pend.quality);
        }
        return;
    }

    /* Frame-size change: deinit + reinit. ~340 ms freeze. */
    if (pend.framesize != s_cur_fs) {
        const framesize_t old_fs = s_cur_fs;
        ESP_LOGI(TAG, "reconfig: %s q%d -> %s q%d (deinit + reinit)",
                 fs_to_name(old_fs), s_cur_quality,
                 fs_to_name(pend.framesize), pend.quality);
        esp_camera_deinit();
        s_cam_cfg.frame_size   = pend.framesize;
        s_cam_cfg.jpeg_quality = pend.quality;
        esp_err_t err = esp_camera_init(&s_cam_cfg);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "reinit failed at %s: 0x%x — restoring %s",
                     fs_to_name(pend.framesize), err, fs_to_name(old_fs));
            s_cam_cfg.frame_size   = old_fs;
            s_cam_cfg.jpeg_quality = s_cur_quality;
            (void)esp_camera_init(&s_cam_cfg);
        } else {
            s_cur_fs      = pend.framesize;
            s_cur_quality = pend.quality;
        }
    }
}

static void cam_pump_task(void *arg)
{
    (void)arg;
    int64_t window_t0 = esp_timer_get_time();
    int     window_n  = 0;

    while (true) {
        apply_pending_config_locked();

        camera_fb_t *fb = esp_camera_fb_get();
        if (fb == NULL) {
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }

        const bool soi_ok = fb->len >= 3 && fb->buf[0] == 0xFF
                          && fb->buf[1] == 0xD8 && fb->buf[2] == 0xFF;
        if (!soi_ok || fb->len < MIN_VALID_BYTES) {
            esp_camera_fb_return(fb);
            continue;
        }

        if (fb->len <= LATEST_BUF_BYTES) {
            xSemaphoreTake(s_mutex, portMAX_DELAY);
            memcpy(s_latest_buf, fb->buf, fb->len);
            s_latest_len = fb->len;
            s_latest_seq++;
            xSemaphoreGive(s_mutex);
        } else {
            ESP_LOGW(TAG, "frame too large for latest_buf: %u > %u; dropped",
                     (unsigned)fb->len, (unsigned)LATEST_BUF_BYTES);
        }
        esp_camera_fb_return(fb);

        window_n++;
        int64_t now = esp_timer_get_time();
        int64_t dt  = now - window_t0;
        if (dt >= (int64_t)FPS_LOG_INTERVAL_S * 1000 * 1000) {
            float fps = (float)window_n * 1e6f / (float)dt;
            s_fps_avg = fps;
            ESP_LOGI(TAG, "fps_avg=%.1f latest_len=%u seq=%" PRIu32
                          " psram_free=%u KiB",
                     fps,
                     (unsigned)s_latest_len,
                     s_latest_seq,
                     (unsigned)(heap_caps_get_free_size(MALLOC_CAP_SPIRAM) / 1024));
            window_t0 = now;
            window_n  = 0;
        }
    }
}

esp_err_t phase5_cam_pump_start(void)
{
    if (s_started) return ESP_ERR_INVALID_STATE;

#if PHASE6_MQTT_ENABLED
    /* Override compile-time defaults from the NVS-stored last-known-good. */
    char fs_name[16];
    phase6_settings_get_str("cam_fs", fs_name, sizeof(fs_name), "QVGA");
    framesize_t fs0 = name_to_fs(fs_name);
    if ((int)fs0 >= 0) s_cam_cfg.frame_size = fs0;
    int q0 = phase6_settings_get_int("cam_q", 12);
    if (q0 >= 6 && q0 <= 30) s_cam_cfg.jpeg_quality = q0;
#endif

    int64_t t0 = esp_timer_get_time();
    esp_err_t err = esp_camera_init(&s_cam_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_camera_init: 0x%x (%s)", err, esp_err_to_name(err));
        return err;
    }
    int64_t init_ms = (esp_timer_get_time() - t0) / 1000;

    sensor_t *sensor = esp_camera_sensor_get();
    ESP_LOGI(TAG, "camera init OK in %" PRId64 " ms (PID=0x%02x)",
             init_ms, sensor ? sensor->id.PID : 0);

    s_latest_buf = heap_caps_malloc(LATEST_BUF_BYTES, MALLOC_CAP_SPIRAM);
    if (s_latest_buf == NULL) {
        ESP_LOGE(TAG, "PSRAM alloc %u failed", (unsigned)LATEST_BUF_BYTES);
        return ESP_ERR_NO_MEM;
    }
    s_latest_len = 0;
    s_latest_seq = 0;
    s_mutex     = xSemaphoreCreateMutex();
    s_cfg_mutex = xSemaphoreCreateMutex();
    if (s_mutex == NULL || s_cfg_mutex == NULL) return ESP_ERR_NO_MEM;
    s_cur_fs      = s_cam_cfg.frame_size;
    s_cur_quality = s_cam_cfg.jpeg_quality;

    BaseType_t ok = xTaskCreatePinnedToCore(
        cam_pump_task, "cam_pump", 4096, NULL, 5, NULL, /* core */ 1);
    if (ok != pdPASS) {
        ESP_LOGE(TAG, "xTaskCreatePinnedToCore failed");
        return ESP_ERR_NO_MEM;
    }

    s_started = true;
    ESP_LOGI(TAG, "cam_pump task pinned to core 1, prio 5, latest_cap=%u kB",
             (unsigned)(LATEST_BUF_BYTES / 1024));
    return ESP_OK;
}

esp_err_t phase5_cam_pump_copy_latest(uint8_t *out, size_t max,
                                      size_t *len, uint32_t *seq)
{
    if (!s_started) return ESP_ERR_INVALID_STATE;
    if (out == NULL || len == NULL || seq == NULL) return ESP_ERR_INVALID_ARG;

    esp_err_t result = ESP_ERR_NOT_FOUND;
    xSemaphoreTake(s_mutex, portMAX_DELAY);
    if (s_latest_seq == 0 || s_latest_len == 0) {
        result = ESP_ERR_NOT_FOUND;
    } else if (max < s_latest_len) {
        *len = s_latest_len;
        *seq = s_latest_seq;
        result = ESP_ERR_INVALID_SIZE;
    } else {
        memcpy(out, s_latest_buf, s_latest_len);
        *len = s_latest_len;
        *seq = s_latest_seq;
        result = ESP_OK;
    }
    xSemaphoreGive(s_mutex);
    return result;
}

float phase5_cam_pump_fps(void)
{
    return s_fps_avg;
}

esp_err_t phase5_cam_pump_request_framesize(const char *name)
{
    if (!s_started) return ESP_ERR_INVALID_STATE;
    if (name == NULL) return ESP_ERR_INVALID_ARG;
    framesize_t fs = name_to_fs(name);
    if ((int)fs < 0) {
        ESP_LOGW(TAG, "unknown framesize: '%s'", name);
        return ESP_ERR_INVALID_ARG;
    }
    xSemaphoreTake(s_cfg_mutex, portMAX_DELAY);
    /* Preserve any quality already queued by an earlier call in the
     * same request; otherwise carry current. */
    if (!s_pending.dirty) {
        s_pending.quality = s_cur_quality;
    }
    s_pending.framesize = fs;
    s_pending.dirty     = true;
    xSemaphoreGive(s_cfg_mutex);
    return ESP_OK;
}

esp_err_t phase5_cam_pump_request_quality(int q)
{
    if (!s_started) return ESP_ERR_INVALID_STATE;
    if (q < 6 || q > 30) return ESP_ERR_INVALID_ARG;
    xSemaphoreTake(s_cfg_mutex, portMAX_DELAY);
    /* Preserve any framesize already queued by an earlier call in the
     * same request; otherwise carry current. */
    if (!s_pending.dirty) {
        s_pending.framesize = s_cur_fs;
    }
    s_pending.quality = q;
    s_pending.dirty   = true;
    xSemaphoreGive(s_cfg_mutex);
    return ESP_OK;
}

const char *phase5_cam_pump_get_framesize_name(void)
{
    return fs_to_name(s_cur_fs);
}

int phase5_cam_pump_get_quality(void)
{
    return s_cur_quality;
}
