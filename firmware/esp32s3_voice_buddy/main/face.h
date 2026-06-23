#pragma once

typedef enum {
    FACE_IDLE = 0,
    FACE_LISTENING,
    FACE_THINKING,
    FACE_SPEAKING,
    FACE_DRIVING,
    FACE_HALTED,
    FACE_LOW_BATTERY,
} face_state_t;

void         face_init(void);                 // SPI + ST7789 + backlight
void         face_set(face_state_t st);       // redraw for a state
void         face_error(int code);            // red screen + `code` white bars (diag)
face_state_t face_state_from_str(const char *s);
