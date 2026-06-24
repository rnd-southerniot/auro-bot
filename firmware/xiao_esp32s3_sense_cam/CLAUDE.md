# CLAUDE.md — xiao-esp32-s3-sense

> **Inherits from:** `~/Developer/projects/firmware/CLAUDE.md` → `~/.claude/CLAUDE.md`.
> **Scope:** firmware for the Seeed Studio XIAO ESP32-S3 Sense (with Sense expansion: OV2640 camera, PDM mic, microSD).
> Last updated: 2026-04-25

---

## 1. Target & Toolchain

| Item | Value |
|---|---|
| Board | Seeed Studio XIAO ESP32-S3 Sense (Sense expansion attached) |
| MCU | ESP32-S3 (QFN56) silicon **rev v0.2**, dual Xtensa LX7 + ULP-RISC-V LP, 240 MHz |
| Crystal | 40 MHz |
| Flash | 8 MB Winbond (`c8 / 4017`), QIO @ 80 MHz, 3.3 V (eFuse: quad) |
| PSRAM | 8 MB embedded Octal (`AP_3v3` / APMemory), 80 MHz |
| Wireless | Wi-Fi 4 (2.4 GHz), Bluetooth 5 LE |
| MAC (this unit) | `8C:BF:EA:8E:65:04` |
| USB | Native USB-Serial/JTAG (no UART bridge), VID:PID `0x303A:0x1001` |
| Host port | `/dev/cu.usbmodem1401` (M5 Pro, 2026-04-25) |
| SDK | ESP-IDF `v6.1-dev-3824-g484e56869c` at `~/esp/esp-idf` |
| Toolchain | xtensa-esp-elf (bundled with IDF), CMake + Ninja |
| Programmer | Native USB (ROM USB-JTAG) — no external probe needed |

---

## 2. Pin Map Summary

Authoritative source: [`docs/PIN_MAP.md`](docs/PIN_MAP.md). Single source in code: `firmware/include/gpio_remap.h`.

**Bare XIAO header pins**

| Silk | GPIO | Default alt | Notes |
|---|---|---|---|
| D0 / A0 | 1 | ADC1_CH0 | |
| D1 / A1 | 2 | ADC1_CH1 | |
| D2 / A2 | 3 | ADC1_CH2 | |
| D3 / A3 | 4 | ADC1_CH3 | |
| D4 / SDA | 5 | I²C0 SDA | |
| D5 / SCL | 6 | I²C0 SCL | |
| D6 / TX | 43 | UART0 TX | also USB-Serial console default in Arduino |
| D7 / RX | 44 | UART0 RX | |
| D8 / SCK | 7 | SPI2 SCK | **shared with Sense SD CLK** |
| D9 / MISO | 8 | SPI2 MISO | **shared with Sense SD D0** |
| D10 / MOSI | 9 | SPI2 MOSI | **shared with Sense SD CMD** |
| LED_BUILTIN | 21 | GPIO out | active **LOW** (orange "L" LED) |

**Sense expansion**

| Function | GPIO | Notes |
|---|---|---|
| Camera XCLK | 10 | OV2640 |
| Camera SIOD (SDA) | 40 | OV2640 SCCB |
| Camera SIOC (SCL) | 39 | OV2640 SCCB |
| Camera VSYNC | 38 | |
| Camera HREF | 47 | |
| Camera PCLK | 13 | |
| Camera Y2..Y9 | 15,17,18,16,14,12,11,48 | data bus |
| PDM Mic CLK | 42 | MSM261D3526H1CPM |
| PDM Mic DATA | 41 | |
| SD CLK | 7 | **conflicts with D8** |
| SD CMD | 9 | **conflicts with D10** |
| SD D0 | 8 | **conflicts with D9** |

> **Pin conflict rule:** if `gpio_remap.h` enables `SENSE_SD_ENABLED`, the SPI2 master on D8/D9/D10 MUST be disabled. Compile-time `static_assert` enforces this.

---

## 3. Hardware Safety Gates (run before EVERY first-flash on a new board)

1. **Power:** USB-C only; do NOT also feed 5V into the BAT pad. Bench supply current limit ≤ 500 mA for first flash.
2. **Boot mode:** native USB-JTAG handles bootloader entry automatically. If the device disappears from `/dev/cu.usbmodem*` and won't reconnect: hold **BOOT** (B), tap **RESET** (R), release BOOT — board enumerates as `Espressif USB JTAG_serial debug unit` in ROM mode.
3. **Erase guard:** never run `esptool erase-flash` without an explicit phase plan; the eFuse-set flash params survive but every partition (incl. NVS Wi-Fi creds, calibration) is wiped.
4. **eFuse:** do NOT burn eFuses (`espefuse.py`) — the N8R8 module ships with flash mode (quad) and PSRAM (Octal 3.3 V) already fused. Re-burning is one-way.
5. **RDP / secure boot:** disabled on this unit. Do not enable without a documented production phase.
6. **Backup before reflashing unknown firmware:**
   ```bash
   esptool -p /dev/cu.usbmodem1401 read-flash 0x0 0x800000 backup-$(date +%Y%m%d).bin
   ```
7. **Sense expansion mechanical:** the camera FFC is fragile. Lock the connector latch before powering. Do not hot-plug the FFC.

---

## 4. Canonical Build / Flash / Monitor

```bash
# One-time per shell
. ~/esp/esp-idf/export.sh

# Build
idf.py -C firmware set-target esp32s3
idf.py -C firmware build

# Flash + monitor (native USB)
idf.py -C firmware -p /dev/cu.usbmodem1401 flash monitor

# Monitor only (Ctrl-] to exit)
idf.py -C firmware -p /dev/cu.usbmodem1401 monitor

# Clean
idf.py -C firmware fullclean
```

Wrapper: `scripts/flash.sh` exports IDF, builds, flashes, and opens monitor at the project's pinned port.

Quick read-only chip query (no IDF needed):
```bash
esptool -p /dev/cu.usbmodem1401 chip-id
esptool -p /dev/cu.usbmodem1401 flash-id
```

---

## 5. Current Phase

### Phase 1 — Bring-up & sanity report

**Goal:** confirm the toolchain, board, and `sdkconfig` produce a working binary that detects 8 MB flash + 8 MB Octal PSRAM and blinks the user LED.

**Entry criteria:**
- ESP-IDF v6.1-dev sourced.
- Board enumerates at `/dev/cu.usbmodem1401`.
- No external wiring on the Sense expansion (camera/mic/SD untouched in this phase).

**Steps:**
1. `idf.py -C firmware set-target esp32s3`
2. `idf.py -C firmware build`
3. `idf.py -C firmware -p /dev/cu.usbmodem1401 flash monitor`
4. Observe boot log + heartbeat for ≥10 s.

**Smoke test (PASS/FAIL gate):**

```text
expected log lines (order may vary, all must appear within 2 s of boot):
  I (xxx) boot: ESP-IDF v6.1-dev ...
  I (xxx) cpu_start: chip revision: v0.2
  I (xxx) esp_psram: Found 8MB PSRAM device
  I (xxx) esp_psram: PSRAM initialized, cache work mode 1, 80 MHz
  I (xxx) sense_bringup: chip=ESP32-S3 rev=0.2 cores=2 features=WIFI|BT|BLE
  I (xxx) sense_bringup: flash=8 MB mode=QIO
  I (xxx) sense_bringup: psram=8 MB mode=OCT speed=80 MHz
  I (xxx) sense_bringup: reset_reason=POWERON
  I (xxx) sense_bringup: heartbeat tick=1
  I (xxx) sense_bringup: heartbeat tick=2
  ...
visual:
  orange LED on GPIO21 toggles at 1 Hz (50% duty)
```

**On PASS:** advance to Phase 2 (camera bring-up).
**On FAIL:** revert any sdkconfig changes, log root cause in §7 State, stop.
**Rollback:** `git revert <sha>` and re-flash from previous tag.

---

### Phase 2 — Camera bring-up (DVP, single JPEG capture)  [PASS]

**Goal:** initialise the Sense camera over DVP/SCCB and capture one valid JPEG.

**Steps:**
1. Pull `espressif/esp32-camera` as a managed component (`firmware/main/idf_component.yml`).
2. Flip `SENSE_CAMERA_ENABLED=1` in `gpio_remap.h`.
3. `phase2_camera_capture_one()` configures the OV2640/OV3660 with QVGA JPEG @ 12 quality, 2 frame buffers in PSRAM, and accepts the first frame whose header is `FF D8 FF` and size ≥ 2 kB. Up to 5 attempts (sensor AGC/AEC settle).

**Smoke test (PASS/FAIL gate):**

```text
within 2 s of boot, log shows:
  I (xxx) sense_camera: init OK in <300-400> ms
  I (xxx) camera: Detected (OV2640|OV3660) camera
  I (xxx) sense_camera: attempt 1: fmt=4 size=320x240 len=NNNN soi=FF D8 FF OK
  I (xxx) sense_camera: first valid JPEG at attempt N, len=NNNN bytes
  I (xxx) sense_camera: psram post-capture: free=≥6000 KiB
heartbeat continues uninterrupted at 1 Hz.
```

**Measured 2026-04-25:** sensor=OV3660 (PID 0x3660, addr 0x3C), init=335 ms, capture=122 ms, JPEG=3505 B (320×240), PSRAM post-capture free=8158 KiB.

---

### Phase 3 — PDM microphone bring-up (single 1 s capture)  [PASS]

**Goal:** initialise I²S0 in PDM RX mode against the Sense MEMS mic and verify the sensor produces real signal variance versus all-zero.

**Steps:**
1. Flip `SENSE_PDM_MIC_ENABLED=1` in `gpio_remap.h`.
2. `phase3_mic_capture_one()` configures I²S0 in PDM RX, mono left, 16-bit @ 16 kHz, on GPIO42 (CLK) / GPIO41 (DATA). Discards 250 ms of warm-up samples, then captures 1000 ms (16 000 samples), computes DC offset, peak, and RMS over `(s − dc)`.

**Smoke test (PASS/FAIL gate):**

```text
within ~2.5 s of boot, log shows:
  I (xxx) sense_mic: I²S PDM RX init OK: clk=42 din=41 sr=16000 Hz fmt=s16 mono
  I (xxx) sense_mic: captured n=16000 t≈1000 ms dc=… peak=… rms=… first4=…
  I (xxx) sense_mic: PDM mic capture PASS
gates:
  - read returned exactly 32 000 bytes
  - peak ≥ 50  LSB           (mic is alive, clock present)
  - rms ≥ 3   LSB            (signal varies, not DC-only)
  - rms ≤ 20000 LSB          (no clipping / config bug)
heartbeat continues at 1 Hz.
```

**Measured 2026-04-25:** init clean, capture 1004 ms, dc=1970, peak=2186, rms=96.0, first samples 2171, 2170, 2165, 2168 (clearly varying around DC). PASS.

---

### Phase 4 — microSD bring-up (mount + write/read 4 kB + unmount)  [PASS]

**Goal:** mount the Sense expansion's microSD slot via SDMMC 1-bit, prove the FS layer round-trips data, and unmount cleanly.

**Steps:**
1. Flip `SENSE_SD_ENABLED=1` in `gpio_remap.h` (compile-time guard against `HEADER_SPI2_ENABLED` is enforced — these two are mutually exclusive on D8/D9/D10).
2. `phase4_sd_capture_one()` mounts FAT at `/sdcard` with `format_if_mount_failed=false` (never silently destroys user data), prints `sdmmc_card_print_info()`, writes a 4 kB pseudo-random pattern to `/sdcard/_phase4.bin`, fsyncs, reads it back, byte-compares, unlinks, unmounts.

**Smoke test (PASS/FAIL gate):**

```text
expected log lines (within ~2.5 s of phase start):
  I (xxx) sense_sd: mounting /sdcard on SDMMC 1-bit (clk=7 cmd=9 d0=8) ...
  I (xxx) sense_sd: mount OK in <100 ms
  Name: ...  Type: SDHC|SDXC  Size: NNNN MB
  I (xxx) sense_sd: capacity: NNNN MB
  I (xxx) sense_sd: wrote 4096 bytes to /sdcard/_phase4.bin in <100 ms
  I (xxx) sense_sd: read back 4096 bytes in <50 ms — match OK
  I (xxx) sense_sd: microSD capture PASS
  I (xxx) sense_sd: unmount OK
gates:
  - capacity ≥ 16 MB
  - write returns exactly 4096 bytes
  - readback memcmp == 0
  - mount and unmount both succeed
heartbeat continues at 1 Hz.
```

**Operator pre-step (mandatory):** unplug USB before inserting/removing the card (no card-detect line, no hot-plug protection on the SDMMC bus). Any FAT32 / exFAT card ≥ 16 MB.

**Measured 2026-04-26:** SanDisk SC16G (SDHC, 15 193 MB), mount=62 ms, write 4 kB=28 ms (146 kB/s), read 4 kB=5 ms, byte-exact, clean unmount. PASS.

---

### Phase 5.1 — Wi-Fi STA bring-up  [PASS]

**Goal:** connect to a Wi-Fi AP in STA mode and obtain an IPv4 address.

**Steps:**
1. Disable bring-up smoke tests (`SENSE_CAMERA_ENABLED`, `SENSE_PDM_MIC_ENABLED`, `SENSE_SD_ENABLED` all → `0`); enable `PHASE5_NET_ENABLED`.
2. Set Wi-Fi creds via `idf.py menuconfig` → `Phase 5 — App configuration` → SSID/password. `sdkconfig` is gitignored.
3. `phase5_net_start_blocking()` does NVS init → `esp_netif_init` → default event loop → `esp_netif_create_default_wifi_sta` → `esp_wifi_init` → `esp_wifi_set_config` → `esp_wifi_start` → blocks on event-group bit until `IP_EVENT_STA_GOT_IP` or timeout. Up to `CONFIG_WIFI_MAX_RETRY` reconnects on disconnect with 500 ms backoff.

**Smoke test (PASS/FAIL):**

```text
within CONFIG_WIFI_CONNECT_TIMEOUT_MS (default 30 000):
  I (xxx) sense_net: wifi_init done, connecting to "<ssid>"
  I (xxx) sense_net: got IP: 192.168.X.Y, gw=…, mask=…
  I (xxx) sense_net: associated: bssid=… channel=N rssi=-NN dBm
host:
  ping -c 5 <ip>     # 5/5 replies
```

**Measured 2026-04-26:** AP `Auro` (channel 7, WPA2-PSK), RSSI -48 dBm, IP 192.168.68.106 obtained 2.3 s after boot; ping 5/5 0 % loss avg 91 ms. App binary 760 kB.

---

### Phase 5.2 — Camera pump + HTTP MJPEG stream  [PASS]

**Goal:** keep the OV3660 streaming continuously and serve frames over HTTP as live MJPEG.

**Steps:**
1. Flip `PHASE5_STREAM_ENABLED=1` in `gpio_remap.h`.
2. `phase5_cam_pump_start()` initialises the camera (config copied from Phase 2 with `fb_count=3`, `grab_mode=CAMERA_GRAB_LATEST`) and runs a producer task pinned to APP CPU (core 1, prio 5). Each iteration: `esp_camera_fb_get` → SOI check → `memcpy` into a 64 kB PSRAM `latest_buf` under a mutex → `seq++` → `fb_return`. Logs `fps_avg` every 5 s.
3. `phase5_http_start()` starts `esp_http_server` on `:80` with handlers `/`, `/stream`, `/snapshot`. Stream handler allocates its own 64 kB PSRAM scratch, polls `phase5_cam_pump_copy_latest`, and sends each new frame as a `multipart/x-mixed-replace;boundary=xframe` part.

**Smoke test (PASS/FAIL):**

```text
boot log:
  I (xxx) sense_cam_pump: camera init OK in <500 ms (PID=0x3660)
  I (xxx) sense_cam_pump: cam_pump task pinned to core 1, prio 5
  I (xxx) sense_http: server up on :80, handlers=3
  I (xxx) sense_cam_pump: fps_avg=≥10 latest_len=NN seq=NN psram_free=≥7000 KiB

host:
  curl -s http://<ip>/                    → 200 text/html (HTML page)
  curl -s http://<ip>/snapshot -o s.jpg   → JPEG 320x240, valid JFIF
  curl -sI http://<ip>/stream             → 200 + multipart/x-mixed-replace;boundary=xframe
  curl --max-time 5 http://<ip>/stream    → ≥ 50 frames in 5 s
```

**Measured 2026-04-26:** camera init 340 ms, producer 26.5 fps (sustained), stream end-to-end 26.6 fps (133 frames / 5 s, 120 kB/s ≈ 960 kbps). Snapshot 4 819 B, valid JFIF 320×240. PSRAM cost: ~178 KiB (3× 15 KiB camera fb + 64 KiB latest_buf + DMA descriptors). PASS.

---

### Phase 5.3 — Motion detection + LED state machine + `/status`  [PASS]

**Goal:** detect frame-difference motion at ~5 Hz and switch the user LED from a 1 Hz heartbeat to a 5 Hz fast blink while motion is present (with a 2 s hold-down).

**Steps:**
1. Flip `PHASE5_MOTION_ENABLED=1` in `gpio_remap.h`. Inline LED loop in `app_main` is gated out and replaced by `phase5_led_start()`.
2. `phase5_motion_start()` spawns a task pinned to PRO CPU (core 0, prio 4) that polls `cam_pump` at 5 Hz (200 ms), decodes JPEG → 80×60 RGB565 via `jpg2rgb565(JPG_SCALE_4X)`, converts to 8-bit Y, and computes per-pixel diff against the previous frame.
3. Drift compensation: subtract the global mean of `(cur − prev)` before per-pixel thresholding so AGC oscillation in the OV3660 doesn't trigger as motion.
4. AGC-event gate: if `|drift| > 15` LSB, the frame is treated as a sensor-wide exposure step and skipped.
5. On rising edge of `pct > 15 %`, increment `event_count`, set `motion_active_until_ms = now + 2000`. Three C11 atomics (`motion_until`, `last_motion`, `event_count`) are read by the LED task and the `/status` handler without locking.
6. `phase5_led_start()` spawns a task that toggles `BOARD_LED_GPIO` with half-period = `phase5_motion_is_active() ? 100 ms : 500 ms`.
7. `phase5_http`'s new `/status` handler returns `{motion, seconds_since_last, event_count, fps, free_psram_kb}` JSON.

**Smoke test (PASS/FAIL):**

```text
boot log:
  I (xxx) sense_motion: motion task started, scale=4x grid=80x60 hold=2000 ms thr=…
  I (xxx) sense_led: LED task started, gpio=21 active_low=1 heartbeat=500 ms fast=100 ms

idle:
  curl -s http://<ip>/status → {"motion":false, …, "event_count":0}
  LED visibly slow ~1 Hz.

hand wave:
  → {"motion":true, "seconds_since_last":<0.5, "event_count":N≥1}
  LED visibly fast ~5 Hz.

stop waving:
  within 2 s → motion returns to false; LED returns to slow.
```

**Tunables (top of `phase5_motion.c`, calibrated 2026-04-26 in a typical indoor scene):**

| Constant | Value |
|---|---|
| `MOTION_POLL_MS` | 200 (5 Hz) |
| `HOLD_MS` | 2000 |
| `PIXEL_DELTA_THR` | 30 |
| `MOTION_PCT_THR` | 15 % |
| `MAX_DRIFT_ABS` | 15 |
| `LED_HEARTBEAT_HALF_MS` | 500 |
| `LED_FAST_HALF_MS` | 100 |

**Measured 2026-04-26:** static-scene noise floor 4–6 % post-drift (well under 15 %), AGC events skipped (drift ~25), real hand-wave triggers within ≈ 200 ms, LED transitions visually crisp, returns to heartbeat ~2 s after motion stops. Operator-confirmed PASS.

---

### Phase 6.1 — Web UI overhaul + status panel  [PASS]

**Goal:** replace the placeholder `<img>`-only page with a self-contained single-page UI that shows live status, lets the user pause the stream client-side, and exposes a "save snapshot" action.

**Steps:**
1. Embed a ~5.5 kB HTML/CSS/JS document in `phase5_http.c` `INDEX_HTML`. No external CDN, no build tooling — single C string.
2. UI: header with link-status dot (idle/ok/alert-pulse on motion) + project name + version. Main grid: live `<img src="/stream">` panel + side aside with **Motion** (state, last-seen age, event count) and **System** (fps, free PSRAM, RSSI, uptime) panels. Buttons: Pause / Save snapshot / Reload stream.
3. JS polls `/status` every 1 s with `fetch`, updates DOM. Pause hides the `<img>` (stops bandwidth client-side). Snapshot uses an anchor with `download="xiao-snap-<iso>.jpg"`.
4. `/status` extended with `uptime_s`, `rssi_dbm` (from `esp_wifi_sta_get_ap_info`), and `version` (from `esp_app_get_description()->version`). Required adding `esp_app_format` to main's REQUIRES.

**Smoke test:**

```text
curl -s http://<ip>/         → 200 text/html, ~5.5 kB
curl -s http://<ip>/status   → JSON has motion / seconds_since_last /
                                event_count / fps / free_psram_kb /
                                uptime_s / rssi_dbm / version
operator opens http://<ip>/  → sees status panel, dot pulses red on
                                hand-wave, returns to green idle ~2 s
                                after motion stops.
```

**Measured 2026-04-26:** index 5 582 B inline, /status carries all fields incl. `rssi_dbm:-44`, `version:"v0.1.0-bringup-3-gf8dfa7b-dirty"`. PASS.

---

### Phase 6.2 — Runtime camera + motion controls  [PASS]

**Goal:** let the operator change frame size, JPEG quality, and toggle motion detection from the browser without rebooting.

**Steps:**
1. `phase5_cam_pump` exposes `phase5_cam_pump_request_framesize(name)`, `phase5_cam_pump_request_quality(q)`, getters `phase5_cam_pump_get_framesize_name/get_quality`. Pending changes are queued under `s_cfg_mutex` and applied at the top of the next pump iteration: quality alone uses `sensor->set_quality` with no reinit; frame-size triggers `esp_camera_deinit` + `esp_camera_init` (~340 ms freeze).
2. `phase5_motion` adds `_Atomic bool s_enabled` with `phase5_motion_set_enabled(b)` and `_get_enabled()`. `phase5_motion_is_active` returns false when disabled. On re-enable, the previous-Y plane is dropped so the next comparison isn't against a stale frame.
3. `phase5_http`:
   - new handler `control_handler` (mounted GET + POST) parses URL-query params: `framesize`, `quality`, `motion`. Returns the same JSON shape as `/status`.
   - `/status` extended with `framesize` (string), `quality` (int), `motion_enabled` (bool).
   - UI: new **Camera** panel (frame-size `<select>`, quality `<input type=range>` debounced), **detection enabled** checkbox in the Motion panel. JS auto-applies on change via `fetch('/control?...', POST)`, syncs control values from `/status` on first poll only.
4. UI dropdown limited to **QQVGA / QVGA / CIF** for now: VGA+ panic with `cam_hal: FB-OVF` because `PSRAM DMA mode disabled` in this IDF v6 build of esp32-camera. Bigger resolutions are blocked at the `phase5_cam_pump` table level too, so `/control?framesize=VGA` is rejected. Fix is a Phase 7 backlog item (enable PSRAM-DMA in the camera component Kconfig + adjust DMA buffer sizing).

**Smoke test (PASS/FAIL):**

```text
curl -s -X POST 'http://<ip>/control?framesize=CIF&quality=18'
  → JSON shows framesize:CIF quality:18

curl -s -X POST 'http://<ip>/control?motion=off'
  → JSON shows motion_enabled:false; LED returns to heartbeat
     even with movement in front of the camera.

curl -s -X POST 'http://<ip>/control?framesize=VGA' → rejected, status unchanged.

operator: changes select/slider/checkbox in browser → values
          reflected in /status within 1 s; size change visibly
          re-renders the <img> at new dimensions.
```

**Measured 2026-04-26:** combined-param requests (`framesize=X&quality=Y`) apply both atomically after fixing a bug where the second `phase5_cam_pump_request_*` was overwriting the first call's pending values. Operator-confirmed visual + JSON state. PASS.

---

### Phase 6.3 — NVS settings + MQTT publish on motion + test/status UI  [PASS]

**Goal:** persist operator config across reboots, publish a JSON message to a configurable MQTT topic on every motion rising-edge, and expose broker config + state in the UI.

**New modules:**
- `phase6_settings.{c,h}` — thin wrapper over `nvs_*` in namespace `siot_p6`. Typed get/set for str/int/bool. NVS init is reused from `phase5_net` (which calls `nvs_flash_init`).
- `phase6_mqtt.{c,h}` — wraps the `espressif/mqtt` managed component (^1.0.0, IDF v6 moved `mqtt` out of core). Handles connect / disconnect / reconnect, publishes `{"event":"motion","count":N,"uptime_s":N}` on rising edge, exposes connection state + publish counter.

**Phase 5 modules touched:**
- `phase5_motion`: `phase5_motion_set_event_handler(cb)` registers a void(uint32_t) callback fired on every rising edge. Cb runs on the motion task — must be non-blocking (esp-mqtt's publish is internally async, so this is fine).
- `phase5_cam_pump` and `phase5_motion`: at start, override compile-time defaults from NVS (`cam_fs`, `cam_q`, `motion_en`).
- `phase5_http`: new `/control` mqtt_* params, new `/mqtt-test` POST endpoint, `/status` extended with `mqtt_*` fields (password never exposed). New "MQTT" UI panel — broker URI, topic, username, password, QoS, retain, enabled, **Save & connect**, **Test publish**.

**HTTP server architecture change (notable):** `esp_http_server` has a single worker task per server instance — a long-lived handler (e.g., `/stream`'s `while(1) httpd_resp_send_chunk()`) blocks all other requests. Split into **two server instances**: control plane on `:80` (index, status, control, snapshot, mqtt-test), data plane on `:81` (stream). Browser builds the stream URL from `location.hostname` in JS.

**Hardening that surfaced during bring-up:**
- All `/control` query values are URL-decoded in-place before storage. Discovered when the browser-encoded URI (`mqtt%3A%2F%2F…`) was passed verbatim to `esp_mqtt_client_init`, panicking the device.
- `phase6_mqtt_init` defensively decodes legacy NVS values, sanity-checks the URI prefix (`mqtt://` / `mqtts://` / `ws[s]://`), and refuses to start the client on a malformed URI — preventing the panic-loop. Cleaned values are persisted back to NVS so `/status` reflects truth.
- `CONFIG_LWIP_MAX_SOCKETS` raised to 16, control-plane `httpd` `max_open_sockets=7`, data-plane `=4`, `lru_purge_enable=true` on both.
- Index page: `Cache-Control: no-cache` so UI updates propagate immediately.

**Smoke test (PASS/FAIL):**

```text
broker config:
  curl -X POST 'http://<ip>/control?mqtt_uri=mqtt://<broker>:1883&mqtt_user=…&mqtt_pass=…&mqtt_enabled=on'
  → /status: mqtt_state goes connecting → connected within ~1 s

test publish:
  curl -X POST http://<ip>/mqtt-test → {"ok":true}; mqtt_publish_count bumps.
  external: mosquitto_sub -h <broker> -t 'siot/.../motion' -v shows
            {"event":"test","uptime_s":N}

motion publish:
  hand-wave → mosquitto_sub shows
            {"event":"motion","count":N,"uptime_s":N}
            on rising edge; mqtt_publish_count bumps; LED switches to fast blink.

reboot persistence:
  reset → boot reads NVS → MQTT auto-reconnects with prior creds.
  /status shows correct framesize / quality / motion_enabled / mqtt_*.

UI under load:
  open browser tab (consumes stream socket on :81) and click around the
  control plane on :80. /status updates 1 Hz, controls apply <1 s,
  test publish responds <500 ms.
```

**Operator-confirmed 2026-04-26:** end-to-end MQTT pipeline working — broker `mqtt://10.10.9.251:1883` (auth `arif/…`), topic `siot/xiao-esp32s3-sense/motion`, QoS 2, motion-on-publish verified at the broker via `mosquitto_sub`, UI MQTT panel reactive after splitting servers. PASS.

---

## 6. Resource Budgets

| Resource | Budget | Phase 1 measured |
|---|---|---|
| Flash (`.bin`) | ≤ 1.5 MB / 8 MB device | 176 kB app + 22 kB bootloader (88 % partition free) |
| Internal SRAM static heap | ≤ 200 kB | ~389 kB total free (336 + 21 + 32 KiB) |
| PSRAM heap | ≥ 6 MB free | 8192 kB pool added |
| Boot to `app_main` | < 800 ms | ≈ 520 ms (boot ROM → `Calling app_main()`) |
| Main loop period | 1000 ms ± 5 ms (heartbeat) | 1000 ms ticks 1–7 (visual confirmed) |

CI (future) will diff `.bin` size vs `main` and fail on >5% growth.

---

## 7. State

<!-- 2026-04-25: Project initialized on M5 Pro. Board detected: ESP32-S3 rev v0.2, 8MB flash QIO, 8MB Octal PSRAM, MAC 8c:bf:ea:8e:65:04, port /dev/cu.usbmodem1401. ESP-IDF v6.1-dev-3824-g484e56869c. -->
<!-- 2026-04-25: ESP-IDF submodules force-resynced (heap/tlsf and spiffs/spiffs had empty worktrees). -->
<!-- 2026-04-25: IDF v6.x compatibility: main/CMakeLists REQUIRES esp_driver_gpio (not legacy 'driver'); esp_clk_cpu_freq() now lives in esp_private/esp_clk.h. -->
<!-- 2026-04-25: Phase 1 PASS. Boot log confirms: ESP32-S3 rev v0.2, 2 cores, 240 MHz, 8 MB flash QIO, 8 MB Octal PSRAM (AP gen3 64Mbit, 3V) @ 80 MHz, WIFI|BLE features (S3 has no Classic BT — expected), reset_reason=USB after esptool reset, heartbeat 1 Hz steady. Boot-to-app_main ≈ 520 ms. App binary 176 kB. -->
<!-- 2026-04-25: Phase 2 PASS. esp32-camera 2.1.6 + esp_jpeg 1.3.1 pulled as managed components. Sensor detected as OV3660 (PID 0x3660, NOT OV2640 as Seeed wiki documents — newer Sense revision). Init 335 ms, single QVGA JPEG (320x240, 3505 B, valid SOI FF D8 FF) captured on first attempt in 122 ms. PSRAM cost: 31 KiB for 2 frame buffers + DMA descriptors. App binary now 283 kB. -->
<!-- 2026-04-25: Phase 3 PASS. PDM mic on GPIO42/41 captured 16000 samples (1004 ms, 16 kHz mono s16). dc=1970 peak=2186 rms=96.0; quiet-room noise floor consistent (~ -23 dBFS). I²S API used: new i2s_chan + i2s_pdm_rx_config_t (driver/i2s_pdm.h). App binary 304 kB (80% partition free). All prior phases unregressed. -->
<!-- 2026-04-26: Phase 4 PASS. SDMMC 1-bit on GPIO7/9/8 mounted SanDisk SC16G (SDHC, 15193 MB) in 62 ms. 4 kB write (28 ms, 146 kB/s) + readback (5 ms) byte-exact, clean unmount. SDK quirk noted: 'SD_HOST: input line delay not supported, fallback to 0 delay' — informational, not a fault. App binary 388 kB (75% partition free). All four Sense subsystems (chip ID, camera, mic, SD) now green. -->
<!-- 2026-04-26: v0.1.0-bringup tagged. -->
<!-- 2026-04-26: Phase 5.1 PASS. App-mode begins: bring-up smoke tests disabled at compile time; Wi-Fi STA brought up via standard esp_wifi/esp_netif/esp_event idiom, creds from Kconfig (sdkconfig gitignored). On AP "Auro" RSSI -48 dBm, IP 192.168.68.106 in 2.3 s, ping 5/5. App binary 760 kB (driven by esp_wifi+lwIP stack). MACSTR/MAC2STR moved to esp_mac.h in v6.x — required adding that include. -->
<!-- 2026-04-26: Phase 5.2 PASS. cam_pump (core 1, prio 5) feeds 64 kB PSRAM latest_buf under mutex with a seq counter; HTTP /stream + /snapshot + / on :80. End-to-end 26.6 fps QVGA q12 (≈ 960 kbps), camera-producer rate matches stream-consumer rate, no drops. PSRAM cost ~178 KiB (3× cam fb + latest_buf). Binary 901 kB. -->
<!-- 2026-04-26: Phase 5.3 PASS. Frame-diff motion at 5 Hz on JPG_SCALE_4X (80x60) Y plane; LED state machine swaps 500/100 ms half-period from atomic motion-until timestamp; /status JSON. Tuning lessons: OV3660 AGC oscillation puts the noise floor at ~8% pixels-changed without compensation — added (a) global-drift subtraction before per-pixel threshold, (b) drift-magnitude gate to skip whole-frame AGC steps. Final thresholds: PIXEL_DELTA_THR=30, MOTION_PCT_THR=15%, MAX_DRIFT_ABS=15. App binary 922 kB. Operator confirmed visual LED behaviour (heartbeat <-> fast on hand wave). -->
