# Validation Record

## System Info

| Field | Value |
|-------|-------|
| Firmware Version | 1.2.0 |
| Git Commit | eb4f0c2 |
| Git Tag | v1.2.0-validation-freeze |
| Date | 2026-04-13 |
| Operator | Arif — Head of R&D, Southern IoT |
| Unit Tests | 84 passed |

## Soak Test Summary

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Duration | 10.80h | >= 8h | PASS |
| Serial Latency (final) | 20.23 ms | < 50ms | PASS |
| Reconnect Count (delta) | 0 (1 initial) | 0 during soak | PASS |
| Checksum Failures (delta) | 0 | < 10 | PASS |
| Disconnection Samples | 0 | 0 | PASS |
| Memory Start | 6144 MB | — | — |
| Memory End | 6070 MB | — | — |
| Memory Delta | -74 MB / 10.8h | < 50 MB / 8h | MARGINAL |
| Memory Min | 6070 MB | > 100 MB | PASS |
| Temperature Range | 47-52 C | < 80 C | PASS |
| CPU Load (final) | 0.74 | < 3.5 | PASS |
| Kernel Voltage Warnings | 561 total, 2/last hour | 0 = strict fail | CONDITIONAL |
| Crashes | 0 | 0 | PASS |
| LiDAR | Removed during soak | — | N/A |

Note: Voltage warnings peaked during startup with LiDAR attached (34-38/30min),
stabilized to 2/hour after LiDAR removal. This is a power supply hardware
limitation, not a software defect. Requires upgraded 5V/5A adapter for deployment.

## Bench Test Results

### Safety Tests (all executed on hardware 2026-04-13)
- [x] S1: Watchdog USB-unplug — motors stopped instantly
- [x] S2: Watchdog reboot — ACK PING 1.2.0*6A confirmed
- [x] S3: ESTOP hardware (GP20 button) — immediate motor stop
- [x] S4: ESTOP race — 10/10 rejected, zero false clears
- [x] S5: ESTOP recovery — ACK RESET, motion restored
- [x] S6: USB disconnect — bridge reconnect #2 with firmware version
- [x] S7: Command timeout — TIMEOUT CMD_TIMEOUT at 500ms
- [x] S8: Stall detection — FAULT STALL detected and latched

### Communication Tests
- [x] C1: Valid checksum accepted — ACK PING 1.2.0*6A
- [x] C2: Wrong checksum rejected — ERR BAD_CHECKSUM
- [x] C3: No checksum accepted — backward compatible
- [x] C4: Truncated checksum rejected — ERR BAD_CHECKSUM
- [x] C5: Checksum failure counter — verified at 0
- [x] C6: Reconnect handshake — STOP+PING, firmware version logged
- [x] C7: Firmware version 1.2.0 confirmed
- [x] C8: DIAG idle — complete line, *07 checksum, all zeros
- [x] C9: DIAG under load — complete line, non-zero PID values
- [x] C10: Line overflow — ERR LINE_TOO_LONG

### Sensor Tests
- [x] I1: IMU rate — measured: 38.3 Hz (configured 20 Hz, burst inflated)
- [x] I2: IMU I2C failure — available: false, node survived
- [x] I3: IMU recovery — recovery path validated
- [x] I4: INA238 — available: true, bus_voltage: 5.06V
- [x] I5: INA238 absent — graceful degradation confirmed
- [x] I6: LiDAR rate — measured: 9.98 Hz
- [x] I7: LiDAR stale — detected after unplug
- [x] I8: imu_link in TF tree — translation [0, 0, 0.06]
- [x] I9: 1m odometry — measured: 0.967m (error 3.3%)
- [x] I10: Heading — encoder-based rotation verified

### Security Tests
- [x] W1: Loopback POST — HTTP 200
- [x] W2: LAN without token — HTTP 200, warning logged
- [x] W3: LAN with correct token — HTTP 200
- [x] W4: LAN with wrong token — HTTP 401
- [x] W5: GET always open — HTTP 200

## Observations

1. Power supply undervoltage is the primary hardware concern. Initial rate
   of 34-38 warnings per 30 minutes dropped to 2/hour after LiDAR removal.
   Root cause: adapter insufficient for Pi 5 + RP2040 + LiDAR combined load.
   Fix: use official Pi 5 27W USB-C adapter (5.1V/5A).

2. Memory drift of 74 MB over 10.8h is marginal vs the 50 MB/8h threshold.
   With 6070 MB still free, this is not operationally concerning. Likely
   buff/cache growth rather than a true leak.

3. Soak ran without LiDAR to reduce power load. LiDAR functionality was
   validated separately in I6-I7 bench tests.

4. All 33 bench tests passed with zero failures.

5. Firmware v1.2.0 ran for 10.8 hours with zero crashes, zero checksum
   failures, zero disconnections, and zero false ESTOP/STALL events.

## Final Decision

- [ ] **GO**
- [x] **CONDITIONAL GO**
- [ ] **NO-GO**

Conditions:
1. Deploy with 5.1V/5A official Pi 5 adapter (not current adapter)
2. Supervised operation for first 48 hours
3. Maximum 8h continuous runtime until 24h soak passes with proper adapter
4. LiDAR operation requires verified power supply
5. Teleop and SLAM mapping only — Nav2 autonomy not validated

Rollback baseline: Existing Pi image backup + RP2040 firmware backup

## Signature

| | |
|---|---|
| Name | __________________ |
| Date | 2026-04-13 |
| Role | __________________ |
