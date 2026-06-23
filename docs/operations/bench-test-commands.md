# Navbot Bench Test Commands (`/navbot:*`)

Operator self-test commands for the navbot, run from Claude Code. They are
project slash commands (in `.claude/commands/navbot/`) that drive the robot
over SSH (`navbot-pi`) and report a clear PASS/FAIL with the measured
numbers. Use them after reassembly, after moving the robot, or any time you
want a quick subsystem check.

## How to run

Type the command in Claude Code, e.g.:

```
/navbot:motor-left-fwd
```

- **Motor tests prompt you to confirm the wheels are lifted/free before
  driving.** Answer "yes" only when the wheels can spin without the robot
  moving. They use `TEST_PWM` (raw duty, PID bypassed, auto-stops after 1 s)
  so there is no closed-loop runaway risk.
- **Read-only tests** (voltages, LiDAR health) do not move the robot.
- **`gyro-test`** asks you to hand-rotate the chassis — start rotating
  counter-clockwise *before* it captures and keep rotating continuously
  (the live prompt is not streamed, so rotate throughout).

## Prerequisites

- Pi powered and reachable: `ssh navbot-pi 'echo ok'` returns `ok`
  (alias → `arif@192.168.68.126`, key `id_ed25519_siot_lab_arif`).
- RP2040 connected via a **data** USB cable (a charge-only cable enumerates
  nothing — see Troubleshooting).
- ROS 2 Jazzy workspace built on the Pi (needed for `lidar-health` and
  `gyro-test`).
- For motor tests: **wheels lifted / on blocks.**

## Command reference

| Command | Function | Moves robot? | PASS criteria | Typical reading |
|---------|----------|--------------|---------------|-----------------|
| `/navbot:motor-left-fwd`  | Left motor forward  | Yes (wheel) | LEFT encoder counts **up**, no `FAULT STALL` | ~+475 / 3 s |
| `/navbot:motor-left-rev`  | Left motor backward | Yes (wheel) | LEFT encoder counts **down** | ~−465 / 3 s |
| `/navbot:motor-right-fwd` | Right motor forward | Yes (wheel) | RIGHT encoder counts **up** | ~+480 / 3 s |
| `/navbot:motor-right-rev` | Right motor backward| Yes (wheel) | RIGHT encoder counts **down** | ~−483 / 3 s |
| `/navbot:motor-voltage`   | Motor-rail voltage  | No | INA238 VBUS in expected band | ~6.3–7.1 V (2S LiPo) |
| `/navbot:lidar-voltage`   | LiDAR-rail voltage  | No | `lidar_v` stable ~5 V | ~4.73 V |
| `/navbot:lidar-health`    | LiDAR health + rate | No (LiDAR spins) | `health: OK`, `/scan_raw` 8–12 Hz | ~10.0 Hz |
| `/navbot:gyro-test`       | Gyro / yaw sign     | No (hand-rotate) | CCW spin → **gyro_z positive**, accel Z ≈ +10 | gyro_z ~+1.8, accel Z ~+11 |

## Read-only & safety commands

| Command | Function | Moves robot? | Notes |
|---------|----------|--------------|-------|
| `/navbot:preflight` | Automatable pre-flight (ssh, by-id, i2c, nodes, scan, port owner) | No | Complements, does not replace, the RUNBOOK human checklist |
| `/navbot:status`    | Health snapshot via `/api/status` if stack up, else serial PING/DIAG | No | Auto-avoids serial-port contention |
| `/navbot:stop`      | Emergency STOP + zero CMD_VEL + RESET | No (halts) | Fallback to web-console STOP when the ROS stack owns the port |

## What each test checks

- **Motor direction tests (1–4):** confirm each motor drives, in the correct
  direction, with its encoder counting the matching sign. Forward command →
  positive count; backward → negative. Left and right should be symmetric in
  magnitude. A `FAULT STALL` means the wheel was commanded but didn't move.
- **`motor-voltage`:** reads the trustworthy INA238 VBUS on the motor rail
  *and* the RP2040 `motor_v` telemetry. Note: `motor_v` currently reads a
  **false ~0.08 V** because the GP27 sense divider is disconnected — this is
  a known open item and does **not** affect driving (telemetry only).
- **`lidar-voltage`:** the RP2040 `lidar_v` ADC (GP28) sense line; ~5 V means
  the LiDAR rail is up.
- **`lidar-health`:** brings up `sllidar`, checks the reported health status
  and that `/scan_raw` streams at ~10 Hz. (Bare LiDAR publishes `/scan_raw`;
  `/scan` only exists once the scan-filter node runs in SLAM/nav bringup.)
- **`gyro-test`:** verifies the IMU is alive at ~50 Hz, that gravity reads
  Z-up (accel Z ≈ +10), and that a CCW rotation produces **positive** gyro_z
  (correct right-hand-rule under the `x_forward_flipped` mount).

## Motion commands (closed-loop CMD_VEL — the robot drives)

Unlike the bench tests above (PID-bypassed `TEST_PWM`), these use closed-loop
`CMD_VEL` and **actually drive the robot across the floor**. Each prompts you to
confirm clear space (or wheels on blocks) before moving. Speeds are conservative
and each runs ~2.5 s (turn-reverse ~5.2 s) then auto-`STOP`s.

| Command | Motion | CMD_VEL (lin, ang) | Expected odom |
|---------|--------|--------------------|---------------|
| `/navbot:move-forward`    | straight forward ~0.25 m | +0.10, 0 | both wheels **+**, balanced |
| `/navbot:move-backward`   | straight backward ~0.25 m | −0.10, 0 | both wheels **−**, balanced |
| `/navbot:soft-turn-left`  | forward + gentle left arc (r≈0.25 m) | +0.10, +0.4 | both **+**, right > left |
| `/navbot:soft-turn-right` | forward + gentle right arc | +0.10, −0.4 | both **+**, left > right |
| `/navbot:turn-reverse`    | in-place ~180° spin (CCW) | 0, +0.6 (~5.2 s) | left **−**, right **+** |

Notes: `+ang` = left/CCW (matches the gyro convention). `turn-reverse` is
open-loop/time-based, so ~180° is approximate — tune `SECS` in the command if it
lands short/long (rotation rate varies with battery/load). All stream `CMD_VEL`
at 10 Hz to beat the 0.5 s firmware command timeout and send `STOP` at the end.

> **Validated on hardware 2026-06-22** — all five pass (straight runs balanced
> <1%, arcs show correct outer/inner differential, in-place spin symmetric
> ±5140, no stalls). Full results:
> [../validation/records/2026-06-22-motion-commands-validation.md](../validation/records/2026-06-22-motion-commands-validation.md).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Motor test: `NO MOVEMENT` | Loose/disconnected motor lead at the terminal (M1 = right, M2 = left), or dead driver channel | Reseat the motor leads firmly; if still dead, swap the motor onto the other terminal to isolate motor vs channel |
| Motor test: wrong direction (forward → negative) | Motor leads swapped (physical reverse) or encoder A/B swapped (counts reversed) | If the wheel physically spins backward → swap that motor's two leads; if it spins forward but counts down → swap that encoder's A/B |
| `FAULT STALL` in states | Wheel commanded but not turning (usually a dead/loose motor) | Fix the motor drive path; stall detection is working as designed |
| RP2040 not found / no `/dev/ttyACM*` | **Charge-only USB cable** (no data lines) | Swap to a known data cable; a good cable enumerates the Pico instantly |
| `motor_v` reads ~0 while INA238 shows volts | GP27 motor-voltage sense divider disconnected | Reconnect the GP27 divider (telemetry-only; does not block driving) |
| gyro-test: `Remote I/O` / IMU not on bus | IMU I²C connector loose (vibration-sensitive at the axle-height mount) | Reseat the IMU connector (SDA pin 3, SCL pin 5, VCC 3.3 V pin 1, GND pin 6); verify with `i2cdetect -y 1` → `19 69 1e` |
| gyro-test: "no clear rotation" | Not rotating during the capture window | Re-run and rotate CCW continuously and briskly the whole time |

## Related docs

- Bring-up record: [../validation/records/2026-06-16-home-reassembly-bringup.md](../validation/records/2026-06-16-home-reassembly-bringup.md)
- Project status: [../project-status.md](../project-status.md)
- IMU driver / orientation: [../../ros2_ws/src/navbot_imu/README.md](../../ros2_ws/src/navbot_imu/README.md)
- Runbook (pre-flight safety): [../RUNBOOK.md](../RUNBOOK.md)
