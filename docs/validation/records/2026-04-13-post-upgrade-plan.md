# Post-Upgrade Validation & Stabilization Plan

Firmware v1.2.0 — Phases 1-5 complete — April 2026

---

## 1. System Risk Assessment (Post-Upgrade)

### 1.1 Residual Risks From Implementation

| Risk | Root Cause | Severity | Discovery Phase |
|------|-----------|----------|----------------|
| **DIAG telemetry truncation** | `snprintf` into 128-byte buffer; worst-case DIAG payload is ~141 bytes. Truncated line produces invalid checksum on Pi side. | HIGH | Post-Phase 4 code review |
| **Watchdog mode is software-only** | `watchdog_enable(200, false)` — second arg `false` means the Pico SDK treats this as a software watchdog. On true hang (e.g., hard fault), behavior depends on SDK version. | MEDIUM | Post-Phase 1 code review |
| **Firmware zombie state on USB disconnect** | After USB drops, firmware keeps running indefinitely — watchdog kicked, telemetry printed to nowhere, no recovery path until power cycle. | MEDIUM | Post-Phase 1 code review |
| **No RP2040 restart detection in odometry** | If RP2040 reboots (watchdog, power glitch), encoder counts jump from N to 0. Delta of -N is integrated as large backward motion. | HIGH | Post-Phase 3 code review |
| **IMU/INA238 data published without range validation** | Corrupt I2C reads produce plausible but wrong sensor values that propagate to EKF and web console. | HIGH | Post-Phase 5 code review |
| **ROS thread death not detected by web server** | If `executor.spin()` crashes, HTTP server keeps serving stale snapshots indefinitely. | HIGH | Post-Phase 4 code review |
| **Serial checksum failure has no recovery threshold** | Unlimited corrupt lines are silently discarded. A noisy serial link appears "connected" but produces no odometry. | MEDIUM | Post-Phase 3 code review |
| **Multiple-asterisk checksum bypass** | `strrchr(line, '*')` finds only the rightmost `*`. Input like `PING*XX*YY` validates YY against `PING*XX` as payload. | LOW | Post-Phase 3 code review |

### 1.2 New Risks Introduced by Upgrades

| Risk | Introduced By | Mitigation |
|------|--------------|------------|
| Handshake timeout blocks bridge startup by 1.5s | Phase 3 reconnect handshake | Acceptable — only on connect |
| PING every 5s adds serial traffic | Phase 4 latency measurement | Negligible at 115200 baud (~0.1% utilization) |
| Token auth could lock out operator if token file is corrupt | Phase 5 security | Loopback bypass always works; token is optional |
| `imu_link` URDF position is estimated, not measured | Phase 4 URDF fix | Must be verified on physical robot before EKF tuning |

### 1.3 Integration Risks Not Caught by Unit Tests

The 81 unit tests validate math and protocol parsing in isolation. They do **not** cover:

- Actual serial timing and buffer behavior between Pi and RP2040
- ROS topic latency under CPU load
- I2C bus contention between IMU and INA238 at runtime
- Web console behavior during concurrent drive + capture + status poll
- Thread safety of `WebConsoleNode` snapshot under concurrent HTTP requests
- Firmware behavior after watchdog-caused reboot (clean re-init?)

---

## 2. Critical Validation Test Matrix

### 2.1 Safety Tests (Must Pass Before Any Motion)

| # | Test | Scenario | Expected Behavior | Pass Criteria |
|---|------|---------|-------------------|---------------|
| S1 | Watchdog stop | Start `CMD_VEL 0.15 0.0`, unplug USB cable | Motors coast to stop | Motor PWM at 0 within 250ms of unplug (oscilloscope or visual) |
| S2 | Watchdog reboot | Hold BOOTSEL to verify post-watchdog state | After watchdog fires, RP2040 reboots and responds to PING | `ACK PING 1.2.0*XX` within 2s of USB reconnect |
| S3 | ESTOP hardware | Press ESTOP during `CMD_VEL 0.15 0.0` | Immediate motor stop, STATE shows ESTOP | Motors at 0 within 1 control cycle (10ms). `STATE ESTOP ESTOP*XX` received. |
| S4 | ESTOP race | Hold ESTOP button, send `RESET` 50 times in scripted loop | Every RESET returns error | 50/50 responses are `ERR ESTOP_HELD*XX`. Zero false clears. |
| S5 | ESTOP recovery | Press ESTOP, release, send `RESET` | Firmware clears fault | `ACK RESET*XX`, then `CMD_VEL` works normally |
| S6 | USB disconnect stop | Start motion, disconnect USB, reconnect | Motion stopped, bridge reconnects with handshake | Pi bridge logs "connected" with firmware version. Motors were stopped. |
| S7 | Command timeout | Send `CMD_VEL 0.10 0.0`, wait 600ms without any command | Motors stop at 500ms | `STATE TIMEOUT CMD_TIMEOUT*XX` in telemetry stream |
| S8 | Stall detection | Mechanically block wheel during `CMD_VEL 0.15 0.0` | Stall detected, fault latched | `STATE FAULT STALL*XX` within `STALL_TIMEOUT_MS + STALL_STARTUP_GRACE_MS` |

### 2.2 Communication Tests

| # | Test | Scenario | Expected Behavior | Pass Criteria |
|---|------|---------|-------------------|---------------|
| C1 | Valid checksum | Send `PING*10` (correct XOR for PING) | Accepted | `ACK PING 1.2.0*XX` response |
| C2 | Wrong checksum | Send `PING*00` | Rejected | `ERR BAD_CHECKSUM*XX` response |
| C3 | No checksum | Send `PING` (bare, no `*`) | Accepted (backward compat) | `ACK PING 1.2.0*XX` response |
| C4 | Truncated checksum | Send `PING*A` | Rejected | `ERR BAD_CHECKSUM*XX` response |
| C5 | Corrupt ODOM detection | Monitor `/base/bridge_health`, inject noise on serial | Checksum failures increment | `checksum_failures > 0` in health JSON |
| C6 | Reconnect handshake | Kill and restart serial bridge node | Bridge sends STOP+PING, verifies ACK | Bridge logs firmware version on reconnect |
| C7 | Firmware version | Send `PING` after flash | Version in response | Response contains `1.2.0` |
| C8 | DIAG command | Send `DIAG` while motors idle | Diagnostic output | `DIAG <stamp> L:0,...,0 R:0,...,0*XX` — verify line is not truncated |
| C9 | DIAG under load | Send `DIAG` while motors running | Diagnostic with non-zero values | duty, setpoint, and filtered CPS are non-zero and parseable |
| C10 | Line overflow | Send 130-byte line | Firmware rejects | `ERR LINE_TOO_LONG*XX` response |

### 2.3 Sensor & Integration Tests

| # | Test | Scenario | Expected Behavior | Pass Criteria |
|---|------|---------|-------------------|---------------|
| I1 | IMU alive | Launch `imu_localization.launch.py` | IMU publishes at 20 Hz | `ros2 topic hz /imu/l3gd20_lsm303d/raw` shows ~20 Hz |
| I2 | IMU I2C failure | Disconnect IMU from I2C bus during operation | Error logged, status shows unavailable | `/imu/l3gd20_lsm303d/status` shows `available: false`. No crash. |
| I3 | IMU recovery | Reconnect IMU after I2C failure | Readings resume | Status returns to `available: true` within 5 seconds |
| I4 | INA238 alive | Check power topic | INA238 publishes at 2 Hz | `ros2 topic echo /power/ina238/status --once` shows `available: true` |
| I5 | INA238 absent | Launch without INA238 connected | Graceful degradation | Status shows `available: false`, no crash, web console renders |
| I6 | LiDAR alive | Check scan topic | `/scan` at ~10 Hz | `ros2 topic hz /scan` shows 8-12 Hz |
| I7 | LiDAR stale | Unplug LiDAR USB mid-operation | `/scan` goes stale, web console shows "Stale" | Web status scan.alive = false within `topic_stale_timeout` |
| I8 | EKF TF chain | Launch EKF, check TF | `imu_link` in tree | `ros2 run tf2_tools view_frames` shows imu_link → base_link |
| I9 | Odometry 1m test | Drive robot forward 1m (measured), compare to /odom | Pose x ≈ 1.0m | Error < 5% (0.05m) |
| I10 | Heading test | Rotate 360 degrees, compare start/end yaw | yaw ≈ 0 (returned to start) | Error < 10 degrees |

### 2.4 Security & Web Console Tests

| # | Test | Scenario | Expected Behavior | Pass Criteria |
|---|------|---------|-------------------|---------------|
| W1 | Loopback no auth | `curl -X POST http://127.0.0.1:8080/api/stop -d '{}'` | Succeeds | HTTP 200 |
| W2 | LAN without token | Launch with `host:=0.0.0.0`, no token set. `curl -X POST http://pi-ip:8080/api/stop -d '{}'` | Succeeds (no token = no auth enforced) but warning logged | HTTP 200, warning in logs |
| W3 | LAN with token | Set `NAVBOT_WEB_TOKEN=secret`, `curl -X POST ... -H "Authorization: Bearer secret"` | Succeeds | HTTP 200 |
| W4 | LAN wrong token | Set token, send wrong bearer | Rejected | HTTP 401 |
| W5 | GET always open | `curl http://pi-ip:8080/api/status` with token enabled | Succeeds | HTTP 200 with valid JSON |
| W6 | Drive key stop | Press W (forward), release W | Robot moves forward then stops | Motion visible, stop within `command_hold_timeout` of key release |
| W7 | Capture start/stop | Start capture, wait 10s, stop | Bag files created | `capture_meta.json` has `return_code: 0` |

---

## 3. Fault Injection Plan

### 3.1 Firmware (RP2040)

| Injection | Method | Expected Response | Verification |
|-----------|--------|-------------------|-------------|
| **Main loop hang** | Add `while(1){}` after `watchdog_update()` (test build only) | Watchdog fires, RP2040 reboots | Pi bridge detects disconnect, re-handshakes after reboot |
| **Stalled encoder** | Disconnect one encoder cable during motion | Stall detection triggers after grace period | `STATE FAULT STALL*XX` within ~1.3s (800ms grace + 500ms stall timeout) |
| **Corrupted inbound command** | Send `CMD_VEL 0.10 0.00*FF` (wrong checksum) | Firmware rejects | `ERR BAD_CHECKSUM*XX` |
| **Partial line** | Send `CMD_V` then wait 5s then send `EL 0.10 0.0\n` | Parser receives `CMD_VEL 0.10 0.0` (no newline reset) | Verify: does partial line accumulate correctly or get flushed? The firmware buffer accumulates chars until `\n`. If a partial line sits in the buffer, the next chars append to it. This is correct behavior but means a 5s-old partial line combines with fresh data. |
| **Rapid command flood** | Send 1000 `PING\n` in <1s | All processed, no buffer overflow | 1000 `ACK PING*XX` responses, no `LINE_TOO_LONG` errors |
| **DIAG during ESTOP** | Trigger ESTOP, then send `DIAG` | DIAG returns with zero duty, fault visible in STATE | `DIAG` shows duty=0 for both wheels |

### 3.2 Communication Link

| Injection | Method | Expected Response | Verification |
|-----------|--------|-------------------|-------------|
| **USB disconnect/reconnect** | Unplug USB cable for 3s, replug | Bridge reconnects with handshake | Bridge logs new connection with firmware version, `/odom` resumes |
| **Rapid disconnect cycle** | Unplug/replug 10 times in 30s | Bridge reconnects each time | `reconnect_count` in health topic increments to 10+ |
| **Serial noise** | Short the serial lines briefly with a jumper wire | Checksum failures detected | `checksum_failures` increments in `/base/bridge_health` |
| **Baud rate mismatch** | Open port at 9600 on Pi while firmware is at 115200 | Handshake fails, bridge retries | Bridge logs "handshake failed: no ACK PING received" |

### 3.3 ROS2 / Pi Side

| Injection | Method | Expected Response | Verification |
|-----------|--------|-------------------|-------------|
| **Kill serial bridge** | `ros2 lifecycle set navbot_serial_bridge shutdown` or `kill -9` | `/odom` stops, web console shows "Stale" | Operator notices within `topic_stale_timeout` (1s) |
| **Kill web console** | `kill -9` the web console process | HTTP returns connection refused | Robot stops (web console sends STOP on shutdown if clean; on SIGKILL, firmware timeout stops motors at 500ms) |
| **CPU overload** | `stress --cpu 4` on Pi during operation | Topic rates may drop | Verify `/odom` stays above 5 Hz, `/scan` stays above 5 Hz, serial latency stays below 50ms |
| **Memory pressure** | `stress --vm 2 --vm-bytes 512M` during operation | System remains responsive | No OOM kills on ROS nodes (check `dmesg`) |
| **Kill ROS executor thread** | Not easily injectable in production — simulate with `Thread.join()` timeout test | Web server continues, serves stale data | **Known gap**: no detection mechanism exists. Document as risk. |

---

## 4. Long-Duration Soak Test Plan (8-24 Hours)

### 4.1 Test Setup

```
Hardware:
- Navbot on a flat surface (wheels on blocks or free to spin)
- RP2040 connected via USB to Pi 5
- RPLIDAR C1 powered and connected
- INA238 on I2C bus 1
- IMU on I2C bus 1
- Pi connected to WiFi for SSH monitoring
- Web console accessible on port 8081

Software:
- imu_localization.launch.py running
- Web console running on port 8081
- Capture running for full duration

Duration: 8 hours minimum, 24 hours target
```

### 4.2 Soak Test Script

Create `scripts/soak_test.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

DURATION_HOURS="${1:-8}"
DURATION_SEC=$((DURATION_HOURS * 3600))
LOG_DIR="$HOME/navbot_soak_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOG_DIR"

echo "Soak test: ${DURATION_HOURS}h, logging to ${LOG_DIR}"

# Background: record bridge health every 10s
while true; do
  ros2 topic echo /base/bridge_health --once 2>/dev/null >> "${LOG_DIR}/bridge_health.jsonl"
  sleep 10
done &
HEALTH_PID=$!

# Background: record topic rates every 60s
while true; do
  echo "--- $(date -Iseconds) ---" >> "${LOG_DIR}/topic_rates.log"
  timeout 5 ros2 topic hz /odom --window 20 2>&1 | head -1 >> "${LOG_DIR}/topic_rates.log"
  timeout 5 ros2 topic hz /scan --window 20 2>&1 | head -1 >> "${LOG_DIR}/topic_rates.log"
  timeout 5 ros2 topic hz /imu/l3gd20_lsm303d/raw --window 20 2>&1 | head -1 >> "${LOG_DIR}/topic_rates.log"
  sleep 60
done &
RATES_PID=$!

# Background: record Pi system metrics every 30s
while true; do
  echo "--- $(date -Iseconds) ---" >> "${LOG_DIR}/system.log"
  free -m | head -2 >> "${LOG_DIR}/system.log"
  cat /proc/loadavg >> "${LOG_DIR}/system.log"
  cat /sys/class/thermal/thermal_zone0/temp >> "${LOG_DIR}/system.log" 2>/dev/null || true
  journalctl -k --since "1 min ago" --no-pager 2>/dev/null | grep -Ei "voltage|throttl|oom" >> "${LOG_DIR}/kernel_warnings.log" || true
  sleep 30
done &
SYS_PID=$!

# Background: periodic DIAG command every 5 minutes
while true; do
  python3 -c "
import serial, time
try:
    s = serial.Serial('/dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00', 115200, timeout=1)
    s.write(b'DIAG\n')
    time.sleep(0.2)
    while s.in_waiting:
        print(s.readline().decode('utf-8', errors='replace').strip())
    s.close()
except Exception as e:
    print(f'DIAG failed: {e}')
" >> "${LOG_DIR}/diag.log" 2>&1
  sleep 300
done &
DIAG_PID=$!

cleanup() {
  kill $HEALTH_PID $RATES_PID $SYS_PID $DIAG_PID 2>/dev/null || true
  echo "Soak test complete. Logs in ${LOG_DIR}"
}
trap cleanup EXIT INT TERM

sleep "$DURATION_SEC"
```

### 4.3 Monitoring Metrics & Failure Detection Rules

| Metric | Source | Normal Range | Failure Threshold |
|--------|--------|-------------|-------------------|
| `/odom` rate | topic_rates.log | 9-11 Hz | < 5 Hz for > 60s |
| `/scan` rate | topic_rates.log | 8-12 Hz | < 5 Hz for > 60s |
| `/imu` rate | topic_rates.log | 18-22 Hz | < 10 Hz for > 60s |
| Serial latency | bridge_health.jsonl | 1-10ms | > 50ms for > 5 samples |
| Checksum failures | bridge_health.jsonl | 0 | > 10 in any 1-hour window |
| Reconnect count | bridge_health.jsonl | 0-1 (initial) | > 3 in any 1-hour window |
| Pi free memory | system.log | > 200MB | < 100MB (memory leak) |
| Pi CPU load | system.log | < 3.0 | > 3.5 sustained 10 min |
| Pi temperature | system.log | < 75C | > 80C |
| Kernel voltage warnings | kernel_warnings.log | 0 | Any occurrence |
| Bridge connected | bridge_health.jsonl | true | false for > 10s |

### 4.4 Post-Soak Analysis Procedure

```bash
# 1. Check for any disconnections
grep '"serial_connected": false' bridge_health.jsonl | wc -l

# 2. Check checksum failure trend
python3 -c "
import json, sys
failures = []
for line in open('bridge_health.jsonl'):
    try:
        d = json.loads(line.strip())
        failures.append(d.get('checksum_failures', 0))
    except: pass
if failures:
    print(f'Checksum failures: start={failures[0]}, end={failures[-1]}, delta={failures[-1]-failures[0]}')
"

# 3. Check memory trend
grep 'Mem:' system.log | awk '{print $4}' | python3 -c "
import sys
vals = [int(l) for l in sys.stdin if l.strip()]
if vals:
    print(f'Free memory: start={vals[0]}MB, end={vals[-1]}MB, min={min(vals)}MB, delta={vals[-1]-vals[0]}MB')
"

# 4. Check for any kernel warnings
cat kernel_warnings.log

# 5. Verify all topic rates were in range
grep 'average rate' topic_rates.log | sort | uniq -c | sort -rn | head -20
```

---

## 5. Observability Verification

### 5.1 Current Observability Coverage

| Layer | What's Monitored | What's Missing |
|-------|-----------------|----------------|
| **Firmware** | STATE, ODOM, DIAG, ERR telemetry | No uptime counter, no boot reason (watchdog vs power-on), no PIO FIFO overflow count |
| **Serial link** | Checksum failures, latency, reconnect count | No byte-level error rate, no throughput measurement, no consecutive-failure threshold |
| **Odometry** | Position, velocity, joint states | No odometry drift estimation, no reset detection |
| **IMU** | Raw data + status + YPR | No range validation, no jitter detection, no sample-to-sample delta monitoring |
| **Power** | Voltage, current, power, temperature | No range validation, no trend (voltage dropping over time), no low-battery alert |
| **Web console** | All topic liveness | No ROS thread health check, no connection count, no request latency |
| **System** | Nothing built-in | No CPU/memory/temperature monitoring from within ROS |

### 5.2 Recommended Additions (Prioritized)

**Must-have before deployment:**

1. **RP2040 restart detection in odometry** — If `left_count` or `right_count` jumps backward by more than 10,000 counts in one sample, reset the odometry integrator and log a warning. This catches watchdog reboots and power glitches.

2. **DIAG buffer size increase** — Change `NAVBOT_PROTOCOL_MAX_LINE` from 128 to 192, or shorten the DIAG format to stay under 128 bytes. The current format truncates at worst-case values.

3. **Consecutive checksum failure threshold** — If 10 consecutive lines fail checksum, close and reopen the serial port. This catches a degraded link that otherwise appears "connected."

**Should-have for production:**

4. **IMU range validation** — Reject samples where |angular_velocity| > 10 rad/s or |linear_acceleration| > 50 m/s^2. Publish the previous valid sample instead.

5. **INA238 range validation** — Flag bus_voltage outside 2.5-6.0V range. Flag current outside 0-15A range.

6. **ROS thread liveness check** — In `_health_timer_callback`, check `ros_thread.is_alive()` and include it in health JSON.

---

## 6. Regression Detection Strategy

### 6.1 Current CI Coverage

| Layer | Coverage | Gap |
|-------|---------|-----|
| Odometry math | 11 tests | No restart-jump test, no long-sequence drift test |
| Serial parser | 25 tests (with checksum) | No fuzz testing, no multiple-asterisk test |
| PID controller | 24 tests | No large-dt test, no measurement-noise test |
| Checksum | 21 tests | Good coverage |
| Firmware build | Not in CI | Cross-compilation not verified |
| ROS build (`colcon`) | In CI but untested (no ROS container yet) | Needs ROS Jazzy Docker image |

### 6.2 Recommended CI Additions

**Immediate (before deployment):**

1. Add `test_odometry.py::TestRestartDetection` — verify that a count jump from 50000 to 0 doesn't produce a 12m backward motion
2. Add `test_serial_parser.py::TestMultipleAsterisks` — verify `PING*XX*YY` behavior
3. Add `test_pid.py::TestLargeDt` — verify integral doesn't explode with dt=5.0

**Post-deployment:**

4. Rosbag replay regression — store a reference capture, replay through odometry, compare output to a golden reference within tolerance
5. Firmware build in CI — add ARM GCC cross-compilation to the pipeline using `pico-sdk` Docker image

### 6.3 Version Gate Rule

Before any firmware flash to the robot:
1. All 81+ unit tests pass
2. Firmware builds without warnings (`-Wall -Werror`)
3. PING returns expected version string
4. Bench ESTOP test passes (manual, non-skippable)

---

## 7. Pre-Deployment Fixes Required

Based on this validation analysis, the following issues **must be fixed before deployment**:

### Fix 1: DIAG buffer truncation (HIGH)

Increase `NAVBOT_PROTOCOL_MAX_LINE` to 192 in `navbot_protocol.h`, or shorten the DIAG format to use integer-scaled values (`%.0f` instead of `%.1f`, dropping one decimal place saves ~12 bytes).

### Fix 2: RP2040 restart detection in odometry (HIGH)

In `odometry.py`, before computing delta, check:
```python
if abs(left_delta) > self.left_counts_per_revolution * 10:
    # Likely RP2040 restart — reset integrator
    self._last_left_count = left_count
    self._last_right_count = right_count
    return previous_state  # Don't integrate the jump
```

### Fix 3: Watchdog mode (MEDIUM)

Change `watchdog_enable(200, false)` to `watchdog_enable(200, true)` so the watchdog triggers a real hardware reset. Verify that the RP2040 re-initializes cleanly after a watchdog reset (all peripherals, PIO, PWM, GPIO re-init in `main()`).

---

## 8. Go/No-Go Deployment Checklist

### Safety

- [ ] S1: Watchdog USB-unplug test — motors stop within 250ms
- [ ] S2: Watchdog reboot — firmware responds to PING after watchdog reset
- [ ] S3: ESTOP hardware — immediate motor stop
- [ ] S4: ESTOP race — 50/50 rejections with button held
- [ ] S5: ESTOP recovery — clean reset after release
- [ ] S6: USB disconnect — bridge reconnects with handshake
- [ ] S7: Command timeout — motors stop at 500ms
- [ ] S8: Stall detection — fault within expected window

### Communication

- [ ] C1-C4: Checksum validation (valid, wrong, bare, truncated)
- [ ] C6: Reconnect handshake verified
- [ ] C7: Firmware version 1.2.0 confirmed
- [ ] C8-C9: DIAG command works (idle and under load) — **verify no truncation**

### Sensors

- [ ] I1: IMU at ~20 Hz
- [ ] I2-I3: IMU I2C failure and recovery
- [ ] I4-I5: INA238 present and absent
- [ ] I6-I7: LiDAR alive and stale detection
- [ ] I8: `imu_link` in TF tree

### Integration

- [ ] I9: 1m odometry accuracy < 5% error
- [ ] I10: 360-degree heading accuracy < 10 degrees

### Security

- [ ] W1: Loopback POST works without token
- [ ] W3-W4: Token auth enforced on LAN
- [ ] W5: GET always open

### Soak Test

- [ ] 8-hour soak with no disconnections
- [ ] No checksum failures during soak
- [ ] Memory stable (no growth > 50MB over 8 hours)
- [ ] All topic rates in range for full duration
- [ ] No kernel voltage warnings

### Pre-Deployment Fixes

- [ ] **DIAG truncation fixed** (buffer or format)
- [ ] **Odometry restart detection added**
- [ ] **Watchdog mode verified** (true hardware reset recommended)

---

### Final Decision

**CONDITIONAL GO — validated 2026-04-13.**

All three blocking fixes were applied prior to validation:

1. **DIAG truncation** — `NAVBOT_PROTOCOL_MAX_LINE` increased to 192
2. **Odometry restart detection** — jump > 10 revolutions absorbed
3. **Watchdog mode** — changed to hardware reset (`watchdog_enable(200, true)`)

Bench validation: **33/33 tests passed** (S1-S8, C1-C10, I1-I10, W1-W5).

Soak test: **10.8 hours**, zero crashes, zero disconnections, zero checksum failures.

Remaining blocker is hardware power quality (undervoltage from adapter), not software.
See [VALIDATION_RECORD_20260413.md](VALIDATION_RECORD_20260413.md) for full results and deployment conditions.
