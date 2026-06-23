# TODO.md

> The authoritative state lives in [docs/project-status.md](docs/project-status.md).
> This list tracks near-term actionable items.

## Immediate (post home-reassembly, 2026-06-16 — session 13)
- [ ] Reconnect the GP27 `motor_v` sense divider (telemetry reads false ~0 V; web-console motor voltage wrong; telemetry-only, does not block driving)
- [ ] Recompute INA238 calibration in `ros2_ws/src/navbot_power/config/ina238.yaml` for the **motor rail** (need motor stall current; confirm 6.27 V is nominal) — was set for the old 5 V Pi rail
- [ ] Capture a **fresh home SLAM map** — `office_lab` / `office_lab_v2` are obsolete now that the robot is at home
- [ ] (Optional) Commit the session-13 IMU `x_forward_flipped` reconfigure to `navbot-experimental`
- [ ] **Deferred from session 12 (next session):** AMCL validation + multi-waypoint rerun + higher-speed testing — restart on the new home map, not `office_lab_v2`

### Done 2026-06-16 (session 13)
- [x] New power: 3S LiPo + 5V converter for Pi only — verified clean (`throttled=0x0`), undervoltage blocker retired
- [x] Full peripheral bring-up: Pi power, RP2040 (fw 1.3.0), encoders, LiDAR (9.97 Hz), INA238 (0x40), IMU (50 Hz)
- [x] Fixed reassembly wiring: charge-only USB cable (RP2040), left motor inversion, dead/inverted right M1 lead — closed-loop CMD_VEL forward verified
- [x] IMU flipped-mount reconfigure: driver `x_forward_flipped` (x,−y,−z), verified Z-up + +CCW yaw on HW

### Historical (pre-relocation, office)
- [x] Wire the INA238 on Pi `i2c-1`, confirm `0x40`, and validate real voltage/current/power readings
- [x] Auto-launch `navbot_power/ina238_reader` from `base_lidar.launch.py`
- [x] Keep `navbot_web` rendering when optional telemetry is unavailable by emitting strict JSON `null` instead of `NaN`
- [x] Commit and push the by-id serial path defaults and serial-bridge reconnect hardening
- [x] Run the cautious small-area SLAM re-test with LiDAR live and capture enabled
- [x] Confirm `slam_toolbox` starts cleanly with the current working LiDAR path
- [x] Confirm `/map` appears and updates during the cautious motion sequence
- [x] Save the SLAM retest result back into repo docs
- [x] Verify the current Pi image uses the validated `sllidar_ros2` runtime and stable LiDAR by-id path
- [x] Commit and push the updated web-console launcher and refreshed docs
- [ ] Review capture evidence and decide whether any wheel/LiDAR calibration refinement is needed before broader autonomy work

## If hardware test fails
- [ ] If short motion pauses return only under load and `/scan` goes stale, stop and treat the power path as the primary suspect before revisiting web-console cadence or SLAM
- [ ] If base status stays stale, inspect serial port, base launch logs, and `/dev/ttyACM*`
- [ ] If LiDAR status stays stale, inspect `sllidar_ros2`, `/dev/serial/by-id/...`, and `/scan`
- [ ] If motion direction is wrong, re-check firmware wheel/sign mapping before more testing
- [ ] If stop-on-release or STOP fails, pause web-console testing and inspect `/cmd_vel` timeout behavior immediately
- [ ] If captures fail, inspect `record.log`, rosbag command invocation, and write permissions under `captures/`

## After first live pass
- [ ] Add clearer capture state and failure messaging in the web UI
- [ ] Add graceful stop/shutdown behavior for the web console process
- [ ] Show latest capture folder path in the UI
- [x] Show INA238 power telemetry in the web console
- [ ] Consider adding lightweight LiDAR preview after base behavior is proven stable
- [x] Re-run cautious SLAM retest with evidence capture if base + LiDAR + web console are stable

## Documentation cleanup
- [x] Update root `README.md` to stop describing firmware as mostly scaffold/TODO-only
- [x] Add a short Pi operator runbook section referencing `navbot_web`
- [x] Save any newly verified serial port, wheel-sign, launch quirks, LiDAR dependency reality, and capture evidence into standard repo docs
