// ESP32-S3 Voice Buddy — app entry.
//
// P1 bring-up: ST7789 face + CDC-serial link to the Pi + I2S mic/speaker.
// The mic streams 20 ms PCM frames to the Pi; TTS frames from the Pi play on the
// speaker; FACE messages drive the face. With the Pi in loopback mode this gives
// the mic->Pi->speaker echo + face control of the /navbot:buddy-link-test gate.
// On-device wake word / AFE / offline "stop" (esp-sr) arrive in P2.

#include <string.h>

#include "audio.h"
#include "board_pins.h"
#include "cJSON.h"
#include "face.h"
#include "freertos/FreeRTOS.h"
#include "freertos/stream_buffer.h"
#include "freertos/task.h"
#include "link.h"

static StreamBufferHandle_t s_tts_sb;  // PCM bytes from Pi -> speaker
static volatile bool s_audio_ok = false;

static void on_frame(uint8_t type, const uint8_t *payload, uint16_t len) {
    switch (type) {
        case T_AUDIO_TTS:
            xStreamBufferSend(s_tts_sb, payload, len, 0);  // copy; never blocks RX
            break;
        case T_AUDIO_TTS_END:
            audio_spk_flush();
            break;
        case T_FACE: {
            cJSON *j = cJSON_ParseWithLength((const char *)payload, len);
            if (j) {
                cJSON *st = cJSON_GetObjectItem(j, "state");
                if (cJSON_IsString(st)) face_set(face_state_from_str(st->valuestring));
                cJSON_Delete(j);
            }
            break;
        }
        case T_HELLO:
            link_send_json(T_HELLO, "{\"role\":\"buddy\",\"fw\":\"voice-v0\",\"proto_ver\":1}");
            break;
        case T_PING:
            link_send(T_PONG, NULL, 0);
            break;
        default:
            break;  // T_CMD (volume/brightness) handled later
    }
}

static void mic_task(void *arg) {
    (void)arg;
    static int16_t buf[AUDIO_FRAME_SAMPLES];
    for (;;) {
        int n = audio_mic_read(buf, AUDIO_FRAME_SAMPLES);
        if (n > 0) {
            link_send(T_AUDIO_MIC, (const uint8_t *)buf, (uint16_t)(n * 2));
        } else {
            vTaskDelay(pdMS_TO_TICKS(2));
        }
    }
}

static void spk_task(void *arg) {
    (void)arg;
    static int16_t frame[AUDIO_FRAME_SAMPLES];
    for (;;) {
        // Non-blocking: play TTS if present, else feed a silence frame. This keeps
        // the I2S TX continuously fed at real-time pace so an idle speaker never
        // underruns and drones the last buffer (i2s write blocks ~one frame).
        size_t got = xStreamBufferReceive(s_tts_sb, frame, sizeof(frame), 0);
        if (got >= 2) {
            audio_spk_write(frame, (int)(got / 2));
        } else {
            audio_spk_flush();
        }
    }
}

static void status_task(void *arg) {
    (void)arg;
    for (;;) {
        link_send_json(T_STATUS, s_audio_ok ? "{\"fw\":\"voice-v0\",\"step\":\"running\",\"audio\":true}"
                                            : "{\"fw\":\"voice-v0\",\"step\":\"running\",\"audio\":false}");
        vTaskDelay(pdMS_TO_TICKS(2000));
    }
}

// Link-first, self-diagnosing bring-up: the Pi sees the buddy and step-tagged
// STATUS even if a peripheral init hangs/fails, so we can localize the fault
// (the console is off UART0, so the link is our only telemetry).
void app_main(void) {
    s_tts_sb = xStreamBufferCreate(16 * 1024, 1);

    int link_err = link_init(on_frame);
    link_send_json(T_HELLO, "{\"role\":\"buddy\",\"fw\":\"voice-v0\",\"proto_ver\":1}");
    link_send_json(T_STATUS, "{\"step\":\"link_up\"}");
    xTaskCreatePinnedToCore(status_task, "status", 3072, NULL, 5, NULL, 0);

    face_init();
    if (link_err) {
        face_error(link_err);  // serial is the blind spot: report on-screen
    }
    link_send_json(T_STATUS, "{\"step\":\"face_ok\"}");

    audio_init();
    s_audio_ok = true;
    link_send_json(T_STATUS, "{\"step\":\"audio_ok\"}");

    if (!link_err) face_set(FACE_IDLE);
    xTaskCreatePinnedToCore(spk_task, "spk", 4096, NULL, 11, NULL, 1);
    xTaskCreatePinnedToCore(mic_task, "mic", 4096, NULL, 10, NULL, 1);
}
