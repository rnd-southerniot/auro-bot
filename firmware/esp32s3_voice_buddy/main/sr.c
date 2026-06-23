#include "sr.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>

#include "audio.h"
#include "link.h"
#include "esp_afe_config.h"
#include "esp_afe_sr_iface.h"
#include "esp_afe_sr_models.h"
#include "esp_mn_iface.h"
#include "esp_mn_models.h"
#include "esp_mn_speech_commands.h"
#include "esp_wn_iface.h"
#include "esp_wn_models.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "model_path.h"

static sr_event_cb_t s_evt;
static sr_audio_cb_t s_audio;

static void sr_task(void *arg) {
    (void)arg;
    char msg[160];
    srmodel_list_t *models = esp_srmodel_init("model");  // the "model" flash partition
    char *wn = models ? esp_srmodel_filter(models, ESP_WN_PREFIX, NULL) : NULL;
    char *mn = models ? esp_srmodel_filter(models, ESP_MN_PREFIX, ESP_MN_ENGLISH) : NULL;
    snprintf(msg, sizeof(msg), "{\"sr\":\"models\",\"wn\":\"%s\",\"mn\":\"%s\"}",
             wn ? wn : "null", mn ? mn : "null");
    link_send_json(T_STATUS, msg);
    if (!wn || !mn) {
        link_send_json(T_STATUS, "{\"sr\":\"no_models\"}");
        vTaskDelete(NULL);  // models missing -> SR disabled; link/face/speaker still work
        return;
    }

    // AFE: single mic ("M"), SR pipeline, low-cost. No AEC (no reference channel),
    // no SE (multi-mic only); WebRTC NS + VAD on; WakeNet on.
    afe_config_t *cfg = afe_config_init("M", models, AFE_TYPE_SR, AFE_MODE_LOW_COST);
    cfg->aec_init = false;
    cfg->se_init = false;
    cfg->vad_init = true;
    cfg->wakenet_init = true;
    cfg->wakenet_model_name = wn;
    cfg->wakenet_mode = DET_MODE_90;   // more sensitive detection mode
    cfg->afe_perferred_core = 1;
    afe_config_check(cfg);
    const esp_afe_sr_iface_t *afe = esp_afe_handle_from_config(cfg);
    esp_afe_sr_data_t *afe_data = afe->create_from_config(cfg);
    afe_config_free(cfg);
    // Lower the wake threshold so a normal-volume "Jarvis" triggers (default ~0.5).
    if (afe->set_wakenet_threshold) afe->set_wakenet_threshold(afe_data, 1, 0.4f);

    // MultiNet command recognizer + register "stop"/"halt".
    esp_mn_iface_t *mnet = esp_mn_handle_from_name(mn);
    model_iface_data_t *mn_data = mnet->create(mn, 5000);  // 5 s detection window
    esp_mn_commands_alloc(mnet, mn_data);
    esp_mn_commands_clear();
    esp_mn_commands_add(1, "stop");
    esp_mn_commands_add(2, "halt");
    esp_mn_commands_update();

    int chunk = afe->get_feed_chunksize(afe_data);
    int16_t *feed = malloc(sizeof(int16_t) * chunk);
    if (!feed) {
        link_send_json(T_STATUS, "{\"sr\":\"oom\"}");
        vTaskDelete(NULL);
        return;
    }
    snprintf(msg, sizeof(msg), "{\"sr\":\"ready\",\"chunk\":%d}", chunk);
    link_send_json(T_STATUS, msg);

    bool awake = false;
    int rep = 0, peak = 0;
    for (;;) {
        int got = 0;
        while (got < chunk) {
            int n = audio_mic_read(feed + got, chunk - got);
            if (n > 0) got += n;
        }
        afe->feed(afe_data, feed);
        afe_fetch_result_t *r = afe->fetch(afe_data);
        if (!r || r->ret_value == -1) continue;

        // diagnostic: report VAD + audio RMS over the link (console is off)
        {
            int n2 = r->data_size / (int)sizeof(int16_t);
            int64_t acc = 0;  // 64-bit: v*v over a chunk overflows 32-bit 'long' on ESP32
            for (int i = 0; i < n2; i++) { int v = r->data[i]; acc += (int64_t)v * v; }
            int rms = n2 ? (int)sqrtf((float)acc / n2) : 0;
            if (rms > peak) peak = rms;
            if (++rep >= 100) {
                snprintf(msg, sizeof(msg),
                         "{\"sr\":\"run\",\"vad\":%d,\"rms\":%d,\"awake\":%d}",
                         (int)r->vad_state, peak, awake ? 1 : 0);
                link_send_json(T_STATUS, msg);
                rep = 0;
                peak = 0;
            }
        }

        if (!awake) {
            if (r->wakeup_state == WAKENET_DETECTED) {
                awake = true;
                mnet->clean(mn_data);          // start a fresh command window
                if (s_evt) s_evt(SR_EVT_WAKE);
            }
            continue;
        }

        // Awake window: stream enhanced audio to the Pi (STT) AND watch locally
        // for the "stop"/"halt" safety command.
        if (s_audio) s_audio(r->data, r->data_size / (int)sizeof(int16_t));

        esp_mn_state_t st = mnet->detect(mn_data, r->data);
        if (st == ESP_MN_STATE_DETECTED) {
            esp_mn_results_t *res = mnet->get_results(mn_data);
            if (res->num > 0 && (res->command_id[0] == 1 || res->command_id[0] == 2)) {
                if (s_evt) s_evt(SR_EVT_STOP);
            }
            awake = false;                      // window done
        } else if (st == ESP_MN_STATE_TIMEOUT) {
            awake = false;                      // no command within the window
            if (s_evt) s_evt(SR_EVT_IDLE);
        }
    }
}

bool sr_start(sr_event_cb_t on_event, sr_audio_cb_t on_audio) {
    s_evt = on_event;
    s_audio = on_audio;
    // esp-sr needs a deep stack; pin to core 1 with the audio work.
    return xTaskCreatePinnedToCore(sr_task, "sr", 8 * 1024, NULL, 6, NULL, 1) == pdPASS;
}
