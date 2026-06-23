#include "link.h"

#include <string.h>

#include "board_pins.h"
#include "driver/uart.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define MAGIC0 0xA5
#define MAGIC1 0x5A
#define MAX_PAYLOAD 1024            // >= 640 (audio) with margin
#define ACC_SIZE (MAX_PAYLOAD + 64)

static link_frame_cb_t s_cb = NULL;
static uint8_t s_seq = 0;
static uint8_t s_acc[ACC_SIZE];
static size_t s_acc_len = 0;
static portMUX_TYPE s_tx_mux = portMUX_INITIALIZER_UNLOCKED;

uint16_t link_crc16(const uint8_t *data, size_t len) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; ++i) {
        crc ^= (uint16_t)data[i] << 8;
        for (int b = 0; b < 8; ++b) {
            crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
        }
    }
    return crc;
}

void link_send(uint8_t type, const uint8_t *payload, uint16_t len) {
    if (len > MAX_PAYLOAD) return;
    // Per-call (stack) buffer so concurrent senders (mic/status/rx tasks) never
    // corrupt a shared buffer; uart_write_bytes is atomic per call.
    uint8_t frame[ACC_SIZE + 8];
    // header: type, seq, len_lo, len_hi, payload...
    taskENTER_CRITICAL(&s_tx_mux);
    uint8_t seq = s_seq++;
    taskEXIT_CRITICAL(&s_tx_mux);
    size_t n = 0;
    uint8_t hdr[4] = {type, seq, (uint8_t)(len & 0xFF), (uint8_t)((len >> 8) & 0xFF)};
    // crc over hdr+payload
    uint16_t crc = link_crc16(hdr, 4);
    // continue crc over payload
    {
        uint16_t c = crc;
        for (uint16_t i = 0; i < len; ++i) {
            c ^= (uint16_t)payload[i] << 8;
            for (int b = 0; b < 8; ++b) c = (c & 0x8000) ? (uint16_t)((c << 1) ^ 0x1021) : (uint16_t)(c << 1);
        }
        crc = c;
    }
    frame[n++] = MAGIC0;
    frame[n++] = MAGIC1;
    memcpy(frame + n, hdr, 4); n += 4;
    if (len) { memcpy(frame + n, payload, len); n += len; }
    frame[n++] = (uint8_t)(crc & 0xFF);
    frame[n++] = (uint8_t)((crc >> 8) & 0xFF);
    uart_write_bytes(LINK_UART_NUM, (const char *)frame, n);
}

void link_send_json(uint8_t type, const char *json) {
    link_send(type, (const uint8_t *)json, (uint16_t)strlen(json));
}

// Try to extract one frame from the accumulator; returns true if it made progress.
static bool extract_one(void) {
    // find magic
    size_t i = 0;
    for (; i + 1 < s_acc_len; ++i) {
        if (s_acc[i] == MAGIC0 && s_acc[i + 1] == MAGIC1) break;
    }
    if (i + 1 >= s_acc_len) {
        // no magic; keep last byte if it could be MAGIC0
        if (s_acc_len && s_acc[s_acc_len - 1] == MAGIC0) {
            s_acc[0] = MAGIC0; s_acc_len = 1;
        } else {
            s_acc_len = 0;
        }
        return false;
    }
    if (i > 0) { memmove(s_acc, s_acc + i, s_acc_len - i); s_acc_len -= i; }
    if (s_acc_len < 6) return false;             // need header
    uint16_t len = s_acc[4] | ((uint16_t)s_acc[5] << 8);
    if (len > MAX_PAYLOAD) {                      // bogus; drop magic and rescan
        memmove(s_acc, s_acc + 1, s_acc_len - 1); s_acc_len -= 1; return true;
    }
    size_t total = 2 + 4 + len + 2;
    if (s_acc_len < total) return false;          // wait for rest
    uint16_t crc_rx = s_acc[6 + len] | ((uint16_t)s_acc[7 + len] << 8);
    if (link_crc16(s_acc + 2, 4 + len) != crc_rx) {
        memmove(s_acc, s_acc + 1, s_acc_len - 1); s_acc_len -= 1; return true;  // resync
    }
    if (s_cb) s_cb(s_acc[2], s_acc + 6, len);
    memmove(s_acc, s_acc + total, s_acc_len - total); s_acc_len -= total;
    return true;
}

static void rx_task(void *arg) {
    (void)arg;
    uint8_t tmp[512];
    for (;;) {
        int r = uart_read_bytes(LINK_UART_NUM, tmp, sizeof(tmp), pdMS_TO_TICKS(20));
        if (r > 0) {
            if (s_acc_len + (size_t)r > ACC_SIZE) s_acc_len = 0;  // overflow -> resync
            memcpy(s_acc + s_acc_len, tmp, r);
            s_acc_len += r;
            while (extract_one()) { /* drain */ }
        }
    }
}

int link_init(link_frame_cb_t cb) {
    s_cb = cb;
    int err = 0;
    uart_config_t cfg = {
        .baud_rate = LINK_BAUD,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    if (uart_driver_install(LINK_UART_NUM, 8192, 8192, 0, NULL, 0) != ESP_OK) err |= 1;
    if (uart_param_config(LINK_UART_NUM, &cfg) != ESP_OK) err |= 2;
    // EXPLICITLY route U0TXD/U0RXD — with console=NONE the pins are otherwise
    // left as low GPIOs and nothing reaches the CH343 bridge.
    if (uart_set_pin(LINK_UART_NUM, LINK_PIN_TX, LINK_PIN_RX,
                     UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE) != ESP_OK) err |= 4;
    xTaskCreatePinnedToCore(rx_task, "link_rx", 4096, NULL, 12, NULL, 1);
    return err;
}
