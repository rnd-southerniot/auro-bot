# Final Deployment Validation Execution Guide

Firmware v1.2.0 — All blocking fixes applied — April 2026

This document is the operator-facing execution guide. Follow it sequentially. Do not skip steps. Record every result in the checklist at the bottom.

---

## 1. Prerequisites

Before starting validation:

```bash
# On the Pi — verify code is current
cd /home/arif/projects/makerpi-rp2040-ros2-navbot
git log --oneline -1
# Expected: latest commit with "Post-upgrade validation" in message

# Verify unit tests pass
python3 -m pytest tests/ -v
# Expected: 84 passed

# Build workspace
./scripts/build_ros2_ws.sh
# Expected: "Build complete"
```

Flash firmware v1.2.0 to the RP2040 using the procedure in `firmware/makerpi_rp2040_base/FLASHING.md`.

**Archive the previous firmware binary before flashing.**

---

## 2. Bench Test Execution — Safety (S1–S8)

All safety tests use direct serial communication. Open miniterm:

```bash
python3 -m serial.tools.miniterm /dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00 115200
```

### S1: Watchdog USB-Unplug Stop

```
1. Type: CMD_VEL 0.15 0.0
2. Verify: motors spinning (visual or oscilloscope)
3. Action: physically unplug the USB cable
4. Observe: motors must coast to stop within 250ms
```

| Result | Pass / Fail |
|--------|-------------|
| Motors stopped within 250ms? | _____ |
| Notes: | |

### S2: Watchdog Reboot Verification

```
1. Reconnect USB (RP2040 rebooted from watchdog)
2. Open miniterm again
3. Type: PING
4. Expected: ACK PING 1.2.0*XX (with checksum)
```

| Result | Pass / Fail |
|--------|-------------|
| ACK PING 1.2.0 received? | _____ |
| Response arrived within 2s? | _____ |

### S3: ESTOP Hardware

```
1. Type: CMD_VEL 0.15 0.0
2. Verify: motors spinning
3. Action: press ESTOP button (GP20)
4. Observe: motors stop immediately
5. Read telemetry: STATE ESTOP ESTOP*XX should appear
```

| Result | Pass / Fail |
|--------|-------------|
| Motors stopped immediately? | _____ |
| STATE ESTOP ESTOP in telemetry? | _____ |

### S4: ESTOP Race Test

```
1. Hold ESTOP button down continuously
2. In a second terminal, run:
   python3 firmware/makerpi_rp2040_base/tools/manual_serial_check.py \
     --port /dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00 \
     --send RESET --send RESET --send RESET --send RESET --send RESET \
     --send RESET --send RESET --send RESET --send RESET --send RESET \
     --read-seconds 0.3
3. All 10 responses must be: ERR ESTOP_HELD*XX
4. Repeat with 50 RESET commands if scripted
```

| Result | Pass / Fail |
|--------|-------------|
| All responses were ERR ESTOP_HELD? | _____ |
| Zero false clears? | _____ |

### S5: ESTOP Recovery

```
1. Release ESTOP button
2. Type: RESET
3. Expected: ACK RESET*XX
4. Type: CMD_VEL 0.10 0.0
5. Expected: ACK CMD_VEL*XX, motors turn
6. Type: STOP
```

| Result | Pass / Fail |
|--------|-------------|
| ACK RESET received after release? | _____ |
| CMD_VEL works after reset? | _____ |

### S6: USB Disconnect with Pi Bridge

```
1. On Pi, launch base:
   source /opt/ros/jazzy/setup.bash
   source ros2_ws/install/setup.bash
   ros2 launch navbot_bringup base.launch.py
2. Verify /odom publishing: ros2 topic hz /odom (should be ~10 Hz)
3. Open web console and send forward command
4. While motors running, unplug RP2040 USB
5. Motors must stop (firmware watchdog + USB disconnect guard)
6. Reconnect USB
7. Wait up to 5s
8. Check Pi logs for: "connected to ... (firmware 1.2.0)"
9. Verify /odom resumes
```

| Result | Pass / Fail |
|--------|-------------|
| Motors stopped on disconnect? | _____ |
| Bridge reconnected with version? | _____ |
| /odom resumed after reconnect? | _____ |

### S7: Command Timeout

```
1. In miniterm, type: CMD_VEL 0.10 0.0
2. Verify: motors spinning
3. Do NOT send anything for 600ms
4. Observe telemetry for: STATE TIMEOUT CMD_TIMEOUT*XX
5. Motors must have stopped
```

| Result | Pass / Fail |
|--------|-------------|
| Timeout detected at ~500ms? | _____ |
| STATE TIMEOUT CMD_TIMEOUT in output? | _____ |

### S8: Stall Detection

```
1. Type: CMD_VEL 0.15 0.0
2. Mechanically block one wheel (hold it firmly)
3. Wait up to 2s (800ms grace + 500ms stall timeout)
4. Observe: STATE FAULT STALL*XX
5. Motors stop
6. Type: RESET to clear
```

| Result | Pass / Fail |
|--------|-------------|
| Stall detected within expected window? | _____ |
| STATE FAULT STALL in output? | _____ |

**GATE: All S1–S8 must pass before proceeding to communication tests.**

---

## 3. Bench Test Execution — Communication (C1–C10)

### C1–C4: Checksum Tests

All in miniterm:

```
C1: Type: PING*10
    Expected: ACK PING 1.2.0*XX (accepted — 0x10 is correct XOR for "PING")

C2: Type: PING*00
    Expected: ERR BAD_CHECKSUM*XX (rejected)

C3: Type: PING
    Expected: ACK PING 1.2.0*XX (accepted — no checksum is OK)

C4: Type: PING*A
    Expected: ERR BAD_CHECKSUM*XX (rejected — truncated suffix)
```

| Test | Expected | Actual | Pass/Fail |
|------|----------|--------|-----------|
| C1 valid checksum | ACK PING 1.2.0 | | |
| C2 wrong checksum | ERR BAD_CHECKSUM | | |
| C3 no checksum | ACK PING 1.2.0 | | |
| C4 truncated | ERR BAD_CHECKSUM | | |

### C7: Firmware Version

```
Type: PING
Verify response contains "1.2.0"
```

| Result | Pass / Fail |
|--------|-------------|
| Version is 1.2.0? | _____ |

### C8: DIAG Idle

```
Type: DIAG
Expected: DIAG <stamp> L:0,0.0,0.0,0.0,0.0,0.0,0 R:0,0.0,0.0,0.0,0.0,0.0,0*XX
Verify: line is NOT truncated (ends with *XX, not cut off mid-field)
```

| Result | Pass / Fail |
|--------|-------------|
| DIAG output received? | _____ |
| Line ends with *XX (not truncated)? | _____ |

### C9: DIAG Under Load

```
1. Type: CMD_VEL 0.15 0.0
2. Wait 1s for motors to reach speed
3. Type: DIAG
4. Verify: duty, setpoint, and filtered CPS are non-zero
5. Verify: line ends with *XX
6. Type: STOP
```

| Result | Pass / Fail |
|--------|-------------|
| Non-zero PID values visible? | _____ |
| No truncation? | _____ |

### C10: Line Overflow

```
Type a line longer than 190 characters (hold down a key)
Expected: ERR LINE_TOO_LONG*XX
```

| Result | Pass / Fail |
|--------|-------------|
| LINE_TOO_LONG error returned? | _____ |

### C6: Reconnect Handshake (on Pi)

```
1. Launch base bridge on Pi
2. Verify /odom is publishing
3. Kill the bridge node: kill -9 $(pgrep -f navbot_serial_bridge)
4. Restart: ros2 launch navbot_bringup base.launch.py
5. Check logs for "connected to ... (firmware 1.2.0)"
```

| Result | Pass / Fail |
|--------|-------------|
| Bridge reconnected with handshake? | _____ |
| Firmware version logged? | _____ |

**GATE: All C1–C10 must pass before proceeding to sensor tests.**

---

## 4. Bench Test Execution — Sensors (I1–I10)

Launch the full stack:

```bash
source /opt/ros/jazzy/setup.bash
source /home/arif/ros2_ws/install/setup.bash
source ros2_ws/install/setup.bash
ros2 launch navbot_bringup imu_localization.launch.py
```

### I1: IMU Alive

```bash
ros2 topic hz /imu/l3gd20_lsm303d/raw --window 20
# Expected: average rate ~20 Hz
```

### I4: INA238 Alive

```bash
ros2 topic echo /power/ina238/status --once | grep available
# Expected: available: true
```

### I6: LiDAR Alive

```bash
ros2 topic hz /scan --window 20
# Expected: average rate 8-12 Hz
```

### I8: TF Chain

```bash
ros2 run tf2_tools view_frames
# Open the generated PDF. Verify imu_link exists as child of base_link.
```

### I2–I3: IMU Failure and Recovery

```
1. While stack is running, physically disconnect IMU I2C cable
2. Check: ros2 topic echo /imu/l3gd20_lsm303d/status --once
   Expected: "available": false
3. Verify: no node crash
4. Reconnect I2C cable
5. Wait 5s
6. Check: status returns to "available": true
```

### I5: INA238 Absent

```
1. Stop the stack
2. Disconnect INA238 from I2C
3. Relaunch stack
4. Check: ros2 topic echo /power/ina238/status --once
   Expected: "available": false
5. Open web console: power panel should show "Stale" or unavailable, not crash
```

### I7: LiDAR Stale

```
1. With stack running, unplug LiDAR USB adapter
2. Open web console
3. Within 1s, scan status should show "Stale"
```

### I9: Odometry 1m Test

```
1. Place robot at a measured start line on the floor
2. Mark 1m ahead
3. Drive forward via web console until robot reaches the 1m mark
4. Record /odom x value: ros2 topic echo /odom --once | grep -A2 position
5. Expected: x between 0.95 and 1.05
```

### I10: Heading 360-Degree Test

```
1. Record start yaw: ros2 topic echo /odom --once | grep -A4 orientation
2. Rotate robot 360 degrees (via web console or manual push)
3. Record end yaw
4. Error must be < 10 degrees (0.175 rad)
```

| Test | Result | Pass/Fail |
|------|--------|-----------|
| I1: IMU rate ~20 Hz | | |
| I2: IMU fail → available: false | | |
| I3: IMU recover → available: true | | |
| I4: INA238 available: true | | |
| I5: INA238 absent → graceful | | |
| I6: LiDAR rate 8-12 Hz | | |
| I7: LiDAR unplug → Stale | | |
| I8: imu_link in TF tree | | |
| I9: 1m accuracy < 5% | | |
| I10: 360° heading < 10° error | | |

---

## 5. Security Tests (W1–W5)

### W1: Loopback (on Pi)

```bash
# Launch web console on loopback (default)
./scripts/launch_web_console.sh port:=8081

# From the Pi itself:
curl -s -X POST http://127.0.0.1:8081/api/stop \
  -H "Content-Type: application/json" -d '{}'
# Expected: {"ok": true}
```

### W3–W4: Token Auth (on Pi)

```bash
# Set token and launch on LAN
export NAVBOT_WEB_TOKEN="test-secret-42"
./scripts/launch_web_console.sh port:=8081 host:=0.0.0.0

# From laptop — with correct token:
curl -s -X POST http://<pi-ip>:8081/api/stop \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-secret-42" -d '{}'
# Expected: {"ok": true}

# With wrong token:
curl -s -X POST http://<pi-ip>:8081/api/stop \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer wrong-token" -d '{}'
# Expected: HTTP 401, {"error": "missing or invalid bearer token"}
```

### W5: GET Always Open

```bash
curl -s http://<pi-ip>:8081/api/status | python3 -m json.tool | head -5
# Expected: valid JSON, HTTP 200, regardless of token
```

| Test | Result | Pass/Fail |
|------|--------|-----------|
| W1: loopback POST 200 | | |
| W3: correct token 200 | | |
| W4: wrong token 401 | | |
| W5: GET open 200 | | |

---

## 6. Soak Test Execution (8 Hours)

### 6.1 Setup

```bash
# Terminal 1: Full stack
source /opt/ros/jazzy/setup.bash
source /home/arif/ros2_ws/install/setup.bash
source ros2_ws/install/setup.bash
ros2 launch navbot_bringup imu_localization.launch.py

# Terminal 2: Web console
./scripts/launch_web_console.sh port:=8081

# Terminal 3: Soak monitoring (create this script first)
```

Create the soak monitor script:

```bash
cat > /tmp/soak_monitor.sh << 'SOAKEOF'
#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="$HOME/navbot_soak_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOG_DIR"
echo "Soak logging to: $LOG_DIR"

# Bridge health every 10s
(while true; do
  ros2 topic echo /base/bridge_health --once 2>/dev/null \
    >> "$LOG_DIR/bridge_health.jsonl" || true
  sleep 10
done) &

# Topic rates every 60s
(while true; do
  echo "--- $(date -Iseconds) ---" >> "$LOG_DIR/topic_rates.log"
  timeout 5 ros2 topic hz /odom --window 20 2>&1 | head -1 \
    >> "$LOG_DIR/topic_rates.log" || true
  timeout 5 ros2 topic hz /scan --window 20 2>&1 | head -1 \
    >> "$LOG_DIR/topic_rates.log" || true
  timeout 5 ros2 topic hz /imu/l3gd20_lsm303d/raw --window 20 2>&1 | head -1 \
    >> "$LOG_DIR/topic_rates.log" || true
  sleep 60
done) &

# System metrics every 30s
(while true; do
  echo "--- $(date -Iseconds) ---" >> "$LOG_DIR/system.log"
  free -m | head -2 >> "$LOG_DIR/system.log"
  cat /proc/loadavg >> "$LOG_DIR/system.log"
  cat /sys/class/thermal/thermal_zone0/temp >> "$LOG_DIR/system.log" 2>/dev/null || true
  journalctl -k --since "1 min ago" --no-pager 2>/dev/null \
    | grep -Ei "voltage|throttl|oom" >> "$LOG_DIR/kernel_warnings.log" || true
  sleep 30
done) &

trap "kill 0; echo 'Soak stopped. Logs: $LOG_DIR'" EXIT INT TERM
echo "Monitoring active. Press Ctrl+C to stop."
wait
SOAKEOF
chmod +x /tmp/soak_monitor.sh
```

```bash
# Terminal 3: Start monitoring
bash /tmp/soak_monitor.sh
```

### 6.2 During the Soak

- Do NOT drive the robot. Soak tests measure idle stability.
- Check SSH every 2 hours. Quick inspection:

```bash
# From laptop via SSH:
curl -s http://<pi-ip>:8081/api/status | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f'ROS alive: {d[\"ros_bridge_alive\"]}')
print(f'Base alive: {d[\"base_bridge_alive\"]}')
print(f'Scan alive: {d[\"scan\"][\"alive\"]}')
print(f'IMU alive: {d[\"imu\"][\"alive\"]}')
print(f'Power alive: {d[\"power\"][\"alive\"]}')
print(f'Uptime: {d[\"ros_uptime_sec\"]:.0f}s')
"
```

### 6.3 Hard Failure Thresholds (Auto-Fail)

| Condition | Threshold | Action |
|-----------|-----------|--------|
| `/odom` rate drops below 5 Hz | For > 60s | **SOAK FAIL** |
| `/scan` rate drops below 5 Hz | For > 60s | **SOAK FAIL** |
| Serial `checksum_failures` increases | By > 10 in any 1h window | **SOAK FAIL** |
| `serial_connected` goes false | For > 10s | **SOAK FAIL** |
| Free memory drops below 100 MB | At any point | **SOAK FAIL** |
| Pi temperature exceeds 80°C | At any point | **SOAK FAIL** |
| Any kernel voltage warning | Any occurrence | **SOAK FAIL** |
| `reconnect_count` increases | By > 3 in any 1h window | **SOAK FAIL** |
| Serial latency exceeds 50ms | For > 5 consecutive samples | **SOAK FAIL** |

### 6.4 Post-Soak Analysis

After the soak completes (8h+ without Ctrl+C interruption):

```bash
cd $HOME/navbot_soak_*  # most recent

echo "=== Disconnections ==="
grep -c '"serial_connected": false' bridge_health.jsonl 2>/dev/null || echo "0"

echo "=== Checksum Failures ==="
python3 -c "
import json
lines = [json.loads(l) for l in open('bridge_health.jsonl') if l.strip()]
if lines:
    start, end = lines[0].get('checksum_failures',0), lines[-1].get('checksum_failures',0)
    print(f'start={start} end={end} delta={end-start}')
else:
    print('no data')
"

echo "=== Memory Trend ==="
grep 'Mem:' system.log | awk '{print $4}' | python3 -c "
import sys
v = [int(l) for l in sys.stdin if l.strip()]
if v: print(f'start={v[0]}MB end={v[-1]}MB min={min(v)}MB delta={v[-1]-v[0]}MB')
"

echo "=== Kernel Warnings ==="
wc -l < kernel_warnings.log 2>/dev/null || echo "0 lines"
cat kernel_warnings.log 2>/dev/null || true

echo "=== Topic Rate Summary ==="
grep 'average rate' topic_rates.log | sort | uniq -c | sort -rn | head -10
```

| Metric | Value | Pass/Fail |
|--------|-------|-----------|
| Duration (hours) | | min 8h |
| Disconnections | | must be 0 |
| Checksum failure delta | | must be 0 |
| Memory delta | | must be < 50 MB |
| Min free memory | | must be > 100 MB |
| Kernel warnings | | must be 0 |
| /odom min rate | | must be > 5 Hz |
| /scan min rate | | must be > 5 Hz |

---

## 7. Residual Risk Classification

| # | Risk | Classification | Detection | Workaround |
|---|------|---------------|-----------|------------|
| R1 | Firmware zombie on USB disconnect | **ACCEPTABLE** | Watchdog hardware reset reboots RP2040 within 200ms. Pi bridge detects disconnect. | If RP2040 appears unresponsive, power cycle it. Firmware re-inits all peripherals on reboot. |
| R2 | IMU/INA238 data without range validation | **REQUIRES FUTURE FIX** | Currently undetectable — corrupt data looks normal. | Operator must visually sanity-check IMU heading and power values in web console. If values are clearly wrong (heading jumping, voltage reading 0 or 200V), restart the IMU/power nodes. Add range validation in next release. |
| R3 | ROS thread death not detected by web server | **MITIGATED** | `/base/bridge_health` topic will stop updating if ROS thread is dead. Soak test monitors topic rate. | Operator checks web console: if all topic ages are growing but ROS status says "Alive", restart the web console process. Add `is_alive()` check in next release. |
| R4 | Serial checksum failure no recovery threshold | **ACCEPTABLE** | Checksum failures tracked in `/base/bridge_health`. Soak test threshold catches persistent issues. | If checksum failures accumulate during operation, restart the serial bridge node. |
| R5 | Multiple-asterisk checksum edge case | **ACCEPTABLE** | Would require malicious input; not possible from Pi bridge (appends single `*XX`). Bench terminal operator would need to intentionally craft such input. | No action needed. Only affects manual debugging sessions. |
| R6 | imu_link URDF position estimated | **ACCEPTABLE** | EKF fusion quality depends on this. Validated during I10 heading test. | If I10 heading test fails, measure actual IMU position on chassis and update the URDF origin. |
| R7 | Handshake 1.5s startup delay | **ACCEPTABLE** | Normal behavior. Bridge logs show the delay. | No action needed. Only affects initial connection time. |
| R8 | Token auth lockout | **ACCEPTABLE** | Loopback (127.0.0.1) always works without token. | SSH to Pi, access web console via loopback. Delete corrupt `~/.navbot_web_token` if needed. |

---

## 8. Deployment Decision Framework

### GO Criteria (All Required)

All of the following must be true:

- [ ] **Safety S1–S8**: All 8 tests passed
- [ ] **Communication C1–C10**: All 10 tests passed
- [ ] **Sensors I1–I8**: All 8 liveness/failure/recovery tests passed
- [ ] **Integration I9**: 1m odometry error < 5%
- [ ] **Integration I10**: 360° heading error < 10°
- [ ] **Security W1, W3–W5**: Token auth working correctly
- [ ] **Soak test**: 8h+ with zero hard failures
- [ ] **Unit tests**: 84 passed, 0 failed
- [ ] **Firmware version**: PING returns 1.2.0

### NO-GO Triggers (Any One = Block)

- Any safety test (S1–S8) fails
- Watchdog does not reboot the RP2040 (S2 fail)
- ESTOP race test has any false clear (S4 fail)
- Checksum failures during soak > 10
- Any disconnection during soak lasting > 10s
- Memory leak > 50 MB over 8h soak
- Any kernel voltage warning during soak
- Odometry 1m error > 10% (double the threshold = systematic calibration problem)
- Heading 360° error > 20° (double the threshold)

### CONDITIONAL GO (Allowed Limitations)

The system may be deployed with the following known limitations:

1. **Supervised operation only** — operator must be able to reach ESTOP or power switch
2. **Maximum 8-hour continuous runtime** — restart daily until 24h soak passes
3. **IMU/power data not range-validated** — operator visually verifies reasonableness
4. **No autonomous navigation** — teleop and SLAM mapping only; Nav2 not validated

---

## 9. First Deployment Operating Rules

### Supervision

- **First 48 hours**: operator within arm's reach of power switch at all times during motion
- **After 48 hours with no incidents**: operator within line of sight
- **After 1 week with no incidents**: unattended operation allowed (with remote monitoring via web console)

### Runtime Limits

| Period | Max Continuous Runtime | Restart Required |
|--------|----------------------|-----------------|
| First week | 8 hours | Daily restart |
| Week 2+ (if clean) | 24 hours | Daily restart |
| After passing 24h soak | Unlimited | Weekly restart recommended |

### Safety Precautions

1. Always verify ESTOP button is functional before each session (press + release + RESET)
2. Never leave motors powered without the web console or serial terminal active
3. If any `STALL` or `ESTOP` fault occurs, investigate before resetting — don't blindly clear faults
4. If the web console shows "Stale" on the base bridge for > 5 seconds, stop all operations and check serial link
5. If power telemetry shows bus voltage below 3.0V, stop immediately — power supply failing

### Rollback Plan

If the upgraded firmware or software causes any issue not seen with the previous version:

```bash
# 1. Flash the archived pre-upgrade firmware.uf2
#    (archived before Phase 1 flash)

# 2. Revert Pi code to the initial commit
git checkout 1592bea -- ros2_ws/

# 3. Rebuild
./scripts/build_ros2_ws.sh

# 4. Verify with PING + STOP bench test
```

---

## 10. Post-Deployment Monitoring Plan

### Daily Review (5 minutes)

```bash
# SSH to Pi, check overnight health:
curl -s http://127.0.0.1:8081/api/status | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f'Uptime: {d[\"ros_uptime_sec\"]/3600:.1f}h')
print(f'Base: {d[\"base_bridge_alive\"]}')
print(f'Scan: {d[\"scan\"][\"alive\"]}')
print(f'IMU: {d[\"imu\"][\"alive\"]}')
print(f'Controller: {d[\"controller\"][\"state\"]}')
"

# Check bridge health
ros2 topic echo /base/bridge_health --once 2>/dev/null | python3 -c "
import json, sys
d = json.loads(sys.stdin.readline().split('data: ')[1].strip(\"'\"))
print(f'FW: {d[\"firmware_version\"]}')
print(f'Reconnects: {d[\"reconnect_count\"]}')
print(f'Checksum fails: {d[\"checksum_failures\"]}')
print(f'Latency: {d[\"last_latency_ms\"]}ms')
"

# Check kernel for power issues
journalctl -k --since "24 hours ago" --no-pager | grep -Ei "voltage|throttl" | tail -5
```

### Degradation Signals (Escalate Immediately)

| Signal | Meaning | Action |
|--------|---------|--------|
| `reconnect_count` growing daily | USB link unstable | Inspect cable, check Pi USB power |
| `checksum_failures` > 0 | Serial data corruption | Check for EMI sources, inspect cable shielding |
| Serial latency > 20ms | USB congestion or Pi CPU load | Check `top`, reduce non-robot workloads |
| `/scan` rate dropping | LiDAR or CP2102 degradation | Check LiDAR power, restart sllidar_node |
| Free memory trending down | Memory leak | Capture `smem` output, file issue |
| Controller state stuck in TIMEOUT | Bridge sending but firmware not receiving | Restart bridge, check serial path |

### Weekly Tasks

1. Review soak logs from the past week
2. Check disk usage in `~/navbot_captures/` — prune old captures
3. Compare serial latency trend to baseline from validation soak
4. Verify firmware version still matches expected (PING check)
5. Run unit tests on any code changes: `pytest tests/ -v`

---

## 11. Validation Record Template

Record the date, operator, and result of each test. This document becomes the deployment approval artifact.

```
Date: ____________________
Operator: ____________________
Firmware: 1.2.0  Confirmed: [ ]
Unit tests: 84 passed  Confirmed: [ ]

SAFETY TESTS
  S1 Watchdog USB-unplug:    [ ] PASS  [ ] FAIL
  S2 Watchdog reboot:        [ ] PASS  [ ] FAIL
  S3 ESTOP hardware:         [ ] PASS  [ ] FAIL
  S4 ESTOP race (50x):       [ ] PASS  [ ] FAIL  False clears: ___
  S5 ESTOP recovery:         [ ] PASS  [ ] FAIL
  S6 USB disconnect bridge:  [ ] PASS  [ ] FAIL
  S7 Command timeout:        [ ] PASS  [ ] FAIL
  S8 Stall detection:        [ ] PASS  [ ] FAIL

COMMUNICATION TESTS
  C1 Valid checksum:          [ ] PASS  [ ] FAIL
  C2 Wrong checksum:          [ ] PASS  [ ] FAIL
  C3 No checksum:             [ ] PASS  [ ] FAIL
  C4 Truncated checksum:      [ ] PASS  [ ] FAIL
  C6 Reconnect handshake:     [ ] PASS  [ ] FAIL
  C7 Firmware version:        [ ] PASS  [ ] FAIL
  C8 DIAG idle:               [ ] PASS  [ ] FAIL
  C9 DIAG under load:         [ ] PASS  [ ] FAIL
  C10 Line overflow:          [ ] PASS  [ ] FAIL

SENSOR TESTS
  I1 IMU alive:               [ ] PASS  [ ] FAIL  Rate: ___ Hz
  I2 IMU failure:             [ ] PASS  [ ] FAIL
  I3 IMU recovery:            [ ] PASS  [ ] FAIL
  I4 INA238 alive:            [ ] PASS  [ ] FAIL
  I5 INA238 absent:           [ ] PASS  [ ] FAIL
  I6 LiDAR alive:             [ ] PASS  [ ] FAIL  Rate: ___ Hz
  I7 LiDAR stale:             [ ] PASS  [ ] FAIL
  I8 TF imu_link:             [ ] PASS  [ ] FAIL

INTEGRATION TESTS
  I9  1m accuracy:            [ ] PASS  [ ] FAIL  Measured x: ___ m
  I10 360° heading:           [ ] PASS  [ ] FAIL  Error: ___ deg

SECURITY TESTS
  W1 Loopback POST:           [ ] PASS  [ ] FAIL
  W3 Correct token:           [ ] PASS  [ ] FAIL
  W4 Wrong token:             [ ] PASS  [ ] FAIL
  W5 GET always open:         [ ] PASS  [ ] FAIL

SOAK TEST
  Duration:                   ___ hours
  Disconnections:             ___
  Checksum failure delta:     ___
  Memory delta:               ___ MB
  Min free memory:            ___ MB
  Kernel warnings:            ___
  Min /odom rate:             ___ Hz
  Min /scan rate:             ___ Hz

DECISION
  [ ] GO — all criteria met
  [ ] CONDITIONAL GO — with limitations: ___________________
  [ ] NO-GO — blocked by: ___________________

Signed: ____________________  Date: ____________________
```
