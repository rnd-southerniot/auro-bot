# POWER — xiao-esp32-s3-sense

## Rails

| Rail | Source | Nominal | Tolerance | Owner |
|---|---|---|---|---|
| 5 V (VBUS) | USB-C or BAT charger boost | 5.0 V | 4.75–5.25 V | host PC / charger IC |
| 3V3 | on-board LDO from 5 V | 3.30 V | ±3 % | XIAO module |
| VDD_CPU | internal regulator | 1.1 V (DVS) | — | ESP32-S3 silicon |
| VDD_SPI | from 3V3, fused 3.3 V | 3.30 V | — | flash + Octal PSRAM |

## Current budget (typical, room temperature)

| Mode | Current @ 5 V | Notes |
|---|---|---|
| Active CPU + Wi-Fi RX idle | 80–120 mA | observed on bare XIAO |
| Active + Wi-Fi TX (ESP_PWR_MAX) | 240 mA peak | brief, during TX bursts |
| Camera streaming + Wi-Fi | 200–280 mA | OV2640 active, QVGA |
| Light sleep | 1–2 mA | RAM retained |
| Deep sleep, RTC retention | ~14 µA | per Espressif datasheet |

> Bench-supply current limit for first-flash and bring-up: **500 mA**. Well above the 280 mA worst case observed on the Sense and below the magic-smoke threshold of typical USB-C cables.

## Brownout

- ESP-IDF brownout detector enabled, default threshold (~2.44 V on VDD_CPU).
- On brownout: HW reset → boot log shows `RTCWDT_BROWN_OUT_RESET` (ESP-IDF reports `ESP_RST_BROWNOUT`).
- Phase 1 firmware logs the reset reason on every boot to make brownouts visible without instrumentation.

## Battery (BAT pad)

- The XIAO has a Li-ion charge IC. Charge current ≈ 100 mA (per Seeed schematic).
- **Do not** simultaneously feed 5 V externally and connect a battery to BAT — the charger IC and the USB VBUS path will fight.
- Charge LED (yellow) is hard-wired and not under MCU control.

## Power-down ordering (mechanical handling)

1. Stop the application (`idf.py monitor` → Ctrl-]).
2. Unplug USB-C.
3. Only then unmate the FFC or remove the SD card.

Hot-swapping the FFC under power has caused brown-outs on similar Sense units in the field.
