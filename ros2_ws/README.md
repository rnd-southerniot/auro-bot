# ROS 2 Workspace

This workspace contains the ROS 2 Jazzy packages for the `makerpi-rp2040-ros2-navbot` robot.

## Local Packages

- `navbot_base`: serial bridge, odometry, joint states, TF
- `navbot_description`: URDF/Xacro and RViz assets
- `navbot_bringup`: top-level launch composition
- `navbot_lidar`: wrapper around the external `sllidar_ros2` driver
- `navbot_slam`: wrapper around `slam_toolbox`
- `navbot_navigation`: wrapper around Nav2
- `navbot_localization`: wrapper around `robot_localization` EKF
- `navbot_teleop`: teleop launch convenience
- `navbot_web`: browser-based ground-test console and rosbag capture helper
- `navbot_power`: INA238-based power telemetry reader
- `navbot_imu`: Pi-side L3GD20 + LSM303D IMU reader
- `navbot_utils`: small utility package placeholder
- `navbot_msgs`: placeholder package for future custom messages

## External Dependencies

This repository does not vendor:

- `sllidar_ros2`
- `robot_localization`
- `slam_toolbox`
- Nav2

Install those on the target Pi through apt or upstream instructions before full bringup.

## Build

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws
colcon build
source install/setup.bash
```

## Live Base Verification

The default `navbot_base` config assumes:

- `serial_port: /dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00`
- `baud_rate: 115200`
- `wheel_radius: 0.033`
- `wheel_separation: 0.160`
- `left_counts_per_revolution: 3943`
- `right_counts_per_revolution: 3946`

Launch the base stack:

```bash
source /opt/ros/jazzy/setup.bash
ros2 launch navbot_bringup base.launch.py
```

If the RP2040 path changes, override it directly:

```bash
ros2 launch navbot_base base_bridge.launch.py serial_port:=/dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00
```

## Live LiDAR Verification

Validated Pi runtime:

```bash
source /opt/ros/jazzy/setup.bash
source /home/arif/ros2_ws/install/setup.bash
ros2 launch navbot_lidar lidar.launch.py
```

Validated LiDAR serial path:

- `/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0`

## Web Console

Use the repo helper from the project root:

```bash
./scripts/launch_web_console.sh port:=8081
```

See `../docs/WEB_CONSOLE.md` for operator behavior and capture details.

## IMU + Localization

The workspace now also has:

- `navbot_imu` for raw gyro / accel / magnetometer publication
- `navbot_localization` for a first `robot_localization` EKF wrapper

Safe first localization launch:

```bash
source /opt/ros/jazzy/setup.bash
source /home/arif/projects/makerpi-rp2040-ros2-navbot/ros2_ws/install/setup.bash
ros2 launch navbot_bringup imu_localization.launch.py
```

The current EKF publishes:

- `/odometry/filtered`

It does not replace the existing base TF path yet.

## Detailed Runtime Docs

Use the standard project docs for operator details:

- `../docs/architecture.md`
- `../docs/RUNBOOK.md`
- `../docs/VALIDATION.md`
- `../docs/WEB_CONSOLE.md`
