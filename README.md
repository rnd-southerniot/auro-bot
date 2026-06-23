# makerpi-rp2040-ros2-navbot

Implementation repo for a Raspberry Pi 5 + Maker Pi RP2040 differential-drive robot running ROS 2 Jazzy with RPLIDAR C1, `slam_toolbox`, INA238 rail telemetry, and a lean browser-based ground-test console.

## Project Overview

This is an active robotics MVP, not a tutorial scaffold and not a fake-finished product. The repo contains:

- real RP2040 firmware for wheel control, encoder counting, serial protocol, timeout, estop, and stall handling
- ROS 2 Jazzy packages for base bridging, robot description, LiDAR, SLAM, navigation wrappers, teleop, and a ground-test web console
- operator documentation for flashing, serial validation, base bringup, LiDAR bringup, cautious SLAM testing, and capture workflow

## Hardware Split

- Raspberry Pi 5:
  - Ubuntu 24.04
  - ROS 2 Jazzy
  - ROS 2 bringup, teleop, LiDAR, SLAM, Nav2
  - USB serial link to the RP2040
- Maker Pi RP2040:
  - Motor PWM output
  - Encoder counting
  - Closed-loop wheel velocity control
  - E-stop and command timeout behavior
  - Human-readable serial protocol for bench diagnostics
- Sensors and drivetrain:
  - Differential drive motors with quadrature encoders
  - RPLIDAR C1 with its own power feed and Pi-side CP2102 USB serial/data link
  - Optional INA238 power monitor on the Pi I2C bus
  - Pi-side 9DOF IMU on `i2c-1` with raw gyro / accel / magnetometer bring-up
  - Future IMU fusion on the Pi side

## Software Architecture

- `firmware/makerpi_rp2040_base/`
  - Pico SDK + CMake firmware
  - wheel PWM, encoder sampling, wheel PID, timeout, estop, stall logic
  - human-readable serial protocol
- `ros2_ws/`
  - ROS 2 Jazzy workspace
  - `navbot_base` for serial bridging, odometry, joint states, and TF
  - Description, bringup, lidar, slam, localization, navigation, teleop, power, web console, utils, and msg packages

## Current Maturity

Implemented and usable now:

- RP2040 firmware for Milestone 1 base control
- line-based serial protocol between Pi and RP2040
- `navbot_base` serial bridge and Pi-side odometry
- `robot_state_publisher` description/TF path
- LiDAR wrapper launch path for upstream `sllidar_ros2`
- Pi-side IMU raw-data bring-up on `i2c-1`
- Pi-side INA238 reader on `i2c-1` with web-console rail telemetry
- `robot_localization` wrapper for filtered odometry output
- `slam_toolbox` wrapper launch path
- `navbot_web` browser console for teleop, status, and rosbag capture

Still environment- or hardware-dependent:

- final wheel calibration values
- broader SLAM session coverage beyond the cautious small-area retest
- Nav2 runtime tuning
- deeper IMU fusion and production diagnostics

## ROS 2 Stack

- Ubuntu 24.04
- ROS 2 Jazzy
- `slam_toolbox` for SLAM
- Nav2 for navigation
- Upstream SLLIDAR ROS 2 driver dependency, wrapped but not vendored

## Repo Layout

```text
.
├── docs/                           standard architecture, runbook, validation, and web-console docs
├── firmware/makerpi_rp2040_base/   RP2040 firmware and firmware docs
├── ros2_ws/                        ROS 2 Jazzy workspace
├── scripts/                        helper scripts for build and launch
├── captures/                       rosbag capture output root
└── TODO.md                         active remaining tasks
```

## Validated Reality Recorded In This Repo

Based on the repo continuity files and operator validation history recorded here:

- firmware serial protocol has been bench-validated
- bench truth is:
  - left wheel forward => positive left count / positive left velocity
  - right wheel forward => positive right count / positive right velocity
  - positive angular `CMD_VEL` produces left / CCW yaw
- RP2040 false-positive stall handling was fixed with:
  - startup/reversal grace
  - setpoint-change stall inhibit
  - near-zero setpoint drop to `IDLE`
  - `MAX_RUN_TIME_MS 0` for ROS/mobile use
- cautious small-area ground motion has now been revalidated:
  - forward passed
  - backward passed
  - left turn passed
  - right turn passed
  - stop behavior passed
  - controller returned to `IDLE OK`
  - `/odom`, `/joint_states`, and `/base/controller_state` stayed alive
  - no false `STALL`
  - no serial disconnect
- LiDAR is now revalidated live on the Pi:
  - device path `/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0`
  - `/scan` live at about `10 Hz`
  - `frame_id: laser_link`
  - `beam_count: 720`
  - working runtime reported `Standard` at `10.0 Hz`
- LiDAR power truth:
  - RPLIDAR C1 is individually powered
  - USB is the serial/data link only
  - `/scan` can still go stale if the CP2102 adapter re-enumerates and `sllidar_node` keeps a deleted `/dev/ttyUSB*` fd
- `navbot_web` has now been used successfully for real ground-test control/status/capture on the Pi
- cautious small-area SLAM re-test is now recorded as a real GO result on the Pi:
  - launch environment used:
    - `/opt/ros/jazzy/setup.bash`
    - `/home/arif/ros2_ws/install/setup.bash`
    - `/home/arif/projects/makerpi-rp2040-ros2-navbot/ros2_ws/install/setup.bash`
  - preflight:
    - `/odom` alive
    - `/joint_states` alive
    - `/base/controller_state` alive, `IDLE OK`
    - `/scan` alive with `frame_id: laser_link` and `beam_count: 720`
    - `map -> odom` became live after normal startup wait
  - cautious motion sequence passed:
    - forward
    - left turn
    - second forward
    - right turn
    - backward
    - stop behavior
  - during the SLAM run:
    - map updated
    - `map -> odom` stayed live
    - `/scan` stayed alive
    - `/odom` stayed alive
    - no false `STALL`
    - no serial disconnect
  - capture completed cleanly with `return_code: 0`

What is **not** yet claimed as fully closed:

- longer LiDAR/runtime validation in the current Pi image
- broader map-quality validation beyond the cautious small-area SLAM checkpoint
- Nav2/autonomy readiness

## Current LiDAR Runtime Expectation

The canonical Pi runtime currently expects:

- `sllidar_ros2`
- the stable RP2040 by-id path:
  - `/dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00`
- the stable LiDAR by-id path:
  - `/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0`

Current runtime intent:

- source ROS 2 Jazzy
- source the external Pi overlay that provides `sllidar_ros2`
- source this repo workspace
- keep both base and LiDAR on their stable `/dev/serial/by-id/...` paths
- let `base_lidar.launch.py` bring up LiDAR, base, and INA238 telemetry together
- use `imu_localization.launch.py` when IMU data should feed `/odometry/filtered`

## Key Runtime Entry Points

Base only:

```bash
source /opt/ros/jazzy/setup.bash
source /path/to/makerpi-rp2040-ros2-navbot/ros2_ws/install/setup.bash
ros2 launch navbot_bringup base.launch.py \
  serial_port:=/dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00
```

Base + LiDAR:

```bash
source /opt/ros/jazzy/setup.bash
source /home/arif/ros2_ws/install/setup.bash
source /path/to/makerpi-rp2040-ros2-navbot/ros2_ws/install/setup.bash
ros2 launch navbot_bringup base_lidar.launch.py
```

Ground-test web console:

```bash
cd /path/to/makerpi-rp2040-ros2-navbot
./scripts/launch_web_console.sh
```

The helper script will free the target port first if an older web-console listener is still holding it. Default port is `8080`; override with `port:=8081` if needed.

Open:

```text
http://<pi-ip>:8080
```

SLAM:

```bash
source /opt/ros/jazzy/setup.bash
cd /path/to/makerpi-rp2040-ros2-navbot
./scripts/launch_slam.sh serial_port:=/dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00
```

For best LiDAR measurement accuracy on the C1, the vendor manual recommends more than 2 minutes of warm-up with the scan motor already rotating before SLAM starts. Use:

```bash
source /opt/ros/jazzy/setup.bash
cd /path/to/makerpi-rp2040-ros2-navbot
./scripts/launch_slam_with_warmup.sh serial_port:=/dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00
```

Validated cautious SLAM retest capture:

```text
/home/arif/projects/makerpi-rp2040-ros2-navbot/captures/2026-03-24_22-42-51_slam_small_area_retest_20260324
```

## Operator Runbook

Tonight-style minimal flow:

```bash
cd /home/arif/projects/makerpi-rp2040-ros2-navbot
./scripts/setup-pi.sh
./scripts/build_ros2_ws.sh
./scripts/serial_check.sh
```

Then on the Pi or target runtime:

```bash
source /opt/ros/jazzy/setup.bash
source /home/arif/ros2_ws/install/setup.bash
source /home/arif/projects/makerpi-rp2040-ros2-navbot/ros2_ws/install/setup.bash
ros2 launch navbot_bringup base_lidar.launch.py
./scripts/launch_web_console.sh
```

For the validated cautious SLAM pattern, use:

```bash
./scripts/launch_slam.sh serial_port:=/dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00
```

And drive only a small diagnostic pattern:

1. forward for 3 s
2. idle for 2 s
3. left turn for 4 s
4. idle for 2 s
5. backward for 3 s
6. idle for 3 s

Current next step after that successful checkpoint:

1. keep the SLAM GO result preserved in repo docs and memory
2. keep the LiDAR path on the validated `sllidar_ros2` runtime with stable by-id device names
3. refine calibration if needed
4. only then expand into broader Nav2/autonomy work

## Power Telemetry

`base_lidar.launch.py` and `imu_localization.launch.py` now bring up `navbot_power/ina238_reader` as part of the main Pi stack. The web console shows an operator-facing `Power Telemetry` panel with:

- rail voltage
- current
- power
- shunt voltage
- INA238 die temperature

This is real rail telemetry from the INA238 on `i2c-1`. It is not a fake battery percentage. If the INA238 topic is unavailable, the current web-console build keeps rendering and shows unavailable values instead of breaking the page.

## Deployment Status

**CONDITIONAL GO** — validated 2026-04-13, firmware v1.2.0 (`eb4f0c2`).

- Bench validation: 33/33 tests passed (safety, communication, sensor, security)
- Soak test: 10.8 hours continuous, zero crashes, zero disconnections, zero checksum failures
- Software stability: confirmed
- Blocking hardware issue: Pi 5 undervoltage with current adapter under full sensor load

Deployment conditions:

1. Use Raspberry Pi 5 official 27W USB-C adapter (5.1V / 5A)
2. Supervised operation for first 48 hours
3. Maximum 8-hour continuous runtime until clean 24-hour soak with proper adapter
4. LiDAR requires adequate power margin from the supply
5. Teleop and SLAM mapping only — Nav2 autonomy not yet validated

Rollback baseline: existing Pi image backup + RP2040 firmware backup.

Full results: [docs/VALIDATION_RECORD_20260413.md](docs/VALIDATION_RECORD_20260413.md)

## Documentation Map

- [docs/index.md](docs/index.md) — navigation hub for all project docs
- [docs/RUNBOOK.md](docs/RUNBOOK.md) — pre-flight, startup/shutdown, incident response, troubleshooting
- [docs/power-architecture.md](docs/power-architecture.md) — three-battery system with Mermaid diagrams
- [docs/project-status.md](docs/project-status.md) — current state and Phase C backlog
- [docs/architecture/system.md](docs/architecture/system.md) — hardware split, ROS graph, serial protocol
- [docs/operations/web-console.md](docs/operations/web-console.md) — `navbot_web` browser console
- [docs/operations/foxglove/README.md](docs/operations/foxglove/README.md) — Foxglove bridge and default layout
- [docs/hardware/pi-rebuild.md](docs/hardware/pi-rebuild.md) — Pi 5 rebuild procedure and five silent bugs
- [docs/hardware/ina238.md](docs/hardware/ina238.md) — INA238 chip, driver, troubleshooting
- [docs/hardware/lidar-mount.md](docs/hardware/lidar-mount.md) — RPLIDAR C1 mount conventions
- [docs/testing/motion-tests.md](docs/testing/motion-tests.md) — 120 mm drive result and coast analysis
- [docs/validation/README.md](docs/validation/README.md) — validated runtime checkpoints
- [docs/validation/records/](docs/validation/records/) — archived session records (v1.2.0 freeze, pre-wipe calibration, DWB session)
- [docs/notes/brake-attempt-forensic.md](docs/notes/brake-attempt-forensic.md) — regen-brake experiment forensic
- [firmware/makerpi_rp2040_base/README.md](firmware/makerpi_rp2040_base/README.md)
- [firmware/makerpi_rp2040_base/FLASHING.md](firmware/makerpi_rp2040_base/FLASHING.md)
- [ros2_ws/README.md](ros2_ws/README.md)
- [TODO.md](TODO.md)
