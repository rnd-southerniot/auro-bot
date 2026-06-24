/*
 * Phase 5.1 — Wi-Fi STA bring-up.
 *
 * Standard IDF idiom: init NVS → init esp_netif/event-loop → create
 * default STA netif → init esp_wifi → set mode STA → set config from
 * Kconfig → start. Event handler does esp_wifi_connect() on
 * WIFI_EVENT_STA_START and re-tries up to CONFIG_WIFI_MAX_RETRY on
 * disconnect. IP_EVENT_STA_GOT_IP raises a bit in the event group;
 * the public entry point blocks on that bit (with a timeout).
 */

#include "phase5_net.h"

#include <inttypes.h>
#include <string.h>

#include "esp_err.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "nvs_flash.h"

#include "sdkconfig.h"

static const char *TAG = "sense_net";

#define BIT_GOT_IP    BIT0
#define BIT_FAIL      BIT1

static EventGroupHandle_t s_event_group;
static int                s_retry_count;

static void on_wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg;
    (void)data;
    if (base != WIFI_EVENT) return;

    switch (id) {
    case WIFI_EVENT_STA_START:
        ESP_LOGI(TAG, "WIFI_EVENT_STA_START → esp_wifi_connect()");
        esp_wifi_connect();
        break;

    case WIFI_EVENT_STA_DISCONNECTED:
        if (s_retry_count < CONFIG_WIFI_MAX_RETRY) {
            s_retry_count++;
            ESP_LOGW(TAG, "disconnected; retry %d/%d", s_retry_count, CONFIG_WIFI_MAX_RETRY);
            vTaskDelay(pdMS_TO_TICKS(500));   /* small backoff */
            esp_wifi_connect();
        } else {
            ESP_LOGE(TAG, "disconnected; exhausted %d retries", CONFIG_WIFI_MAX_RETRY);
            xEventGroupSetBits(s_event_group, BIT_FAIL);
        }
        break;

    default:
        break;
    }
}

static void on_ip_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg;
    if (base != IP_EVENT || id != IP_EVENT_STA_GOT_IP) return;

    const ip_event_got_ip_t *evt = (const ip_event_got_ip_t *)data;
    ESP_LOGI(TAG, "got IP: " IPSTR ", gw=" IPSTR ", mask=" IPSTR,
             IP2STR(&evt->ip_info.ip),
             IP2STR(&evt->ip_info.gw),
             IP2STR(&evt->ip_info.netmask));
    s_retry_count = 0;
    xEventGroupSetBits(s_event_group, BIT_GOT_IP);
}

esp_err_t phase5_net_start_blocking(void)
{
    if (CONFIG_WIFI_SSID[0] == '\0') {
        ESP_LOGE(TAG, "CONFIG_WIFI_SSID is empty — run `idf.py menuconfig` "
                      "→ Phase 5 → Wi-Fi SSID");
        return ESP_ERR_INVALID_ARG;
    }

    /* --- NVS (Wi-Fi calibration / cred cache lives here) --- */
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "NVS partition needs erase: 0x%x", err);
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);

    /* --- netif + event loop + default STA --- */
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_t *sta = esp_netif_create_default_wifi_sta();
    (void)sta;

    s_event_group = xEventGroupCreate();
    if (s_event_group == NULL) return ESP_ERR_NO_MEM;
    s_retry_count = 0;

    /* --- Wi-Fi driver init --- */
    wifi_init_config_t init_cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init_cfg));

    esp_event_handler_instance_t any_wifi, got_ip;
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT, ESP_EVENT_ANY_ID, on_wifi_event, NULL, &any_wifi));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        IP_EVENT, IP_EVENT_STA_GOT_IP, on_ip_event, NULL, &got_ip));

    wifi_config_t wifi_cfg = { 0 };
    strncpy((char *)wifi_cfg.sta.ssid,     CONFIG_WIFI_SSID,
            sizeof(wifi_cfg.sta.ssid) - 1);
    strncpy((char *)wifi_cfg.sta.password, CONFIG_WIFI_PASSWORD,
            sizeof(wifi_cfg.sta.password) - 1);
    wifi_cfg.sta.threshold.authmode = WIFI_AUTH_OPEN;
    wifi_cfg.sta.pmf_cfg.capable    = true;
    wifi_cfg.sta.pmf_cfg.required   = false;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_cfg));
    ESP_LOGI(TAG, "wifi_init done, connecting to \"%s\"", CONFIG_WIFI_SSID);
    ESP_ERROR_CHECK(esp_wifi_start());

    /* --- block on event group --- */
    EventBits_t bits = xEventGroupWaitBits(
        s_event_group,
        BIT_GOT_IP | BIT_FAIL,
        pdFALSE,                           /* don't clear on exit */
        pdFALSE,                           /* any of the bits */
        pdMS_TO_TICKS(CONFIG_WIFI_CONNECT_TIMEOUT_MS));

    if (bits & BIT_GOT_IP) {
        wifi_ap_record_t ap = { 0 };
        if (esp_wifi_sta_get_ap_info(&ap) == ESP_OK) {
            ESP_LOGI(TAG, "associated: bssid=" MACSTR " channel=%u rssi=%d dBm",
                     MAC2STR(ap.bssid), ap.primary, ap.rssi);
        }
        return ESP_OK;
    }
    if (bits & BIT_FAIL) {
        ESP_LOGE(TAG, "wifi connect failed (retries exhausted)");
        return ESP_FAIL;
    }
    ESP_LOGE(TAG, "wifi connect timed out after %d ms",
             CONFIG_WIFI_CONNECT_TIMEOUT_MS);
    return ESP_ERR_TIMEOUT;
}
