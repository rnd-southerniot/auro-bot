/*
 * Phase 6.3 — esp-mqtt client wrapper.
 *
 * The client is owned here, NVS-backed config lives in phase6_settings.
 * On boot, init() loads the config and starts the client iff enabled.
 * /control mutations call apply_config(), which restarts the client
 * with the new params (or shuts it down if disabled).
 *
 * Motion publish is wired by main.c via
 *   phase5_motion_set_event_handler(phase6_mqtt_publish_motion_event);
 * The callback runs on the motion task; we only call esp_mqtt_client_publish
 * (non-blocking, queues to esp-mqtt's internal task) so that's safe.
 */

#include "phase6_mqtt.h"

#include <inttypes.h>
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>

#include "esp_err.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "mqtt_client.h"

#include "phase6_settings.h"

static const char *TAG = "sense_mqtt";

/* Bounded sizes for cached config (we re-read NVS into these on every
 * apply_config). Keep modest; matches what the UI accepts. */
#define URI_LEN    160
#define TOPIC_LEN  128
#define USER_LEN   64
#define PASS_LEN   64

static esp_mqtt_client_handle_t s_client;
static _Atomic int              s_state          = PHASE6_MQTT_DISABLED;
static _Atomic uint32_t         s_publish_count;
static char                     s_topic[TOPIC_LEN] = "siot/xiao-esp32s3-sense/motion";
static int                      s_qos            = 0;
static bool                     s_retain         = false;

/* In-place URL-decode (percent-decoding + '+'→space). Defensive against
 * legacy NVS values stored before phase5_http added url_decode at the
 * /control entry point. Idempotent on clean ASCII. */
static void url_decode_inplace(char *s)
{
    if (s == NULL) return;
    char *r = s, *w = s;
    while (*r != '\0') {
        if (r[0] == '%' && r[1] != '\0' && r[2] != '\0') {
            char h1 = r[1], h2 = r[2];
            int hi = (h1 >= '0' && h1 <= '9') ? h1 - '0'
                   : (h1 >= 'A' && h1 <= 'F') ? h1 - 'A' + 10
                   : (h1 >= 'a' && h1 <= 'f') ? h1 - 'a' + 10 : -1;
            int lo = (h2 >= '0' && h2 <= '9') ? h2 - '0'
                   : (h2 >= 'A' && h2 <= 'F') ? h2 - 'A' + 10
                   : (h2 >= 'a' && h2 <= 'f') ? h2 - 'a' + 10 : -1;
            if (hi >= 0 && lo >= 0) {
                *w++ = (char)((hi << 4) | lo);
                r += 3;
                continue;
            }
        }
        if (*r == '+') { *w++ = ' '; r++; continue; }
        *w++ = *r++;
    }
    *w = '\0';
}

static bool uri_looks_like_mqtt(const char *s)
{
    if (s == NULL) return false;
    return strncmp(s, "mqtt://",  7) == 0
        || strncmp(s, "mqtts://", 8) == 0
        || strncmp(s, "ws://",    5) == 0
        || strncmp(s, "wss://",   6) == 0;
}

static void on_mqtt_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg; (void)base; (void)data;
    switch ((esp_mqtt_event_id_t)id) {
    case MQTT_EVENT_CONNECTED:
        atomic_store(&s_state, PHASE6_MQTT_CONNECTED);
        ESP_LOGI(TAG, "broker CONNECTED");
        break;
    case MQTT_EVENT_DISCONNECTED:
        atomic_store(&s_state, PHASE6_MQTT_CONNECTING);   /* esp-mqtt auto-reconnects */
        ESP_LOGW(TAG, "broker DISCONNECTED (will retry)");
        break;
    case MQTT_EVENT_ERROR:
        atomic_store(&s_state, PHASE6_MQTT_ERROR);
        ESP_LOGE(TAG, "broker ERROR");
        break;
    case MQTT_EVENT_PUBLISHED:
        ESP_LOGD(TAG, "publish acked");
        break;
    default:
        break;
    }
}

static void stop_client(void)
{
    if (s_client != NULL) {
        esp_mqtt_client_stop(s_client);
        esp_mqtt_client_destroy(s_client);
        s_client = NULL;
    }
}

esp_err_t phase6_mqtt_apply_config(const char *uri,
                                   const char *user,
                                   const char *pass,
                                   const char *topic,
                                   int qos, bool retain, bool enabled)
{
    /* Always tear down first; we'll reconnect with fresh params if enabled. */
    stop_client();

    /* Cache topic / qos / retain regardless (used at publish time). */
    if (topic != NULL && topic[0] != '\0') {
        strlcpy(s_topic, topic, sizeof(s_topic));
    }
    s_qos    = (qos < 0 || qos > 2) ? 0 : qos;
    s_retain = retain;

    if (!enabled) {
        atomic_store(&s_state, PHASE6_MQTT_DISABLED);
        ESP_LOGI(TAG, "client disabled");
        return ESP_OK;
    }
    if (uri == NULL || uri[0] == '\0') {
        atomic_store(&s_state, PHASE6_MQTT_DISABLED);
        ESP_LOGW(TAG, "enable requested but uri is empty");
        return ESP_ERR_INVALID_ARG;
    }
    if (!uri_looks_like_mqtt(uri)) {
        atomic_store(&s_state, PHASE6_MQTT_ERROR);
        ESP_LOGE(TAG, "URI '%s' is not a valid mqtt[s]:// or ws[s]:// URL — "
                      "refusing to start client (would panic esp-mqtt)", uri);
        return ESP_ERR_INVALID_ARG;
    }

    esp_mqtt_client_config_t cfg = { 0 };
    cfg.broker.address.uri               = uri;
    cfg.credentials.username             = (user != NULL && user[0] != '\0') ? user : NULL;
    cfg.credentials.authentication.password = (pass != NULL && pass[0] != '\0') ? pass : NULL;

    s_client = esp_mqtt_client_init(&cfg);
    if (s_client == NULL) {
        atomic_store(&s_state, PHASE6_MQTT_ERROR);
        ESP_LOGE(TAG, "esp_mqtt_client_init failed");
        return ESP_FAIL;
    }
    esp_err_t err = esp_mqtt_client_register_event(s_client, ESP_EVENT_ANY_ID, on_mqtt_event, NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "register_event: 0x%x", err);
        stop_client();
        atomic_store(&s_state, PHASE6_MQTT_ERROR);
        return err;
    }

    atomic_store(&s_state, PHASE6_MQTT_CONNECTING);
    err = esp_mqtt_client_start(s_client);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "client_start: 0x%x", err);
        stop_client();
        atomic_store(&s_state, PHASE6_MQTT_ERROR);
        return err;
    }
    ESP_LOGI(TAG, "client starting → %s (topic=%s qos=%d retain=%d user=%s)",
             uri, s_topic, s_qos, retain ? 1 : 0,
             (user != NULL && user[0]) ? user : "(none)");
    return ESP_OK;
}

esp_err_t phase6_mqtt_init(void)
{
    char uri  [URI_LEN]   = { 0 };
    char user [USER_LEN]  = { 0 };
    char pass [PASS_LEN]  = { 0 };
    char topic[TOPIC_LEN] = { 0 };

    phase6_settings_get_str ("mqtt_uri",   uri,   sizeof(uri),   "");
    phase6_settings_get_str ("mqtt_user",  user,  sizeof(user),  "");
    phase6_settings_get_str ("mqtt_pass",  pass,  sizeof(pass),  "");
    phase6_settings_get_str ("mqtt_topic", topic, sizeof(topic), "siot/xiao-esp32s3-sense/motion");
    int  qos     = phase6_settings_get_int ("mqtt_qos",    0);
    bool retain  = phase6_settings_get_bool("mqtt_retain", false);
    bool enabled = phase6_settings_get_bool("mqtt_en",     false);

    /* Heal legacy NVS values that pre-date the /control url_decode fix. */
    url_decode_inplace(uri);
    url_decode_inplace(user);
    url_decode_inplace(pass);
    url_decode_inplace(topic);

    /* If the URI was malformed (neither URL-encoded nor a plain
     * mqtt[s]:// URL), don't even try to enable — write the cleaned
     * version back so future boots are clean, and continue with the
     * client disabled. The user can re-edit in /control. */
    if (enabled && !uri_looks_like_mqtt(uri)) {
        ESP_LOGW(TAG, "stored URI '%s' invalid; disabling MQTT until "
                      "operator re-saves a valid mqtt[s]:// URL", uri);
        phase6_settings_set_bool("mqtt_en", false);
        enabled = false;
    } else {
        /* Persist cleaned-up strings so /status reflects truth. */
        phase6_settings_set_str("mqtt_uri",   uri);
        phase6_settings_set_str("mqtt_user",  user);
        phase6_settings_set_str("mqtt_pass",  pass);
        phase6_settings_set_str("mqtt_topic", topic);
    }

    return phase6_mqtt_apply_config(uri, user, pass, topic, qos, retain, enabled);
}

esp_err_t phase6_mqtt_publish_motion_event(uint32_t event_count)
{
    if (atomic_load(&s_state) != PHASE6_MQTT_CONNECTED || s_client == NULL) {
        return ESP_ERR_INVALID_STATE;
    }
    char payload[160];
    int n = snprintf(payload, sizeof(payload),
        "{\"event\":\"motion\",\"count\":%" PRIu32
        ",\"uptime_s\":%" PRId64 "}",
        event_count,
        esp_timer_get_time() / 1000000);
    int msg_id = esp_mqtt_client_publish(s_client, s_topic, payload, n, s_qos, s_retain ? 1 : 0);
    if (msg_id < 0) {
        ESP_LOGW(TAG, "publish failed");
        return ESP_FAIL;
    }
    atomic_fetch_add(&s_publish_count, 1);
    ESP_LOGI(TAG, "published motion #%" PRIu32 " (msg_id=%d, %d B)", event_count, msg_id, n);
    return ESP_OK;
}

esp_err_t phase6_mqtt_publish_test(void)
{
    if (atomic_load(&s_state) != PHASE6_MQTT_CONNECTED || s_client == NULL) {
        return ESP_ERR_INVALID_STATE;
    }
    char payload[128];
    int n = snprintf(payload, sizeof(payload),
        "{\"event\":\"test\",\"uptime_s\":%" PRId64 "}",
        esp_timer_get_time() / 1000000);
    int msg_id = esp_mqtt_client_publish(s_client, s_topic, payload, n, s_qos, s_retain ? 1 : 0);
    if (msg_id < 0) return ESP_FAIL;
    atomic_fetch_add(&s_publish_count, 1);
    ESP_LOGI(TAG, "published test (msg_id=%d, %d B)", msg_id, n);
    return ESP_OK;
}

phase6_mqtt_state_t phase6_mqtt_state(void)
{
    return (phase6_mqtt_state_t)atomic_load(&s_state);
}

const char *phase6_mqtt_state_name(void)
{
    switch (phase6_mqtt_state()) {
    case PHASE6_MQTT_DISABLED:   return "disabled";
    case PHASE6_MQTT_CONNECTING: return "connecting";
    case PHASE6_MQTT_CONNECTED:  return "connected";
    case PHASE6_MQTT_ERROR:      return "error";
    }
    return "?";
}

uint32_t phase6_mqtt_publish_count(void)
{
    return atomic_load(&s_publish_count);
}
