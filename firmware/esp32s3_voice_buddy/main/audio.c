#include "audio.h"

#include "board_pins.h"
#include "driver/i2s_std.h"
#include "freertos/FreeRTOS.h"

static i2s_chan_handle_t s_rx = NULL;  // mic
static i2s_chan_handle_t s_tx = NULL;  // speaker

void audio_init(void) {
    // ---- Mic: INMP441 on I2S0 (RX). Read 32-bit slots; downshift to 16-bit.
    i2s_chan_config_t rx_cfg = I2S_CHANNEL_DEFAULT_CONFIG(MIC_I2S_PORT, I2S_ROLE_MASTER);
    i2s_new_channel(&rx_cfg, NULL, &s_rx);
    i2s_std_config_t rx_std = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(AUDIO_SAMPLE_RATE),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_MONO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = MIC_PIN_BCK,
            .ws = MIC_PIN_WS,
            .dout = I2S_GPIO_UNUSED,
            .din = MIC_PIN_DIN,
            .invert_flags = {0},
        },
    };
    // INMP441 puts its data in the left slot.
    rx_std.slot_cfg.slot_mask = I2S_STD_SLOT_LEFT;
    i2s_channel_init_std_mode(s_rx, &rx_std);
    i2s_channel_enable(s_rx);

    // ---- Speaker: MAX98357A on I2S1 (TX), 16-bit mono.
    i2s_chan_config_t tx_cfg = I2S_CHANNEL_DEFAULT_CONFIG(SPK_I2S_PORT, I2S_ROLE_MASTER);
    i2s_new_channel(&tx_cfg, &s_tx, NULL);
    i2s_std_config_t tx_std = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(AUDIO_SAMPLE_RATE),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = SPK_PIN_BCK,
            .ws = SPK_PIN_LRC,
            .dout = SPK_PIN_DOUT,
            .din = I2S_GPIO_UNUSED,
            .invert_flags = {0},
        },
    };
    i2s_channel_init_std_mode(s_tx, &tx_std);
    i2s_channel_enable(s_tx);
}

int audio_mic_read(int16_t *out, int max_samples) {
    // Read 32-bit slots and downshift. INMP441 is 24-bit in a 32-bit slot;
    // >>16 yields a usable 16-bit sample (tune the shift for gain on the bench).
    static int32_t buf32[AUDIO_FRAME_SAMPLES];
    int want = max_samples < AUDIO_FRAME_SAMPLES ? max_samples : AUDIO_FRAME_SAMPLES;
    size_t bytes_read = 0;
    if (i2s_channel_read(s_rx, buf32, want * sizeof(int32_t), &bytes_read, pdMS_TO_TICKS(100)) != ESP_OK) {
        return 0;
    }
    int n = (int)(bytes_read / sizeof(int32_t));
    for (int i = 0; i < n; ++i) {
        // INMP441 is 24-bit MSB-aligned in a 32-bit slot. >>16 was too quiet for
        // WakeNet; >>13 (~8x) is the sweet spot — >>12 clips loud speech and hurts
        // WakeNet. Saturate so loud speech doesn't wrap.
        int32_t v = buf32[i] >> 13;
        if (v > 32767) v = 32767;
        else if (v < -32768) v = -32768;
        out[i] = (int16_t)v;
    }
    return n;
}

void audio_spk_write(const int16_t *pcm, int samples) {
    size_t written = 0;
    i2s_channel_write(s_tx, pcm, samples * sizeof(int16_t), &written, pdMS_TO_TICKS(200));
}

void audio_spk_flush(void) {
    static const int16_t silence[AUDIO_FRAME_SAMPLES] = {0};
    size_t w = 0;
    i2s_channel_write(s_tx, silence, sizeof(silence), &w, pdMS_TO_TICKS(50));
}
