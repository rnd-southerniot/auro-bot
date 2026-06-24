# P7 autostart — robot boot validation (2026-06-24)

**Result: PASS.** The robot (`navbot-pi`) boots hands-free into the voice + camera
appliance via the systemd stack. Validated by a real reboot, not just a manual
`systemctl start`.

## What was deployed

The robot runs a **two-overlay split** (discovered during this validation):
- `~/projects/claude-navbot/ros2_ws/install` — base + LiDAR + **sllidar_ros2**.
- `~/projects/auro-bot/ros2_ws/install` — voice/camera packages (sourced on top).

Steps: rsync'd the P6/P7 source (`navbot_camera`, `navbot_voice`, `ops/`, the new
scripts) into the robot's `auro-bot`; `colcon build --packages-select navbot_camera
navbot_voice navbot_voice_io` (clean, ~4 s); `sudo ./scripts/install_autostart.sh`.
Two fixes landed in the repo from this:
- overlay path: `EXTERNAL_WORKSPACE_SETUP` → the `claude-navbot` ws (was a wrong
  `/home/arif/ros2_ws`). Commit `0760be7`.
- `navbotctl` executable bit restored (it was 644 in the repo). Commit `6c4f9fe`.

## Boot result

Fresh boot (`uptime` 0 min). All three core units `active` + `enabled`;
`navbot-nav` correctly `inactive` + `disabled`.

- `navbot-bringup`: base serial bridge + IMU + EKF — `/api/status` = `controller
  IDLE OK`, `estop off`.
- `navbot-web`: `/api/*` on :8080.
- `navbot-voice`: journal shows `whisper ready` → `voice control ON (P5) — headless
  Claude Code` → `buddy brain running`.
- Camera: `navbotctl look` (via the brain's loopback control server) saved a frame
  post-boot — P6 vision live under autostart.

## Known issue (not autostart)

**LiDAR times out on boot:** `sllidar_node` launches from the correct overlay with
the right params, then dies with `SL_RESULT_OPERATION_TIMEOUT` (exit 255), so
`/scan` is absent (`scan_alive=False`). This is the project's known LiDAR class
(power / CP2102 / warmup — see [RUNBOOK troubleshooting](../../RUNBOOK.md)), **not**
a P7 problem. Base + IMU + EKF + web + voice + camera are unaffected; Nav2 is
disabled anyway. Follow-up: check the LiDAR rail (`/navbot:lidar-voltage`) / use the
warmup launch, then re-test `/scan`.

Also still present: `motor_v≈0.07` (GP27 divider disconnected, known) and the
`CDRIVE …` serial_bridge warnings flooding the journal (known unparsed telemetry).
