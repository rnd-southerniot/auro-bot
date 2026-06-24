# PIN_MAP — xiao-esp32-s3-sense

**Authoritative.** All firmware pin macros must reference `firmware/include/gpio_remap.h`, which mirrors this table. Any disagreement between code and this document is a bug.

Sources:
- Seeed Studio wiki — XIAO ESP32-S3 / XIAO ESP32-S3 Sense getting-started guide.
- ESP32-S3 datasheet & TRM (Espressif).

---

## 1. XIAO header (bare board)

The XIAO module exposes 11 user pins (D0–D10) plus power. Internal-only pins (USB D+/D-, flash/PSRAM) are not listed.

| Silk | GPIO | ADC | Touch | Default alt | Notes |
|---|---|---|---|---|---|
| 3V3 | — | — | — | 3.3 V out | LDO regulated |
| GND | — | — | — | — | |
| 5V (VBUS) | — | — | — | 5 V in/out | tied to USB VBUS |
| BAT | — | — | — | Li-ion +tve | charger IC: hold-on, ≤500 mA |
| D0 / A0 | 1 | ADC1_CH0 | T1 | GPIO | |
| D1 / A1 | 2 | ADC1_CH1 | T2 | GPIO | |
| D2 / A2 | 3 | ADC1_CH2 | T3 | GPIO | strapping (boot) — drive carefully |
| D3 / A3 | 4 | ADC1_CH3 | T4 | GPIO | |
| D4 / SDA | 5 | ADC1_CH4 | T5 | I²C0 SDA | |
| D5 / SCL | 6 | ADC1_CH5 | T6 | I²C0 SCL | |
| D6 / TX | 43 | — | — | UART0 TX | |
| D7 / RX | 44 | — | — | UART0 RX | |
| D8 / SCK | 7 | — | — | SPI2 SCK | **shared with Sense SD CLK** |
| D9 / MISO | 8 | — | — | SPI2 MISO | **shared with Sense SD D0** |
| D10 / MOSI | 9 | — | — | SPI2 MOSI | **shared with Sense SD CMD** |

**On-board (not on header)**

| Function | GPIO | Polarity | Notes |
|---|---|---|---|
| User LED ("L", orange) | 21 | active **LOW** | drive LOW to light |
| Charge LED (yellow) | — | — | hard-wired to charger IC, not MCU-controllable |
| BOOT button | 0 | strapping | held LOW at reset → ROM bootloader |
| RESET button | EN | — | hardware reset |

**Strapping pins** (do not drive externally during reset): GPIO0, GPIO3, GPIO45, GPIO46. GPIO3 = D2 — keep it floating or weakly biased through reset if used as input.

---

## 2. Sense expansion

The Sense daughterboard adds an OV2640 camera, a digital PDM MEMS microphone, and a microSD slot. It is connected to the XIAO via the FFC and the underside B-side pads (GPIO11–18, 38–48).

### 2.1 Camera (DVP 8-bit)

> **Sensor on this unit:** OV3660 (PID `0x3660`, I²C addr `0x3C`), detected at runtime. The Seeed wiki currently documents OV2640 for older Sense revisions; newer units ship with OV3660 (3 MP). The `espressif/esp32-camera` component supports both transparently. Pin map below is identical for either sensor.


| Function | GPIO |
|---|---|
| XCLK | 10 |
| SIOD (SCCB SDA) | 40 |
| SIOC (SCCB SCL) | 39 |
| VSYNC | 38 |
| HREF | 47 |
| PCLK | 13 |
| Y2 (D0) | 15 |
| Y3 (D1) | 17 |
| Y4 (D2) | 18 |
| Y5 (D3) | 16 |
| Y6 (D4) | 14 |
| Y7 (D5) | 12 |
| Y8 (D6) | 11 |
| Y9 (D7) | 48 |
| PWDN | not connected |
| RESET | not connected (tied via board) |

### 2.2 PDM microphone (MSM261D3526H1CPM or equivalent)

| Function | GPIO |
|---|---|
| CLK (WS) | 42 |
| DATA | 41 |

Configure as I²S RX in PDM mode. WS = high → left channel; this mic is mono-left.

### 2.3 microSD (SDMMC 1-bit)

| Function | GPIO | XIAO header conflict |
|---|---|---|
| CLK | 7 | **D8 / SPI2 SCK** |
| CMD | 9 | **D10 / SPI2 MOSI** |
| D0 | 8 | **D9 / SPI2 MISO** |

> ⚠ **Conflict rule:** SD and external SPI on D8/D9/D10 are mutually exclusive. `gpio_remap.h` enforces this at compile time. If a future phase needs both, multiplex via FSPI bus on a different pin set or use SD over SPI mode with a CS sourced from a free GPIO and accept the bus contention only when SD is idle.

---

## 3. Free pins after full Sense use

With camera + PDM mic + SDMMC in use, the only remaining XIAO header pins available for the application are:

| Silk | GPIO | Suggested use |
|---|---|---|
| D0 / A0 | 1 | analog in |
| D1 / A1 | 2 | analog in |
| D2 / A2 | 3 | digital — careful, strapping |
| D3 / A3 | 4 | analog in |
| D4 / SDA | 5 | I²C0 (host-side sensors) |
| D5 / SCL | 6 | I²C0 |
| D6 / TX | 43 | UART or GPIO |
| D7 / RX | 44 | UART or GPIO |

D8/D9/D10 are owned by the SD card.

---

## 4. Strapping summary (reset-time levels)

| Pin | Strapping role | XIAO header? |
|---|---|---|
| GPIO0 | boot mode (BOOT button) | no — on-board |
| GPIO3 | JTAG enable / VDD_SPI voltage | yes (D2) |
| GPIO45 | VDD_SPI voltage | no — internal flash strap |
| GPIO46 | ROM messages on/off | no |

If an application drives D2 (GPIO3) as a heavy push-pull output, ensure it is OUTPUT-OPEN-DRAIN or has a clean reset-time level so cold-boot is deterministic.

---

## 5. Change log

- 2026-04-25 — initial map, mirrors Seeed wiki + datasheet at the time of writing.
