#pragma once
#include <stdbool.h>
#include <stdint.h>

// On-device speech: AFE (noise-suppress + VAD) -> WakeNet wake word + MultiNet
// commands. Owns the I2S mic. esp-sr runs on core 1.
typedef enum {
    SR_EVT_WAKE = 0,  // wake word detected ("Jarvis")
    SR_EVT_STOP,      // safety command "stop" / "halt"
    SR_EVT_IDLE,      // awake window ended with no command (back to listening for wake)
} sr_event_t;

typedef void (*sr_event_cb_t)(sr_event_t evt);
// AFE-enhanced audio delivered while awake (post-wake), for streaming to the Pi (STT).
typedef void (*sr_audio_cb_t)(const int16_t *pcm, int samples);

// Start the SR task. Returns false if models are missing (link/face still work).
bool sr_start(sr_event_cb_t on_event, sr_audio_cb_t on_audio);
