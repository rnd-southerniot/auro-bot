/*
 * Phase 6.3 — NVS settings.
 *
 * NVS is already initialised by phase5_net_start_blocking (which calls
 * nvs_flash_init). This module just owns a single read-write handle into
 * a project-specific namespace and exposes typed get/set wrappers.
 */

#include "phase6_settings.h"

#include <stdint.h>
#include <string.h>

#include "esp_log.h"
#include "nvs.h"

static const char *TAG = "sense_settings";
static const char *NS  = "siot_p6";

static nvs_handle_t s_h;
static bool         s_open;

esp_err_t phase6_settings_init(void)
{
    if (s_open) return ESP_OK;
    esp_err_t err = nvs_open(NS, NVS_READWRITE, &s_h);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "nvs_open(%s): 0x%x (%s)", NS, err, esp_err_to_name(err));
        return err;
    }
    s_open = true;
    ESP_LOGI(TAG, "NVS namespace '%s' open", NS);
    return ESP_OK;
}

esp_err_t phase6_settings_get_str(const char *key, char *out, size_t maxlen, const char *def)
{
    if (!s_open || key == NULL || out == NULL || maxlen == 0) return ESP_ERR_INVALID_STATE;
    size_t len = maxlen;
    esp_err_t err = nvs_get_str(s_h, key, out, &len);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        size_t n = (def != NULL) ? strlen(def) : 0;
        if (n >= maxlen) n = maxlen - 1;
        if (n > 0) memcpy(out, def, n);
        out[n] = '\0';
        return ESP_OK;
    }
    return err;
}

esp_err_t phase6_settings_set_str(const char *key, const char *val)
{
    if (!s_open || key == NULL || val == NULL) return ESP_ERR_INVALID_STATE;
    esp_err_t err = nvs_set_str(s_h, key, val);
    if (err == ESP_OK) err = nvs_commit(s_h);
    return err;
}

int phase6_settings_get_int(const char *key, int def)
{
    if (!s_open || key == NULL) return def;
    int32_t v;
    if (nvs_get_i32(s_h, key, &v) == ESP_OK) return (int)v;
    return def;
}

esp_err_t phase6_settings_set_int(const char *key, int val)
{
    if (!s_open || key == NULL) return ESP_ERR_INVALID_STATE;
    esp_err_t err = nvs_set_i32(s_h, key, (int32_t)val);
    if (err == ESP_OK) err = nvs_commit(s_h);
    return err;
}

bool phase6_settings_get_bool(const char *key, bool def)
{
    if (!s_open || key == NULL) return def;
    uint8_t v;
    if (nvs_get_u8(s_h, key, &v) == ESP_OK) return v != 0;
    return def;
}

esp_err_t phase6_settings_set_bool(const char *key, bool val)
{
    if (!s_open || key == NULL) return ESP_ERR_INVALID_STATE;
    esp_err_t err = nvs_set_u8(s_h, key, val ? 1u : 0u);
    if (err == ESP_OK) err = nvs_commit(s_h);
    return err;
}
