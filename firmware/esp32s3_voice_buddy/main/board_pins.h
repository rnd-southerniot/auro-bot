#pragma once
// Pin map for the ESP32-S3-WROOM-1-N16R8 Claude Buddy board.
// Source: my-Claude-buddy/HARDWARE_PROFILE.md (Arif-verified).

// ---- Pi link: UART0 is wired to the CH343 USB bridge ----
#define LINK_UART_NUM        0
#define LINK_BAUD            1000000      // 1 Mbps (see PROTOCOL.md)
// UART0 TXD=GPIO43 / RXD=GPIO44 on the S3 module; CH343 uses these. Must be set
// EXPLICITLY: with CONFIG_ESP_CONSOLE_NONE the app leaves U0TXD unrouted (GPIO
// low) otherwise, so nothing reaches the bridge.
#define LINK_PIN_TX          43
#define LINK_PIN_RX          44

// ---- ST7789V2 LCD (SPI2/FSPI, 240x240, write-only) ----
#define LCD_SPI_HOST         SPI2_HOST
#define LCD_PIN_SCK          21
#define LCD_PIN_MOSI         47
#define LCD_PIN_MISO         -1
#define LCD_PIN_CS           41
#define LCD_PIN_DC           40
#define LCD_PIN_RST          45
#define LCD_PIN_BL           42           // LEDC PWM backlight
#define LCD_W                240
#define LCD_H                240
#define LCD_SPI_HZ           (40 * 1000 * 1000)

// ---- INMP441 microphone (I2S0 RX, 16 kHz / 16-bit mono) ----
#define MIC_I2S_PORT         I2S_NUM_0
#define MIC_PIN_WS           4
#define MIC_PIN_BCK          5
#define MIC_PIN_DIN          6

// ---- MAX98357A speaker (I2S1 TX, 16 kHz / 16-bit mono) ----
#define SPK_I2S_PORT         I2S_NUM_1
#define SPK_PIN_BCK          15
#define SPK_PIN_LRC          16
#define SPK_PIN_DOUT         7

// ---- Buttons (active LOW, button-to-GND) ----
#define BTN_VOLP             39
#define BTN_VOLN             38
#define BTN_BOOT             0            // PTT / optional

// ---- Audio format ----
#define AUDIO_SAMPLE_RATE    16000
#define AUDIO_FRAME_SAMPLES  320          // 20 ms @ 16 kHz
#define AUDIO_FRAME_BYTES    (AUDIO_FRAME_SAMPLES * 2)  // 16-bit = 640 bytes
