# Closed-loop in-place turn (IMU gyro feedback) — finding + fix

**Date:** 2026-06-26
**Scope:** P6 visual search — the `turn` / `look_around` in-place rotation was
**open-loop** (timed `cmd_vel`), so it could not reliably face a found object.
Replaced with closed-loop control on the IMU gyro.
**Stack:** robot `navbot-pi`, autostart appliance (P7) running
`navbot-bringup`/`web`/`voice`; tool path = loopback control server (`:8077`) →
`navbot_web /api/*`. Robot on blocks (body free to rotate).
**Verdict:** FIXED + LIVE-VALIDATED on blocks (turns accurate to ~1°).

## Finding

Checking the visual search (`look_around` 360° sweep → brain finds object →
`turn` to face it), the **turn-to-face missed badly**: a candidate object at
~67° was not centered after `turn 67` — the robot landed ~30°+ off.

Root cause in `RobotTools._spin` (`ros2_ws/src/navbot_voice/navbot_voice/robot_tools.py`),
shared by both `look_around` and `turn`:

- **Open-loop.** It commanded `cmd_vel(0, ±0.5)` for `angle / 0.5 rad/s` seconds,
  i.e. it *trusted* that commanded time × nominal rate equalled rotation. Any
  wheel slip, surface variation, or motor-rate error went uncorrected. There was
  no heading feedback at all.

### Which sensor to close the loop on

Measured all three available yaw signals over a controlled ~65° spin (probe
polling `/api/status` while commanding `cmd_vel(0, +0.5)` for ~2.5 s):

| signal | source | Δ over the spin | usable? |
|---|---|---|---|
| `imu.yaw_rad` / `heading_deg` | **magnetometer** (`atan2(mag_y,mag_x)`) | **+2.8°** | **No** — barely moves indoors near the motors |
| `imu.angular_velocity_z` (integrated) | **gyro** | **+60.8°** | **Yes** — tracks, slip-immune |
| `odom.yaw` | wheel odom (`/odom`) | +65.2° | tracks, but slip-vulnerable |

The "obvious" IMU field — `imu.yaw_rad` — is magnetometer-derived
(`navbot_imu/l3gd20_lsm303d_reader.py:_compute_ypr`) and is effectively dead for
heading indoors near the motors; closing on it would spin to the timeout every
time. The **gyro z-rate** is the correct signal (and is what wheel odom can't be:
immune to slip). Gyro bias ≈ 0 (±0.0009 rad/s).

## Fix

`RobotTools._spin` rewritten as a gyro-feedback controller:

- `_gyro_z()` reads live `imu.angular_velocity_z` (None if IMU stale/NaN);
  `_gyro_bias()` averages it at rest before each spin to cancel the zero-offset.
- The control loop commands `cmd_vel(0, dir·rate)` then integrates
  `(gyro − bias)·dt` to track **actual** rotation, stopping when the integrated
  angle reaches the target (less a ~2° lead for command/stop latency). `rate`
  ramps down proportionally (`Kp=1.5`, floored at 0.25 rad/s) near the target to
  limit overshoot; cruise is the shared `_ROTATE_RATE = 0.5 rad/s`.
- **Safety preserved / added:** degrades to the original timed spin
  (`_spin_timed`) if no usable IMU; a hard time ceiling (2.5× nominal + 1 s)
  guarantees it cannot spin forever; `safety.aborted` ("stop" word) and e-stop
  still abort; `cmd_vel` is issued every ~0.06 s loop to hold the web watchdog
  open; `stop()` in `finally`. Still drive-mode gated, still angular-only so
  exempt from the linear per-episode motion budget.

## Live validation (robot on blocks)

Deployed: scp edited `robot_tools.py` → `colcon build --packages-select
navbot_voice` → `systemctl restart navbot-voice`. Commanded turns via the
`:8077` tool server while an **independent** observer logged `odom.yaw` and
integrated the gyro with its own bias estimate:

| commanded | gyro (independent) | odom (independent) |
|---|---|---|
| +90° | **+89.0°** | +92.7° |
| −90° | **−89.7°** | −94.3° |
| +45° | **+44.4°** | +47.1° |

Within ~1° of target in both directions and at large/small angles (vs. ~30°+
open-loop error). The independent gyro integral matching the target confirms the
gyro scale is accurate — no systematic overshoot from the integrate-to-target
scheme. (`odom.yaw` consistently reads ~2–3° higher than the gyro on this
surface; the controller closes on the gyro, so gyro-vs-target is the metric.)

## Deploy note

`navbot_voice` on the robot is colcon-built **without** `--symlink-install`
(install holds a copy), so a rebuild is required after editing source — restart
alone is not enough. See [[robot-ros-deploy]].

## Follow-ups

- On a magnetically quieter spot / after a mag calibration, re-check whether
  `imu.yaw_rad` is salvageable as an absolute-heading cross-check.
- Camera (`192.168.68.110`) was reboot-flapping during this session (uptime
  reset 365 s → offline → 25 s) — separate XIAO power/Wi-Fi stability issue.
