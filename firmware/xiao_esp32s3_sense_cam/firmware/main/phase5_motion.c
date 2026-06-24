/*
 * Phase 5.3 — motion detection.
 *
 * Algorithm (per iteration, every MOTION_POLL_MS):
 *   1. Pull latest JPEG from cam_pump (skip if no fresh frame).
 *   2. jpg2rgb565 with JPG_SCALE_4X → 80×60 RGB565 in PSRAM scratch.
 *   3. Convert each RGB565 pixel to 8-bit Y (luma) using the integer
 *      approximation Y = (77·R + 150·G + 29·B) >> 8.
 *   4. If we have a previous Y plane, count pixels with
 *      |cur − prev| > PIXEL_DELTA_THR; report "motion" if the
 *      changed-fraction exceeds MOTION_PCT_THR.
 *   5. On rising edge: increment event_count, log, set
 *      motion_active_until_ms = now + HOLD_MS.
 *   6. Swap (cur, prev) — zero-copy.
 *
 * Tunables are at the top so they're easy to revisit without digging.
 *
 * Concurrency: motion_active_until_ms / last_motion_ms / event_count
 * are C11 atomics; multiple readers (LED task, /status handler) are
 * fine without locking.
 */

#include "phase5_motion.h"

#include <inttypes.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "esp_camera.h"             /* for jpg_scale_t / JPG_SCALE_4X via img_converters.h */
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "img_converters.h"

#include "phase5_cam_pump.h"
#include "gpio_remap.h"
#if PHASE6_MQTT_ENABLED
#include "phase6_settings.h"
#endif

static const char *TAG = "sense_motion";

/* ---- Tunables ----
 * Calibrated on the OV3660 in a typical indoor scene 2026-04-26:
 *   static-scene noise floor (post drift compensation): 4–6 %
 *   AGC step events:                                    50–75 % with drift ~25
 *   hand-wave motion:                                   30–80 %, drift < 5
 * Thresholds chosen with margin between noise floor and motion. */
#define MOTION_POLL_MS           200    /* 5 Hz check rate */
#define HOLD_MS                  2000   /* "active" window after a detection */
#define PIXEL_DELTA_THR          30     /* per-pixel grayscale delta (0–255) */
#define MOTION_PCT_THR           15.0f  /* percent of pixels changed */
#define MAX_DRIFT_ABS            15     /* skip frame as AGC event if |mean shift| > this */
#define MOTION_W                 80     /* QVGA / 4 */
#define MOTION_H                 60
#define MOTION_PX                (MOTION_W * MOTION_H)        /* 4 800 */
#define MOTION_RGB_BYTES         (MOTION_PX * 2)              /* 9 600 */
#define JPEG_SCRATCH_BYTES       (64u * 1024u)
#define MOTION_TASK_STACK        6144

/* ---- Atomic state shared with consumers ---- */
static _Atomic int64_t  s_motion_until_ms = 0;     /* 0 = never */
static _Atomic int64_t  s_last_motion_ms  = -1;    /* -1 = never */
static _Atomic uint32_t s_event_count     = 0;
static _Atomic bool     s_enabled         = true;  /* Phase 6.2 toggle */
static _Atomic bool     s_drop_prev       = false; /* set on enable to skip stale prev */
static bool             s_started         = false;
static phase5_motion_event_cb_t s_event_cb = NULL; /* Phase 6.3 callback */

static inline int64_t now_ms(void)
{
    return esp_timer_get_time() / 1000;
}

static inline uint8_t rgb565_to_y(uint16_t px)
{
    /* esp32-camera writes RGB565 big-endian, but jpg2rgb565 actually
     * stores each 16-bit pixel as two consecutive bytes already in
     * native (little-endian) layout in the buffer. We let the caller
     * load the value with a normal uint16_t read of the correctly
     * shifted bytes. */
    uint8_t r5 = (uint8_t)((px >> 11) & 0x1F);
    uint8_t g6 = (uint8_t)((px >> 5)  & 0x3F);
    uint8_t b5 = (uint8_t)( px        & 0x1F);
    uint8_t r8 = (uint8_t)((r5 << 3) | (r5 >> 2));
    uint8_t g8 = (uint8_t)((g6 << 2) | (g6 >> 4));
    uint8_t b8 = (uint8_t)((b5 << 3) | (b5 >> 2));
    return (uint8_t)((77u * r8 + 150u * g8 + 29u * b8) >> 8);
}

static void rgb565_buf_to_y(const uint8_t *rgb, uint8_t *y, size_t n_px)
{
    for (size_t i = 0; i < n_px; ++i) {
        /* esp32-camera's jpg2rgb565 writes high byte then low byte. */
        uint16_t px = (uint16_t)((rgb[2 * i] << 8) | rgb[2 * i + 1]);
        y[i] = rgb565_to_y(px);
    }
}

/* Compute the mean signed (cur − prev) drift across the whole frame.
 * This represents global brightness shift driven by AGC/AWB oscillation
 * on the OV3660. Subtracting it from per-pixel diffs makes the metric
 * insensitive to uniform exposure changes. */
static int mean_drift(const uint8_t *cur, const uint8_t *prev, size_t n_px)
{
    int64_t sum = 0;
    for (size_t i = 0; i < n_px; ++i) {
        sum += (int)cur[i] - (int)prev[i];
    }
    return (int)(sum / (int64_t)n_px);
}

/* Count pixels whose change exceeds the threshold *after* removing the
 * global drift. Returns count of "real motion" pixels and writes the
 * inferred mean drift to *drift if non-NULL (for diagnostic logging). */
static size_t count_changed(const uint8_t *cur, const uint8_t *prev,
                            size_t n_px, int *drift_out)
{
    int drift = mean_drift(cur, prev, n_px);
    if (drift_out) *drift_out = drift;
    size_t changed = 0;
    for (size_t i = 0; i < n_px; ++i) {
        int d = (int)cur[i] - (int)prev[i] - drift;
        if (d < 0) d = -d;
        if (d > PIXEL_DELTA_THR) changed++;
    }
    return changed;
}

static void motion_task(void *arg)
{
    (void)arg;

    uint8_t *jpeg = heap_caps_malloc(JPEG_SCRATCH_BYTES, MALLOC_CAP_SPIRAM);
    uint8_t *rgb  = heap_caps_malloc(MOTION_RGB_BYTES,   MALLOC_CAP_SPIRAM);
    uint8_t *y_a  = heap_caps_malloc(MOTION_PX,          MALLOC_CAP_SPIRAM);
    uint8_t *y_b  = heap_caps_malloc(MOTION_PX,          MALLOC_CAP_SPIRAM);
    if (jpeg == NULL || rgb == NULL || y_a == NULL || y_b == NULL) {
        ESP_LOGE(TAG, "PSRAM alloc failed (jpeg/rgb/y_a/y_b)");
        free(jpeg); free(rgb); free(y_a); free(y_b);
        vTaskDelete(NULL);
    }
    uint8_t *cur  = y_a;
    uint8_t *prev = y_b;
    bool     have_prev = false;
    bool     was_active = false;

    ESP_LOGI(TAG, "motion task started, scale=4x grid=%dx%d hold=%d ms thr=%d/%.0f%%",
             MOTION_W, MOTION_H, HOLD_MS, PIXEL_DELTA_THR, (double)MOTION_PCT_THR);

    uint32_t last_seq = 0;

    while (true) {
        vTaskDelay(pdMS_TO_TICKS(MOTION_POLL_MS));

        if (!atomic_load(&s_enabled)) {
            have_prev  = false;
            was_active = false;
            continue;
        }
        if (atomic_load(&s_drop_prev)) {
            atomic_store(&s_drop_prev, false);
            have_prev = false;
        }

        size_t   jlen = 0;
        uint32_t seq  = 0;
        esp_err_t cr = phase5_cam_pump_copy_latest(jpeg, JPEG_SCRATCH_BYTES, &jlen, &seq);
        if (cr != ESP_OK || seq == last_seq) continue;
        last_seq = seq;

        if (!jpg2rgb565(jpeg, jlen, rgb, JPG_SCALE_4X)) {
            ESP_LOGW(TAG, "jpg2rgb565 failed (len=%u seq=%" PRIu32 ")",
                     (unsigned)jlen, seq);
            continue;
        }
        rgb565_buf_to_y(rgb, cur, MOTION_PX);

        if (have_prev) {
            int    drift   = 0;
            size_t changed = count_changed(cur, prev, MOTION_PX, &drift);
            float  pct     = 100.0f * (float)changed / (float)MOTION_PX;
            int64_t now    = now_ms();

            /* Periodic debug log (every 5 s) so we can see pct/sample stats
             * without flooding the console. Useful for tuning thresholds
             * to a particular installation. */
            static int64_t s_dbg_t0 = 0;
            const bool agc_event = (drift >  MAX_DRIFT_ABS) ||
                                   (drift < -MAX_DRIFT_ABS);
            if (now - s_dbg_t0 >= 5000) {
                s_dbg_t0 = now;
                ESP_LOGI(TAG, "sample: changed=%u/%u (%.1f%%) drift=%d%s",
                         (unsigned)changed, (unsigned)MOTION_PX, (double)pct,
                         drift, agc_event ? " [agc-skip]" : "");
            }

            if (!agc_event && pct > MOTION_PCT_THR) {
                atomic_store(&s_motion_until_ms, now + HOLD_MS);
                atomic_store(&s_last_motion_ms,  now);
                if (!was_active) {
                    uint32_t cnt = atomic_fetch_add(&s_event_count, 1) + 1;
                    ESP_LOGI(TAG, "motion ON  changed=%u/%u (%.1f%%)",
                             (unsigned)changed, (unsigned)MOTION_PX, (double)pct);
                    was_active = true;
                    /* Phase 6.3: notify subscribers (e.g. MQTT publisher).
                     * Cb runs on this task so it must be non-blocking. */
                    phase5_motion_event_cb_t cb = s_event_cb;
                    if (cb != NULL) cb(cnt);
                }
            } else if (was_active && now > atomic_load(&s_motion_until_ms)) {
                ESP_LOGI(TAG, "motion OFF (held %d ms)", HOLD_MS);
                was_active = false;
            }
        }

        /* swap, no copy */
        uint8_t *tmp = prev;
        prev = cur;
        cur  = tmp;
        have_prev = true;
    }
}

esp_err_t phase5_motion_start(void)
{
    if (s_started) return ESP_ERR_INVALID_STATE;
#if PHASE6_MQTT_ENABLED
    atomic_store(&s_enabled, phase6_settings_get_bool("motion_en", true));
#endif
    BaseType_t ok = xTaskCreatePinnedToCore(
        motion_task, "motion", MOTION_TASK_STACK, NULL, /* prio */ 4,
        NULL, /* core */ 0);
    if (ok != pdPASS) {
        ESP_LOGE(TAG, "xTaskCreatePinnedToCore failed");
        return ESP_ERR_NO_MEM;
    }
    s_started = true;
    return ESP_OK;
}

bool phase5_motion_is_active(void)
{
    if (!atomic_load(&s_enabled)) return false;
    return now_ms() < atomic_load(&s_motion_until_ms);
}

void phase5_motion_set_enabled(bool enabled)
{
    bool was = atomic_exchange(&s_enabled, enabled);
    if (was != enabled) {
        ESP_LOGI(TAG, "motion detect %s", enabled ? "ENABLED" : "DISABLED");
        if (!enabled) {
            atomic_store(&s_motion_until_ms, 0);
        } else {
            /* Drop stale prev so the first comparison after re-enable
             * isn't against a frame from before the user paused. */
            atomic_store(&s_drop_prev, true);
        }
    }
}

bool phase5_motion_get_enabled(void)
{
    return atomic_load(&s_enabled);
}

void phase5_motion_set_event_handler(phase5_motion_event_cb_t cb)
{
    s_event_cb = cb;
}

float phase5_motion_seconds_since_last(void)
{
    int64_t last = atomic_load(&s_last_motion_ms);
    if (last < 0) return -1.0f;
    int64_t dt = now_ms() - last;
    if (dt < 0) dt = 0;
    return (float)dt / 1000.0f;
}

uint32_t phase5_motion_event_count(void)
{
    return atomic_load(&s_event_count);
}
