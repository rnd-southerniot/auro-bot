# Validation Execution Workflow

Complete step-by-step procedure for final deployment validation.
Execute on the Raspberry Pi 5 with the robot fully assembled.

---

## Phase 1 — Firmware Archival

### 1.1 Build Firmware on Pi

```bash
cd /home/arif/projects/makerpi-rp2040-ros2-navbot
cd firmware/makerpi_rp2040_base
mkdir -p build && cd build
cmake .. -DPICO_SDK_PATH=$PICO_SDK_PATH
make -j$(nproc)
# Expected: firmware.uf2 created
ls -la firmware.uf2
```

### 1.2 Archive Before Flashing

```bash
cd /home/arif/projects/makerpi-rp2040-ros2-navbot
./scripts/archive_firmware.sh
```

Expected output:
```
Firmware archived successfully.
  Path:     firmware_archive/v1.2.0_20260412_XXXXXX
  Version:  1.2.0
  Commit:   1e15221
  Tag:      v1.2.0-validation-freeze
  SHA256:   <64-char hex>
```

### 1.3 Flash Firmware

```bash
# 1. Disconnect RP2040 USB
# 2. Hold BOOTSEL, connect USB, release BOOTSEL
# 3. Copy:
cp firmware/makerpi_rp2040_base/build/firmware.uf2 /media/$USER/RPI-RP2/
# 4. Wait for auto-reboot
```

### 1.4 Verify Flash

```bash
python3 -m serial.tools.miniterm \
  /dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00 115200
# Type: PING
# Expected: ACK PING 1.2.0*XX
# Type: STOP
# Expected: ACK STOP*XX
# Exit: Ctrl+]
```

**GATE: Do not proceed until PING returns v1.2.0.**

---

## Phase 2 — Bench Tests (S1–S8, C1–C10, I1–I10, W1–W5)

Follow the complete bench test procedure in `docs/DEPLOYMENT_VALIDATION.md` sections 2–5.

Estimated time: 60–90 minutes.

**Quick reference — test sequence:**

```
Safety:    S1 → S2 → S3 → S4 → S5 → S6 → S7 → S8
Comms:     C1 → C2 → C3 → C4 → C7 → C8 → C9 → C10 → C6
Sensors:   I1 → I4 → I6 → I8 → I2 → I3 → I5 → I7 → I9 → I10
Security:  W1 → W3 → W4 → W5
```

**GATE: ALL tests must pass. Any safety test (S1–S8) failure is an immediate NO-GO.**

---

## Phase 3 — Soak Test Setup (3 Terminals)

### Terminal 1 — ROS Stack

```bash
source /opt/ros/jazzy/setup.bash
source /home/arif/ros2_ws/install/setup.bash
source /home/arif/projects/makerpi-rp2040-ros2-navbot/ros2_ws/install/setup.bash
ros2 launch navbot_bringup imu_localization.launch.py
```

Wait 10 seconds for all nodes to start. Verify:

```bash
# In a quick check terminal:
ros2 topic list | wc -l
# Expected: 20+ topics
ros2 topic hz /odom --window 10
# Expected: ~10 Hz
```

### Terminal 2 — Web Console

```bash
cd /home/arif/projects/makerpi-rp2040-ros2-navbot
./scripts/launch_web_console.sh port:=8081
```

Verify:

```bash
curl -s http://127.0.0.1:8081/api/status | python3 -m json.tool | head -3
# Expected: valid JSON
```

### Terminal 3 — Soak Monitor

```bash
cd /home/arif/projects/makerpi-rp2040-ros2-navbot
./scripts/soak_test.sh 8
```

Expected output:

```
Soak test: 8h, logging to /home/arif/navbot_soak_20260412_XXXXXX
Monitoring active. Will run for 8h.
Press Ctrl+C to stop early.
```

Record the log directory path: `____________________________________`

---

## Phase 4 — Live Checkpoints During Soak

### Every 30 Minutes

SSH to Pi and run:

```bash
cd /home/arif/projects/makerpi-rp2040-ros2-navbot
./scripts/soak_checkpoint.sh 8081
```

Record timestamp and any warnings in the table below.

| Time | Uptime | Latency | Reconnects | Checksum Fails | Memory Free | Notes |
|------|--------|---------|------------|----------------|-------------|-------|
| +0:30 | | | | | | |
| +1:00 | | | | | | |
| +1:30 | | | | | | |
| +2:00 | | | | | | |
| +2:30 | | | | | | |
| +3:00 | | | | | | |
| +3:30 | | | | | | |
| +4:00 | | | | | | |
| +4:30 | | | | | | |
| +5:00 | | | | | | |
| +5:30 | | | | | | |
| +6:00 | | | | | | |
| +6:30 | | | | | | |
| +7:00 | | | | | | |
| +7:30 | | | | | | |
| +8:00 | | | | | | |

### Every 2 Hours — Manual DIAG Verification

At the +2:00, +4:00, +6:00, and +8:00 checkpoints, also run:

```bash
python3 firmware/makerpi_rp2040_base/tools/manual_serial_check.py \
  --port /dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00 \
  --send DIAG --read-seconds 0.5
```

Verify the DIAG line is complete (ends with `*XX`, not truncated).

### Immediate Escalation Triggers

Stop the soak immediately if:
- Checkpoint shows `serial_connected: false`
- Any kernel voltage warning appears
- Free memory drops below 100 MB
- Web console returns connection errors
- Latency exceeds 50 ms for 3+ consecutive checkpoints

---

## Phase 5 — Post-Soak Analysis

After the soak completes (8h timer expires or Ctrl+C):

### 5.1 Run Automated Analysis

```bash
cd /home/arif/projects/makerpi-rp2040-ros2-navbot
./scripts/soak_analyze.sh
```

This prints a section-by-section pass/fail report.

### 5.2 Detailed Log Inspection

```bash
cd ~/navbot_soak_*   # most recent

# Disconnections (must be 0)
grep -c '"serial_connected": false' bridge_health.jsonl

# Latency outliers
python3 -c "
import json
lats = []
for line in open('bridge_health.jsonl'):
    try:
        d = json.loads(line.strip())
        v = d.get('last_latency_ms')
        if v is not None: lats.append(v)
    except: pass
if lats:
    over = [l for l in lats if l > 20]
    print(f'Total samples: {len(lats)}')
    print(f'Over 20ms: {len(over)}')
    if over: print(f'Outlier values: {sorted(over, reverse=True)[:10]}')
"

# Memory leak check (visual trend)
grep 'Mem:' system.log | awk '{print NR, $4}' | head -20
# Values should be stable ± 20 MB

# DIAG samples — verify none are truncated
grep '^DIAG ' diag.log | while read line; do
  if echo "$line" | grep -q '\*[0-9A-F][0-9A-F]$'; then
    echo "OK: $(echo $line | cut -c1-60)..."
  else
    echo "*** TRUNCATED: $line"
  fi
done
```

---

## Phase 6 — Generate Validation Record

```bash
cd /home/arif/projects/makerpi-rp2040-ros2-navbot
./scripts/generate_validation_record.sh > \
  "validation_record_$(date +%Y%m%d).md"

echo "Record generated: validation_record_$(date +%Y%m%d).md"
```

Open the generated file. It will be pre-filled with soak metrics. Manually complete:
- All bench test checkboxes (from Phase 2 results)
- Sensor rate measurements
- Integration test measurements (1m accuracy, heading accuracy)
- Observations
- Final decision
- Signature

---

## Quick Reference — All Scripts

| Script | Purpose | When to Run |
|--------|---------|-------------|
| `scripts/archive_firmware.sh` | Archive .uf2 with SHA256 + metadata | Before flashing |
| `scripts/soak_test.sh 8` | Start 8h soak monitor | Phase 3 |
| `scripts/soak_checkpoint.sh 8081` | Quick health check | Every 30 min during soak |
| `scripts/soak_analyze.sh` | Parse soak logs, print report | After soak completes |
| `scripts/generate_validation_record.sh` | Generate sign-off document | After all tests complete |

## Quick Reference — Failure Thresholds

| Metric | PASS | FAIL |
|--------|------|------|
| Serial latency | < 10 ms avg, < 50 ms max | > 50 ms for 5+ samples |
| Reconnects during soak | 0 | > 3 in any 1h window |
| Checksum failures | 0 | > 10 total |
| Topic rate (/odom) | > 5 Hz | < 5 Hz for > 60s |
| Topic rate (/scan) | > 5 Hz | < 5 Hz for > 60s |
| Free memory | > 200 MB | < 100 MB |
| Memory growth | < 50 MB over 8h | > 50 MB |
| Pi temperature | < 75°C | > 80°C |
| Kernel warnings | 0 | Any |
| Disconnection samples | 0 | Any |
