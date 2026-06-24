/*
 * Phase 3 — PDM microphone single-shot capture.
 *
 * Hardware: digital MEMS mic on the Sense daughterboard.
 *   CLK  = GPIO42  (I²S WS/CLK out)
 *   DATA = GPIO41  (PDM bitstream in)
 *
 * The mic is mono-left (WS high → left). At sensor power-up the AGC takes
 * a few hundred ms to settle, so we discard the first ~250 ms of samples
 * before measuring. With the mic placed on a quiet desk we typically see:
 *   peak  ≈   200–2000 LSB  (16-bit signed full-scale = 32767)
 *   rms   ≈    20–300  LSB
 *   dc    ≈ -100..+100 LSB  (varies; subtracted before RMS)
 *
 * Smoke gate (all must hold):
 *   - i2s_channel_read returns the requested byte count
 *   - peak >= MIN_PEAK_LSB                (rules out dead mic / no clock)
 *   - rms  >= MIN_RMS_LSB                 (rules out DC-only / stuck)
 *   - rms  <= MAX_REASONABLE_RMS_LSB      (rules out clipping / config error)
 */

#include "phase3_mic.h"

#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "driver/i2s_pdm.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "gpio_remap.h"

static const char *TAG = "sense_mic";

#define SAMPLE_RATE_HZ          16000
#define BITS_PER_SAMPLE         16
#define WARMUP_MS               250
#define CAPTURE_MS              1000
#define READ_TIMEOUT_MS         2000

#define MIN_PEAK_LSB            50      /* dead mic threshold */
#define MIN_RMS_LSB             3       /* DC-only / stuck threshold */
#define MAX_REASONABLE_RMS_LSB  20000   /* clip / config-bug threshold */

static size_t samples_for_ms(int ms)
{
    return (size_t)((SAMPLE_RATE_HZ * (uint32_t)ms) / 1000U);
}

esp_err_t phase3_mic_capture_one(void)
{
    i2s_chan_handle_t rx_handle = NULL;

    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
    /* Auto-allocate DMA buffers; defaults are fine for 16 kHz mono. */
    esp_err_t err = i2s_new_channel(&chan_cfg, NULL, &rx_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "i2s_new_channel: 0x%x (%s)", err, esp_err_to_name(err));
        return err;
    }

    i2s_pdm_rx_config_t pdm_cfg = {
        .clk_cfg  = I2S_PDM_RX_CLK_DEFAULT_CONFIG(SAMPLE_RATE_HZ),
        .slot_cfg = I2S_PDM_RX_SLOT_DEFAULT_CONFIG(
            I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO),
        .gpio_cfg = {
            .clk = PDM_MIC_CLK_GPIO,
            .din = PDM_MIC_DATA_GPIO,
            .invert_flags = { .clk_inv = false },
        },
    };

    err = i2s_channel_init_pdm_rx_mode(rx_handle, &pdm_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "i2s_channel_init_pdm_rx_mode: 0x%x (%s)", err, esp_err_to_name(err));
        i2s_del_channel(rx_handle);
        return err;
    }

    err = i2s_channel_enable(rx_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "i2s_channel_enable: 0x%x (%s)", err, esp_err_to_name(err));
        i2s_del_channel(rx_handle);
        return err;
    }

    ESP_LOGI(TAG, "I²S PDM RX init OK: clk=%d din=%d sr=%d Hz fmt=s16 mono",
             PDM_MIC_CLK_GPIO, PDM_MIC_DATA_GPIO, SAMPLE_RATE_HZ);

    /* --- Warm-up: drain WARMUP_MS worth of samples and discard. --- */
    const size_t warmup_samples = samples_for_ms(WARMUP_MS);
    const size_t warmup_bytes   = warmup_samples * sizeof(int16_t);
    int16_t *warmup_buf = heap_caps_malloc(warmup_bytes, MALLOC_CAP_8BIT);
    if (warmup_buf == NULL) {
        ESP_LOGE(TAG, "warmup buf alloc (%u B) failed", (unsigned)warmup_bytes);
        err = ESP_ERR_NO_MEM;
        goto cleanup;
    }
    size_t got = 0;
    (void)i2s_channel_read(rx_handle, warmup_buf, warmup_bytes, &got,
                           pdMS_TO_TICKS(READ_TIMEOUT_MS));
    free(warmup_buf);

    /* --- Real capture. --- */
    const size_t n_samples   = samples_for_ms(CAPTURE_MS);
    const size_t buf_bytes   = n_samples * sizeof(int16_t);
    int16_t *buf = heap_caps_malloc(buf_bytes, MALLOC_CAP_8BIT);
    if (buf == NULL) {
        ESP_LOGE(TAG, "capture buf alloc (%u B) failed", (unsigned)buf_bytes);
        err = ESP_ERR_NO_MEM;
        goto cleanup;
    }

    int64_t t0 = esp_timer_get_time();
    err = i2s_channel_read(rx_handle, buf, buf_bytes, &got,
                           pdMS_TO_TICKS(READ_TIMEOUT_MS));
    int64_t cap_ms = (esp_timer_get_time() - t0) / 1000;

    if (err != ESP_OK || got != buf_bytes) {
        ESP_LOGE(TAG, "i2s_channel_read: err=0x%x got=%u expected=%u",
                 err, (unsigned)got, (unsigned)buf_bytes);
        free(buf);
        err = (err != ESP_OK) ? err : ESP_FAIL;
        goto cleanup;
    }

    /* --- Statistics. --- */
    int64_t  sum    = 0;
    uint64_t sum_sq = 0;
    int16_t  peak   = 0;
    bool     all_zero = true;

    for (size_t i = 0; i < n_samples; ++i) {
        int16_t s = buf[i];
        if (s != 0) all_zero = false;
        sum += s;
        if (s == INT16_MIN) s = INT16_MIN + 1;   /* abs() overflow guard */
        int16_t a = (int16_t)((s < 0) ? -s : s);
        if (a > peak) peak = a;
    }
    int32_t mean = (int32_t)(sum / (int64_t)n_samples);
    for (size_t i = 0; i < n_samples; ++i) {
        int32_t d = (int32_t)buf[i] - mean;
        sum_sq += (uint64_t)(d * d);
    }
    double rms = sqrt((double)sum_sq / (double)n_samples);

    ESP_LOGI(TAG,
             "captured n=%u t=%" PRId64 " ms  dc=%" PRId32 " peak=%" PRId16
             " rms=%.1f  first4=%" PRId16 ",%" PRId16 ",%" PRId16 ",%" PRId16,
             (unsigned)n_samples, cap_ms, mean, peak, rms,
             buf[0], buf[1], buf[2], buf[3]);

    if (all_zero) {
        ESP_LOGE(TAG, "all-zero buffer — mic dead / no clock / bad pinout");
        err = ESP_FAIL;
    } else if (peak < MIN_PEAK_LSB) {
        ESP_LOGE(TAG, "peak %" PRId16 " below floor %d — mic likely dead",
                 peak, MIN_PEAK_LSB);
        err = ESP_FAIL;
    } else if (rms < MIN_RMS_LSB) {
        ESP_LOGE(TAG, "rms %.1f below floor %d — DC-only / stuck",
                 rms, MIN_RMS_LSB);
        err = ESP_FAIL;
    } else if (rms > MAX_REASONABLE_RMS_LSB) {
        ESP_LOGE(TAG, "rms %.1f above ceiling %d — clipping / wrong config",
                 rms, MAX_REASONABLE_RMS_LSB);
        err = ESP_FAIL;
    } else {
        ESP_LOGI(TAG, "PDM mic capture PASS");
        err = ESP_OK;
    }

    free(buf);

cleanup:
    (void)i2s_channel_disable(rx_handle);
    (void)i2s_del_channel(rx_handle);
    return err;
}
