# xiao-esp32-s3-sense

Firmware for the Seeed Studio **XIAO ESP32-S3 Sense** (ESP32-S3 N8R8 + camera/mic/SD expansion).

This repo is phase-gated. The current execution contract lives in [`CLAUDE.md`](CLAUDE.md); humans should start there.

## Quick start

```bash
# 1. Source ESP-IDF (one-time per shell)
. ~/esp/esp-idf/export.sh

# 2. Build, flash, monitor
./scripts/flash.sh                  # uses /dev/cu.usbmodem1401 by default
./scripts/flash.sh /dev/cu.usbmodemXXXX  # override port
```

Exit `idf.py monitor` with **Ctrl-]**.

## Layout

```
.
├── CLAUDE.md              # phase-gated execution contract
├── docs/
│   ├── ARCHITECTURE.md
│   ├── PIN_MAP.md         # authoritative pin table (incl. Sense conflicts)
│   ├── POWER.md
│   └── RUNBOOK.md
├── firmware/              # ESP-IDF project root (idf.py -C firmware ...)
│   ├── CMakeLists.txt
│   ├── sdkconfig.defaults
│   ├── partitions.csv
│   ├── include/
│   │   ├── gpio_remap.h   # SINGLE source of truth for pins
│   │   └── system_config.h
│   └── main/
│       ├── CMakeLists.txt
│       └── main.c         # Phase 1 bring-up
├── host/                  # host-native tests (future)
├── scripts/flash.sh
├── tests/
└── tools/
```

## Hardware

- **Board:** XIAO ESP32-S3 Sense (N8R8 + Sense expansion)
- **MCU:** ESP32-S3, dual LX7 @ 240 MHz, 8 MB flash QIO, 8 MB Octal PSRAM
- **Console:** native USB-Serial/JTAG (no UART bridge)
- **Sense add-ons:** OV2640 camera (DVP), PDM MEMS mic, microSD slot

See [`docs/PIN_MAP.md`](docs/PIN_MAP.md) before wiring anything — the Sense SD card shares pins with the XIAO header SPI bus (D8/D9/D10).

## Status

| Phase | Title | State |
|---|---|---|
| 1 | Bring-up & sanity report | PASS |
| 2 | Camera bring-up (single JPEG capture) | PASS — OV3660 detected on this unit |
| 3 | PDM mic capture | PASS |
| 4 | microSD mount + log sink | PASS — SDMMC 1-bit, write/read 4 kB verified |
| 5.1 | Wi-Fi STA bring-up | PASS — `idf.py menuconfig` for creds, IP in ~2 s |
| 5.2 | HTTP MJPEG stream | PASS — 26 fps QVGA end-to-end |
| 5.3 | Motion detect + LED state machine | PASS — 5 Hz check, drift-compensated, hand-wave verified |
| 6.1 | Web UI redesign + status panel | PASS — single-page, status polling, pause/snapshot |
| 6.2 | Runtime camera + motion controls | PASS — frame size / quality / motion toggle from UI |
| 6.3 | MQTT publish on motion + NVS settings | PASS — UI broker config, motion publishes verified at broker |
