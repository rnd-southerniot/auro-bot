#pragma once
#include <stdint.h>

// I2S mic (INMP441) + speaker (MAX98357A), both 16 kHz / 16-bit mono.
void audio_init(void);

// Read up to max_samples int16 mono samples from the mic. Returns count read.
int  audio_mic_read(int16_t *out, int max_samples);

// Write samples int16 mono samples to the speaker (blocks until queued).
void audio_spk_write(const int16_t *pcm, int samples);

// Push silence / drain (used on TTS end).
void audio_spk_flush(void);
