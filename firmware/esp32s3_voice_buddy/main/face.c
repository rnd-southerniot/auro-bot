#include "face.h"

#include <string.h>

#include "board_pins.h"
#include "driver/ledc.h"
#include "driver/spi_master.h"
#include "esp_heap_caps.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"
#include "esp_lcd_panel_vendor.h"

// RGB565 helpers
#define RGB(r, g, b) ((uint16_t)((((r) & 0xF8) << 8) | (((g) & 0xFC) << 3) | ((b) >> 3)))
// ST7789 wants byte-swapped pixels over SPI.
#define SW(c) ((uint16_t)(((c) >> 8) | ((c) << 8)))

static esp_lcd_panel_handle_t s_panel = NULL;
static uint16_t *s_fb = NULL;  // 240x240 framebuffer in PSRAM

static void bl_init(void) {
    ledc_timer_config_t t = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .duty_resolution = LEDC_TIMER_8_BIT,
        .timer_num = LEDC_TIMER_0,
        .freq_hz = 5000,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ledc_timer_config(&t);
    ledc_channel_config_t c = {
        .gpio_num = LCD_PIN_BL,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = LEDC_CHANNEL_0,
        .timer_sel = LEDC_TIMER_0,
        .duty = 200,  // ~80%
        .hpoint = 0,
    };
    ledc_channel_config(&c);
}

static void fill(uint16_t color) {
    uint16_t v = SW(color);
    for (int i = 0; i < LCD_W * LCD_H; ++i) s_fb[i] = v;
}

static void fill_rect(int x, int y, int w, int h, uint16_t color) {
    uint16_t v = SW(color);
    for (int yy = y; yy < y + h; ++yy) {
        if (yy < 0 || yy >= LCD_H) continue;
        for (int xx = x; xx < x + w; ++xx) {
            if (xx < 0 || xx >= LCD_W) continue;
            s_fb[yy * LCD_W + xx] = v;
        }
    }
}

static void blit(void) {
    esp_lcd_panel_draw_bitmap(s_panel, 0, 0, LCD_W, LCD_H, s_fb);
}

void face_init(void) {
    bl_init();

    spi_bus_config_t bus = {
        .sclk_io_num = LCD_PIN_SCK,
        .mosi_io_num = LCD_PIN_MOSI,
        .miso_io_num = LCD_PIN_MISO,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = LCD_W * LCD_H * 2 + 16,
    };
    spi_bus_initialize(LCD_SPI_HOST, &bus, SPI_DMA_CH_AUTO);

    esp_lcd_panel_io_handle_t io = NULL;
    esp_lcd_panel_io_spi_config_t io_cfg = {
        .dc_gpio_num = LCD_PIN_DC,
        .cs_gpio_num = LCD_PIN_CS,
        .pclk_hz = LCD_SPI_HZ,
        .lcd_cmd_bits = 8,
        .lcd_param_bits = 8,
        .spi_mode = 0,
        .trans_queue_depth = 10,
    };
    esp_lcd_new_panel_io_spi((esp_lcd_spi_bus_handle_t)LCD_SPI_HOST, &io_cfg, &io);

    esp_lcd_panel_dev_config_t panel_cfg = {
        .reset_gpio_num = LCD_PIN_RST,
        .rgb_ele_order = LCD_RGB_ELEMENT_ORDER_RGB,
        .bits_per_pixel = 16,
    };
    esp_lcd_new_panel_st7789(io, &panel_cfg, &s_panel);
    esp_lcd_panel_reset(s_panel);
    esp_lcd_panel_init(s_panel);
    esp_lcd_panel_invert_color(s_panel, true);  // ST7789 panels usually need this
    // 240x240 ST7789 often needs a small gap; tune on the bench if shifted.
    esp_lcd_panel_set_gap(s_panel, 0, 0);
    esp_lcd_panel_disp_on_off(s_panel, true);

    s_fb = heap_caps_malloc(LCD_W * LCD_H * 2, MALLOC_CAP_SPIRAM);
    if (!s_fb) s_fb = heap_caps_malloc(LCD_W * LCD_H * 2, MALLOC_CAP_DEFAULT);

    face_set(FACE_IDLE);
}

// Draw two eyes + a mouth; color/shape vary by state. Minimal but reactive —
// the rich character/GIF face (reusing my-Claude-buddy assets) is a later polish.
void face_set(face_state_t st) {
    if (!s_fb) return;
    uint16_t bg = RGB(0, 0, 0);
    uint16_t eye = RGB(0, 220, 255);  // cyan
    int eye_w = 46, eye_h = 60, eye_y = 80;
    int mouth_w = 70, mouth_h = 10, mouth_y = 175;
    uint16_t mouth = RGB(0, 220, 255);

    switch (st) {
        case FACE_LISTENING:  eye = RGB(0, 255, 120); eye_h = 70; break;        // green, wide
        case FACE_THINKING:   eye = RGB(255, 210, 0); eye_y = 70; eye_h = 40; break;  // amber, up
        case FACE_SPEAKING:   eye = RGB(0, 220, 255); mouth_h = 34; break;      // open mouth
        case FACE_DRIVING:    eye = RGB(120, 180, 255); break;
        case FACE_HALTED:     bg = RGB(60, 0, 0); eye = RGB(255, 40, 40); mouth = RGB(255, 40, 40); break;
        case FACE_LOW_BATTERY:eye = RGB(255, 120, 0); break;
        case FACE_IDLE:
        default: break;
    }

    fill(bg);
    fill_rect(60 - eye_w / 2, eye_y, eye_w, eye_h, eye);            // left eye
    fill_rect(180 - eye_w / 2, eye_y, eye_w, eye_h, eye);           // right eye
    fill_rect(120 - mouth_w / 2, mouth_y, mouth_w, mouth_h, mouth); // mouth
    blit();
}

// Diagnostic: red screen with `code` white vertical bars (serial is our blind
// spot, so the screen reports a fault code — e.g. link_init's failure bitmask).
void face_error(int code) {
    if (!s_fb) return;
    fill(RGB(120, 0, 0));
    int n = code < 1 ? 1 : (code > 8 ? 8 : code);
    for (int i = 0; i < n; ++i) {
        fill_rect(20 + i * 26, 95, 16, 50, RGB(255, 255, 255));
    }
    blit();
}

face_state_t face_state_from_str(const char *s) {
    if (!s) return FACE_IDLE;
    if (!strcmp(s, "listening")) return FACE_LISTENING;
    if (!strcmp(s, "thinking")) return FACE_THINKING;
    if (!strcmp(s, "speaking")) return FACE_SPEAKING;
    if (!strcmp(s, "driving")) return FACE_DRIVING;
    if (!strcmp(s, "halted")) return FACE_HALTED;
    if (!strcmp(s, "low_battery")) return FACE_LOW_BATTERY;
    return FACE_IDLE;
}
