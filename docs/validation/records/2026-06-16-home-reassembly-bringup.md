# Home Reassembly + Power Reconfig + Full Peripheral Bring-up (session 13)

**Date:** 2026-06-16
**Branch:** `navbot-experimental`
**Firmware:** v1.3.0 (unchanged; confirmed live `ACK PING 1.3.0`)
**Location:** Relocated office lab → **home**
**Access:** Pi `navbot-pi` @ 192.168.68.126 (user `arif`), all checks over SSH

## Summary

After a long pause and a relocation home, the robot was reassembled with a
new power architecture. A full peripheral bring-up was run; three reassembly
wiring faults were found and fixed, and the IMU (remounted flipped) was
reconfigured in software. The robot ended the session **fully
bench-operational**. No nav work was done; session-12 nav items remain
deferred and the office maps are now obsolete.

## Power architecture (new)

- 3S LiPo → 5V converter → **Pi 5 only**. `vcgencmd get_throttled` = `0x0`
  (no undervoltage). This retires the undervoltage condition that capped the
  earlier v1.2.0 validation at CONDITIONAL-GO.
- **INA238 moved** from the Pi 5V rail to the **motor power rail** (which
  also powers the Maker Pi RP2040). INA238 VBUS reads ~6.27 V — consistent
  with 6 V motors (confirm nominal).
- LiDAR separately powered.

## Bring-up results

| # | Subsystem | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Pi power | PASS | throttled=0x0, 41–64 °C, 7.3 GB free |
| 2 | RP2040 link | PASS | `ACK PING 1.3.0*6B`, `STATE IDLE OK`, /dev/ttyACM0 |
| 3 | Encoders | PASS | both channels count on hand-turn |
| 4 | INA238 | PASS (recal pending) | 0x40, DEVICE_ID 0x2381, VBUS 6.275 V |
| 5 | LiDAR | PASS | health OK, `/scan_raw` 9.97 Hz |
| 6 | IMU | PASS (after reconfig) | 0x19/0x69/0x1E, 50.0 Hz, all 3 sensors |
| 7 | Motors | PASS | closed-loop CMD_VEL fwd, L+2692/R+2681, no stall |

## Faults found and fixed

1. **RP2040 absent from USB.** Root cause: a **charge-only USB cable** (a
   30 s live plug watch showed zero enumeration events). Swapped to a data
   cable → enumerated instantly (2e8a:000a Pico, SN E661410403114B35).
   Lesson: zero kernel USB events on replug = power-only cable, not firmware.
2. **Left motor direction inverted** (forward cmd → reverse encoder, and
   closed-loop runaway). Fixed by user rewiring.
3. **Right motor dead, then inverted.** Initially no drive at any duty
   (loose **M1** lead); after reseating it drove but reversed; user swapped
   the M1 motor leads and reseated firmly → correct direction. The earlier
   `FAULT STALL` was correct behaviour (right wheel commanded, not moving).

Diagnosis used `TEST_PWM <l> <r>` (raw duty, PID-bypassed, 1 s auto-stop) to
isolate each motor without closed-loop runaway. Final closed-loop
`CMD_VEL 0.05 0.0`: both wheels forward, encoders matched to ~0.4 %, no
stall/runaway.

## IMU reconfigure (flipped mount)

The IMU was reinstalled **flipped 180° about the forward (X) axis** (accel_z
read −10.99, roll ≈ 176° vs the calibrated Z-up). Decision: keep the mount,
reconfigure in software.

- Added driver orientation mode **`x_forward_flipped`** =
  `(sensor_x, −sensor_y, −sensor_z)` in
  `navbot_imu/l3gd20_lsm303d_reader.py`; set `sensor_orientation` to it in
  `config/l3gd20_lsm303d.yaml`.
- Deployed to Pi (backups `*.bak-20260616`), `colcon build navbot_imu` clean.
- **HW verification:** accel_z back to **+10.99** (Z-up), roll/pitch ≈ 0;
  CCW spin → gyro_z **+0.64 rad/s** (correct +CCW, right-hand rule); 50.0 Hz.
- The EKF (`ekf.yaml imu0_config`) fuses **yaw + yaw-rate only**, and mag
  fusion is **disabled** (`use_mag: False`). Both fused quantities are
  gyro-derived and verified correct, so the orientation fix is fully
  sufficient for nav. Stale mag offsets, the ~12 % accel-scale offset, and
  the small gyro-X bias are all outside the nav path.
- **Mag hard-iron recalibration deferred** — only needed if the compass is
  ever re-enabled (session-10 found motor EM degrades it anyway).

## Open follow-ups (non-blocking)

- **GP27 `motor_v` sense divider disconnected** — telemetry reads false
  ~0.085 V while the rail is ~6.27 V; web-console motor voltage is wrong.
  `motor_v` is telemetry-only (no firmware lockout), so it does not affect
  driving. Reconnect the GP27 divider.
- **INA238 calibration** in `navbot_power/config/ina238.yaml` (15 mΩ shunt,
  `max_current_a: 3.0`) is still set for the old 5 V Pi rail. Recompute
  SHUNT_CAL / `max_current_a` for the motor rail — needs the motor stall
  current; confirm 6.27 V is the intended nominal.

## Deferred to next session

- **Maps:** `office_lab` / `office_lab_v2` are office-only and obsolete now
  that the robot is at home. Capture a **fresh home SLAM map** first.
- **Session-12 nav work** (AMCL validation, multi-waypoint rerun,
  higher-speed) resumes on the new home map.

## Deployment state

Pi repo is on `navbot-experimental` but HEAD is stale at `dc04ba9` with
~14 rsync'd uncommitted files. The session-13 IMU edits were applied to the
Pi directly and staged on the Mac checkout; **not yet committed**.
