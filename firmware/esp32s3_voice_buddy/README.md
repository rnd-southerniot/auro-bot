# esp32s3_voice_buddy

Firmware for the **ESP32-S3 voice buddy** — the robot's hands-free voice + face
front-end. It is the **ears, mouth, and face**; the robot's Pi is the brain,
eyes (camera), and motion. Connected to the Pi over **USB-serial (CH343 →
UART0)** using the framed protocol in [PROTOCOL.md](PROTOCOL.md).

Board: **ESP32-S3-WROOM-1-N16R8** (pins in `main/board_pins.h`, from
`my-Claude-buddy/HARDWARE_PROFILE.md`): ST7789 240×240 LCD, INMP441 mic,
MAX98357A speaker, three buttons.

## Scope (this firmware = P1 bring-up)

- ST7789 **animated face** (state-driven eyes/mouth; rich character/GIF face is a
  later polish that reuses the `my-Claude-buddy/characters/` assets).
- **Pi link**: framed control + 16 kHz/16-bit PCM audio over UART0 @ 1 Mbps.
- **I²S mic** streamed up; **I²S speaker** plays TTS frames from the Pi.

Not yet (P2): on-device WakeNet wake word + AFE (VAD/AEC) + offline "stop" via
`esp-sr`. The mic currently streams continuously; P2 adds wake-gating.

## Build & flash (on the Mac, where the board lives)

This is a PlatformIO **ESP-IDF** project (uses your existing `pio` toolchain):

```bash
cd esp32s3_voice_buddy
pio device list                       # find the board's /dev/cu.usbmodemXXXX
# set upload_port in platformio.ini (or pass --upload-port)
pio run -e claude-buddy-voice -t upload
```

> **Console note:** the IDF console is moved **off UART0** (sdkconfig
> `ESP_CONSOLE_NONE`) because UART0 *is* the binary Pi link. So `pio device
> monitor` won't show logs. For early display/audio debugging, temporarily set
> `CONFIG_ESP_CONSOLE_UART_DEFAULT=y` (accepting log noise on the link), or watch
> the face on-screen.

## Pair with the Pi (the `buddy-link-test` gate)

Plug the flashed board into the robot Pi, then on the Pi:

```bash
ros2 launch navbot_voice_io voice_io.launch.py loopback:=true
ros2 topic pub --once /buddy/face std_msgs/String "{data: listening}"
# speak at the buddy -> your phrase echoes from its speaker (mic->Pi->speaker),
# and the face switches to the 'listening' look.
```

## Status: v0 — expect a build-iterate pass

This was authored without an on-hand IDF toolchain; the **wire framing is
verified byte-identical to the Pi side** (`link.c` ↔ `navbot_voice_io/protocol.py`),
but the IDF driver calls (`i2s_std`, `esp_lcd` ST7789, LEDC) may need small fixes
for your exact IDF version on first `pio run`. Bring up in this order and tune as
needed: **face → link/loopback → mic levels (INMP441 shift) → speaker volume**.
