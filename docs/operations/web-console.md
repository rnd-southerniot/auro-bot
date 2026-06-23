# Web Console

> **Status note (2026-04 onward):** `navbot_web` is being succeeded by
> Foxglove bridge for new Navbot work. The package still ships and is
> documented here as the current bring-up console, but the Foxglove
> setup at [foxglove/README.md](foxglove/README.md) is the recommended
> path for new session work. This doc will be retired once Foxglove
> covers the capture workflow that `navbot_web` still owns.

## Purpose

`navbot_web` is a local-network ground-test console. It is an operator aid for bringup, not a replacement for firmware timeout, estop, RViz, SLAM tools, or Nav2.

It provides:

- hold-to-move browser teleop over `/cmd_vel`
- explicit STOP
- base, LiDAR, odom, joint, controller, and estop freshness
- INA238 rail telemetry from `/power/ina238/status`
- IMU status and compass-derived YPR from `/imu/l3gd20_lsm303d/*`
- capture start/stop for selected ROS topics

## Launch

```bash
cd /home/arif/projects/makerpi-rp2040-ros2-navbot
./scripts/launch_web_console.sh port:=8081
```

Open:

```text
http://192.168.15.20:8081
```

The helper frees the requested port before relaunching. It sources `/home/arif/ros2_ws/install/setup.bash` when present so the web console can run against the validated LiDAR overlay.

## Status API

Endpoint:

```text
GET /api/status
```

The response stays strict JSON. Missing optional telemetry is represented with JSON `null` or unavailable status instead of `NaN`.

Important fields:

- `base_bridge_alive`
- `odom.alive`
- `scan.alive`
- `joint_states.alive`
- `power.alive`
- `imu.alive`
- `controller.state`
- `estop.active`
- `capture.active`

## Capture

Recorded topics:

- `/scan`
- `/odom`
- `/tf`
- `/tf_static`
- `/joint_states`
- `/base/controller_state`
- `/base/estop`
- `/cmd_vel`
- `/imu/l3gd20_lsm303d/raw`
- `/imu/l3gd20_lsm303d/mag`
- `/imu/l3gd20_lsm303d/ypr`
- `/heading_controller/status`
- `/odometry/filtered`

Output:

```text
captures/YYYY-MM-DD_HH-MM-SS_<label>/
```

Each capture should contain `capture_meta.json`, `record.log`, and bag data under `bag/`.

## Operator Safety

- Movement buttons are hold-to-move.
- Releasing a movement button stops command streaming.
- The STOP button remains visible.
- The RP2040 firmware still owns command timeout and estop behavior.
- If any freshness card is stale, do not trust browser teleop for motion.

## Sensor Notes

LiDAR:

- RPLIDAR C1 is individually powered.
- USB is the CP2102 serial/data link.
- Web freshness can go stale if the serial adapter re-enumerates and `sllidar_node` keeps a deleted `/dev/ttyUSB*` fd.

INA238:

- INA238 is the only supported web-console power telemetry source.
- The web console reads `/power/ina238/status`.
- Pi kernel undervoltage warnings remain hardware diagnostics, not the web power telemetry source.

IMU:

- The web console reads `/imu/l3gd20_lsm303d/status`, `/raw`, `/mag`, and `/ypr`.
- The UI shows compass-derived heading, yaw, pitch, and roll instead of raw accel/mag rows.
- YPR yaw is sign-adjusted to follow the ROS positive/left-turn convention.
- YPR uses the `2026-04-11` planar X/Y magnetometer calibration in `navbot_imu`; Z hard/soft iron remains pending until a 3D tilt capture is performed.
- Use `imu_localization.launch.py` when the IMU should also feed EKF output on `/odometry/filtered`.
