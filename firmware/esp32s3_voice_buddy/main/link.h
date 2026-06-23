#pragma once
#include <stddef.h>
#include <stdint.h>

// Wire protocol message types — must match firmware/.../PROTOCOL.md and the
// Pi-side navbot_voice_io/protocol.py.
#define T_HELLO         0x01
#define T_PING          0x02
#define T_PONG          0x03
#define T_AUDIO_MIC     0x10
#define T_AUDIO_TTS     0x11
#define T_AUDIO_TTS_END 0x12
#define T_EVENT         0x20
#define T_FACE          0x30
#define T_STATUS        0x31
#define T_CMD           0x40
#define PROTO_VER       1

// Called from the link RX task for each decoded frame. Keep it short / non-blocking.
typedef void (*link_frame_cb_t)(uint8_t type, const uint8_t *payload, uint16_t len);

// Configures UART0 + starts the RX task. Returns 0 on success, or a bitmask of
// failed steps: 1=driver_install, 2=param_config, 4=set_pin (for face diag).
int      link_init(link_frame_cb_t cb);
void     link_send(uint8_t type, const uint8_t *payload, uint16_t len);
void     link_send_json(uint8_t type, const char *json);
uint16_t link_crc16(const uint8_t *data, size_t len);  // CRC-16/CCITT-FALSE
