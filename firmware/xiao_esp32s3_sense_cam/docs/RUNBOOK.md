# RUNBOOK — xiao-esp32-s3-sense

Operational procedures for bring-up, recovery, and common failure modes.

---

## 1. First-time bring-up on a fresh M5 Pro shell

```bash
# Source IDF (every new shell)
. ~/esp/esp-idf/export.sh

# Verify board reachable
ls /dev/cu.usbmodem*           # expect a usbmodemNNNN entry
esptool -p /dev/cu.usbmodem1401 chip-id

# Build + flash + monitor
cd ~/Developer/projects/firmware/xiao-esp32-s3-sense
./scripts/flash.sh
```

Successful Phase 1 boot ends with `sense_bringup: heartbeat tick=N` lines and the orange LED toggling at 1 Hz.

---

## 2. Board not appearing on `/dev/cu.usbmodem*`

Native USB-CDC may have been crashed by the running app, or the board is in deep-sleep without USB attach.

Force the ROM bootloader:

1. Hold **BOOT** (B button on top).
2. Press and release **RESET** (R button).
3. Release **BOOT**.
4. `ls /dev/cu.usbmodem*` — should reappear within 1 s.
5. Re-flash: `./scripts/flash.sh`.

If still no enumeration:
- Try a different USB-C cable (must be data-capable, not charge-only).
- Try the M5 Pro direct port instead of the USB-C hub.
- `system_profiler SPUSBDataType | grep -i espressif` — look for ROM device `USB JTAG_serial debug unit`.

---

## 3. `idf.py flash` fails with "Failed to connect"

Almost always a BOOT/RESET timing issue when the running app blocks USB:

1. Hold **BOOT**.
2. Run `./scripts/flash.sh` (or `idf.py flash`).
3. Release **BOOT** when esptool prints `Connecting......`.

For permanent fix, flash a known-good binary that does not block USB-Serial/JTAG.

---

## 4. Recover from a bricked app (boot loop / panic)

Symptoms: monitor prints `Guru Meditation Error` repeatedly, or `rst:0xc (RTCWDT_RTC_RESET)` in a tight loop.

```bash
# 1. Capture the panic for analysis
idf.py -C firmware -p /dev/cu.usbmodem1401 monitor | tee panic-$(date +%Y%m%d-%H%M%S).log
# Ctrl-] after a few panic cycles

# 2. Flash a minimal known-good app (e.g. Phase 1 main)
git checkout phase-1-pass            # tag once Phase 1 PASSes
./scripts/flash.sh

# 3. Or full erase (DESTRUCTIVE - wipes NVS/calibration)
#    Confirm with operator before running.
esptool -p /dev/cu.usbmodem1401 erase-flash
./scripts/flash.sh
```

---

## 5. Backup / restore flash image

```bash
# Backup (read-only, safe)
esptool -p /dev/cu.usbmodem1401 read-flash 0x0 0x800000 backup-$(date +%Y%m%d).bin

# Restore (DESTRUCTIVE - confirm before running)
esptool -p /dev/cu.usbmodem1401 write-flash 0x0 backup-YYYYMMDD.bin
```

---

## 6. Common errors and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `A fatal error occurred: Could not open /dev/cu.usbmodem...` | port held by another process | `lsof /dev/cu.usbmodem1401` → kill stale `idf_monitor` |
| `E (xx) esp_psram: Octal PSRAM ID read error` | sdkconfig set Quad PSRAM but module is Octal | set `CONFIG_SPIRAM_MODE_OCT=y` |
| `E (xx) cam_hal: cam_dma_config: dma_chan alloc failed` | DMA channel exhausted by other peripheral | free I²S/SPI before camera init |
| Boot stuck at `entry 0x...` | flash mode mismatch | `CONFIG_ESPTOOLPY_FLASHMODE_QIO=y`, freq 80 MHz |
| Brownout reset on Wi-Fi TX | underpowered USB | use direct M5 Pro port or 5 V/1 A bench supply |

---

## 7. Useful one-liners

```bash
# Live chip info
esptool -p /dev/cu.usbmodem1401 chip-id
esptool -p /dev/cu.usbmodem1401 flash-id

# Read MAC
esptool -p /dev/cu.usbmodem1401 read-mac

# Size report after build
idf.py -C firmware size
idf.py -C firmware size-components

# Decode a panic backtrace
idf.py -C firmware monitor                # IDF auto-decodes if .elf is present

# Filter logs
idf.py -C firmware monitor --print_filter "sense_*:I *:N"
```
