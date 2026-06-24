/*
 * Phase 1 — bring-up & sanity report for XIAO ESP32-S3 Sense.
 *
 * Goals:
 *   1. Print chip / flash / PSRAM identity on every boot.
 *   2. Fail loudly (ESP_LOGE) if reality disagrees with system_config.h.
 *   3. Heartbeat user LED on GPIO21 at 1 Hz so a power-only check
 *      can confirm the app is alive.
 *
 * Acceptance criteria are documented in CLAUDE.md §5.
 */

#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "driver/gpio.h"
#include "esp_chip_info.h"
#include "esp_flash.h"
#include "esp_log.h"
#include "esp_psram.h"
#include "esp_system.h"
#include "esp_private/esp_clk.h"

#include "gpio_remap.h"
#include "system_config.h"

#if SENSE_CAMERA_ENABLED
#include "phase2_camera.h"
#endif

#if SENSE_PDM_MIC_ENABLED
#include "phase3_mic.h"
#endif

#if SENSE_SD_ENABLED
#include "phase4_sd.h"
#endif

#if PHASE5_NET_ENABLED
#include "phase5_net.h"
#endif

#if PHASE5_STREAM_ENABLED
#include "phase5_cam_pump.h"
#include "phase5_http.h"
#endif

#if PHASE5_MOTION_ENABLED
#include "phase5_motion.h"
#include "phase5_led.h"
#endif

#if PHASE6_MQTT_ENABLED
#include "phase6_settings.h"
#include "phase6_mqtt.h"
/* Adapter: phase5_motion expects a void return; phase6_mqtt's publish
 * helper returns esp_err_t. Drop the err here. */
static void on_motion_event_publish(uint32_t count)
{
    (void)phase6_mqtt_publish_motion_event(count);
}
#endif

static const char *TAG = "sense_bringup";

/* ----------------------------------------------------------------------- */

static const char *reset_reason_str(esp_reset_reason_t r)
{
    switch (r) {
    case ESP_RST_POWERON:   return "POWERON";
    case ESP_RST_EXT:       return "EXT";
    case ESP_RST_SW:        return "SW";
    case ESP_RST_PANIC:     return "PANIC";
    case ESP_RST_INT_WDT:   return "INT_WDT";
    case ESP_RST_TASK_WDT:  return "TASK_WDT";
    case ESP_RST_WDT:       return "WDT";
    case ESP_RST_DEEPSLEEP: return "DEEPSLEEP";
    case ESP_RST_BROWNOUT:  return "BROWNOUT";
    case ESP_RST_SDIO:      return "SDIO";
    case ESP_RST_USB:       return "USB";
    case ESP_RST_JTAG:      return "JTAG";
    default:                return "UNKNOWN";
    }
}

static void log_features(uint32_t features)
{
    char buf[64];
    int n = 0;
    buf[0] = '\0';
    if (features & CHIP_FEATURE_WIFI_BGN) {
        n += snprintf(buf + n, sizeof(buf) - (size_t)n, "WIFI|");
    }
    if (features & CHIP_FEATURE_BT) {
        n += snprintf(buf + n, sizeof(buf) - (size_t)n, "BT|");
    }
    if (features & CHIP_FEATURE_BLE) {
        n += snprintf(buf + n, sizeof(buf) - (size_t)n, "BLE|");
    }
    if (features & CHIP_FEATURE_IEEE802154) {
        n += snprintf(buf + n, sizeof(buf) - (size_t)n, "802.15.4|");
    }
    if (n > 0 && buf[n - 1] == '|') {
        buf[n - 1] = '\0';
    }
    ESP_LOGI(TAG, "features=%s", buf[0] ? buf : "none");
}

static void report_identity(void)
{
    esp_chip_info_t info;
    esp_chip_info(&info);

    ESP_LOGI(TAG,
             "chip=ESP32-S3 rev=%d.%d cores=%u",
             (info.revision >> 8) & 0xFF,
             info.revision & 0xFF,
             (unsigned)info.cores);
    log_features(info.features);

    /* Flash */
    uint32_t flash_size = 0;
    if (esp_flash_get_size(NULL, &flash_size) == ESP_OK) {
        ESP_LOGI(TAG, "flash=%" PRIu32 " MB", flash_size / (1024U * 1024U));
        if (flash_size != BOARD_EXPECTED_FLASH_BYTES) {
            ESP_LOGE(TAG,
                     "flash size mismatch: got %" PRIu32 " expected %u",
                     flash_size,
                     BOARD_EXPECTED_FLASH_BYTES);
        }
    } else {
        ESP_LOGE(TAG, "esp_flash_get_size failed");
    }

    /* PSRAM */
#if CONFIG_SPIRAM
    size_t psram_size = esp_psram_get_size();
    ESP_LOGI(TAG, "psram=%u MB (octal)", (unsigned)(psram_size / (1024U * 1024U)));
    if (psram_size != BOARD_EXPECTED_PSRAM_BYTES) {
        ESP_LOGE(TAG,
                 "psram size mismatch: got %u expected %u",
                 (unsigned)psram_size,
                 BOARD_EXPECTED_PSRAM_BYTES);
    }
#else
    ESP_LOGW(TAG, "psram disabled in sdkconfig");
#endif

    /* CPU clock */
    int cpu_mhz = esp_clk_cpu_freq() / 1000000;
    ESP_LOGI(TAG, "cpu=%d MHz", cpu_mhz);
    if ((unsigned)cpu_mhz != BOARD_EXPECTED_CPU_MHZ) {
        ESP_LOGW(TAG, "cpu mhz unexpected: got %d expected %u", cpu_mhz, BOARD_EXPECTED_CPU_MHZ);
    }

    ESP_LOGI(TAG, "reset_reason=%s", reset_reason_str(esp_reset_reason()));
    ESP_LOGI(TAG, "%s ready", BOARD_NAME);
}

/* ----------------------------------------------------------------------- *
 * The Phase 1 inline LED helpers (led_init/led_set) and the inline
 * heartbeat loop in app_main were superseded by phase5_led.c when
 * PHASE5_MOTION_ENABLED was flipped on. When motion is disabled, a
 * simple inline heartbeat in app_main keeps the LED alive.
 * ----------------------------------------------------------------------- */

#if !PHASE5_MOTION_ENABLED
static void inline_led_init(void)
{
    gpio_config_t cfg = {
        .pin_bit_mask = 1ULL << BOARD_LED_GPIO,
        .mode         = GPIO_MODE_OUTPUT,
        .pull_up_en   = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&cfg));
    gpio_set_level(BOARD_LED_GPIO, BOARD_LED_ACTIVE_LOW ? 1 : 0);
}

static inline void inline_led_set(bool on)
{
    int level = BOARD_LED_ACTIVE_LOW ? !on : on;
    gpio_set_level(BOARD_LED_GPIO, level);
}
#endif

/* ----------------------------------------------------------------------- */

void app_main(void)
{
    report_identity();

#if BOARD_LED_ENABLED && !PHASE5_MOTION_ENABLED
    inline_led_init();
#endif

#if SENSE_CAMERA_ENABLED
    (void)phase2_camera_capture_one();   /* Phase 2 smoke test; logs result */
#endif

#if SENSE_PDM_MIC_ENABLED
    (void)phase3_mic_capture_one();      /* Phase 3 smoke test; logs result */
#endif

#if SENSE_SD_ENABLED
    (void)phase4_sd_capture_one();       /* Phase 4 smoke test; logs result */
#endif

#if PHASE5_NET_ENABLED
    esp_err_t net_err = phase5_net_start_blocking();   /* Phase 5.1 Wi-Fi STA */
#else
    esp_err_t net_err = ESP_ERR_INVALID_STATE;
#endif

#if PHASE6_MQTT_ENABLED
    /* Open NVS-backed settings. Must come before cam_pump / motion /
     * mqtt so they pick up the operator's last-known-good config. */
    ESP_ERROR_CHECK(phase6_settings_init());
#endif

#if PHASE5_STREAM_ENABLED
    if (net_err == ESP_OK) {
        ESP_ERROR_CHECK(phase5_cam_pump_start());      /* Phase 5.2 camera pump */
        ESP_ERROR_CHECK(phase5_http_start());          /* Phase 5.2 HTTP server */
    } else {
        ESP_LOGE(TAG, "skipping Phase 5.2 — Wi-Fi not up (net_err=0x%x)", net_err);
    }
#endif

#if PHASE5_MOTION_ENABLED
    ESP_ERROR_CHECK(phase5_motion_start());            /* Phase 5.3 motion detect */
    ESP_ERROR_CHECK(phase5_led_start());               /* Phase 5.3 LED state machine */
#endif

#if PHASE6_MQTT_ENABLED
    if (net_err == ESP_OK) {
        ESP_ERROR_CHECK(phase6_mqtt_init());           /* Phase 6.3 MQTT client */
#if PHASE5_MOTION_ENABLED
        phase5_motion_set_event_handler(on_motion_event_publish);
#endif
    } else {
        ESP_LOGE(TAG, "skipping Phase 6.3 — Wi-Fi not up");
    }
#endif
    (void)net_err;

#if !PHASE5_MOTION_ENABLED
    /* Fallback inline heartbeat (no motion task running). */
    const TickType_t period = pdMS_TO_TICKS(HEARTBEAT_PERIOD_MS / 2);
    uint32_t tick = 0;
    bool led_on = false;
    while (true) {
        led_on = !led_on;
#if BOARD_LED_ENABLED
        inline_led_set(led_on);
#endif
        if (led_on) {
            tick++;
            ESP_LOGI(TAG, "heartbeat tick=%" PRIu32, tick);
        }
        vTaskDelay(period);
    }
#else
    /* phase5_led_start spawned its own task; let app_main return.
     * IDF's main task self-deletes on return per default config. */
#endif
}
