/*
 * Phase 5.3 — LED state machine.
 *
 * Trivially simple: each iteration reads the motion atomic and picks a
 * half-period. Pattern can switch mid-cycle (we only re-check at toggle
 * boundaries) so worst-case visual lag is one half-period (≤ 500 ms).
 *
 * GPIO is active-low; macros from gpio_remap.h.
 */

#include "phase5_led.h"

#include <stdbool.h>

#include "driver/gpio.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "gpio_remap.h"
#include "phase5_motion.h"

static const char *TAG = "sense_led";

#define LED_HEARTBEAT_HALF_MS  500    /* 1 Hz */
#define LED_FAST_HALF_MS       100    /* 5 Hz */
#define LED_TASK_STACK         2048

static bool s_started;

static inline void led_set(bool on)
{
    int level = BOARD_LED_ACTIVE_LOW ? !on : on;
    gpio_set_level(BOARD_LED_GPIO, level);
}

static void led_task(void *arg)
{
    (void)arg;

    gpio_config_t cfg = {
        .pin_bit_mask = 1ULL << BOARD_LED_GPIO,
        .mode         = GPIO_MODE_OUTPUT,
        .pull_up_en   = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&cfg));
    led_set(false);

    ESP_LOGI(TAG, "LED task started, gpio=%d active_low=%d "
                  "heartbeat=%d ms fast=%d ms",
             BOARD_LED_GPIO, BOARD_LED_ACTIVE_LOW,
             LED_HEARTBEAT_HALF_MS, LED_FAST_HALF_MS);

    bool on = false;
    while (true) {
        bool fast = phase5_motion_is_active();
        int half_ms = fast ? LED_FAST_HALF_MS : LED_HEARTBEAT_HALF_MS;
        on = !on;
        led_set(on);
        vTaskDelay(pdMS_TO_TICKS(half_ms));
    }
}

esp_err_t phase5_led_start(void)
{
    if (s_started) return ESP_ERR_INVALID_STATE;
    BaseType_t ok = xTaskCreate(led_task, "led", LED_TASK_STACK, NULL,
                                /* prio */ 2, NULL);
    if (ok != pdPASS) return ESP_ERR_NO_MEM;
    s_started = true;
    return ESP_OK;
}
