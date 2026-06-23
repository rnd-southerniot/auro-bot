# Validation

## Validated Checkpoints

- RP2040 serial protocol bench checks:
  - `PING`, `STOP`, `RESET`, `ESTOP`, `CMD_VEL`, `WHEEL_VEL`
- Bench-truth wheel signs:
  - left wheel forward gives positive left count and velocity
  - right wheel forward gives positive right count and velocity
  - positive angular command gives left / counter-clockwise yaw
- Firmware false-positive stall fix held through base, LiDAR, and cautious SLAM testing:
  - startup and reversal grace
  - setpoint-change stall inhibit
  - near-zero setpoint drop to `IDLE`
  - `MAX_RUN_TIME_MS 0` for normal ROS/mobile use
- Cautious small-area base + LiDAR + web-console test passed:
  - forward, backward, left turn, right turn, stop
  - `/odom`, `/joint_states`, `/base/controller_state`, and `/scan` stayed alive
  - controller returned to `IDLE OK`
  - no false `STALL`
  - no serial disconnect
- Cautious small-area SLAM re-test reached `GO`:
  - `map -> odom` became live and stayed live
  - map updated during motion
  - `/scan` and `/odom` stayed alive
  - capture stopped cleanly

## Current Smoke-Test Truth

Confirmed on the Pi after the 2026-04-11 cleanup:

- SSH works to `192.168.15.20` using the laptop Ed25519 key.
- `imu_localization.launch.py` can own the current stack:
  - LiDAR
  - INA238
  - IMU
  - `robot_localization` EKF
  - robot state publisher
  - base serial bridge
- `/scan` publishes at about `10 Hz`.
- `/imu/l3gd20_lsm303d/raw` publishes at about `20 Hz`.
- `/odometry/filtered` publishes from `robot_localization`.
- `GET /api/status` on port `8081` reports base, scan, joint states, INA238, IMU, and controller alive.

## LiDAR Runtime Truth

- RPLIDAR C1 is individually powered.
- USB is the CP2102 serial/data path, not the LiDAR power source.
- Validated serial/data by-id path:
  - `/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0`
- Validated frame: `laser_link`
- Validated beam count: about `720`
- Validated scan mode: `Standard`
- Validated scan rate: about `10 Hz`
- Validated driver: `sllidar_ros2` from `/home/arif/ros2_ws/install/setup.bash`

Recent stale LiDAR event:

- `sllidar_node` still had a ROS `/scan` publisher.
- Its serial fd pointed to `/dev/ttyUSB0 (deleted)`.
- The CP2102 adapter had re-enumerated as `/dev/ttyUSB1`.
- Restarting the launch reopened the by-id path and restored `/scan`.

Interpretation: stale `/scan` was a USB serial/data-link re-enumeration problem, not evidence that LiDAR is powered from USB.

## INA238 Truth

- INA238 is visible on Pi `i2c-1` at `0x40`.
- `navbot_power` publishes `/power/ina238/status`.
- Web console consumes the same status topic.
- INA238 is the only supported Pi-side operator power telemetry path in this repo.
- It reports rail telemetry, not battery percentage or runtime prediction.

Kernel undervoltage warnings may still appear. Keep them visible for hardware troubleshooting, but do not use Pi firmware/throttle telemetry as the web-console power source.

## IMU Truth

- Detected IMU layout:
  - gyro `0x69`
  - accelerometer `0x19`
  - magnetometer `0x1E`
- `navbot_imu` publishes:
  - `/imu/l3gd20_lsm303d/raw`
  - `/imu/l3gd20_lsm303d/mag`
  - `/imu/l3gd20_lsm303d/ypr`
  - `/imu/l3gd20_lsm303d/status`
- The reader publishes raw SI-unit gyro, accel, and magnetometer data plus compass-derived YPR.
- YPR yaw is sign-adjusted so positive yaw follows the ROS positive/left-turn convention.
- Planar magnetometer calibration was captured on `2026-04-11`:
  - X/Y hard-iron offsets: `-1.604545454545e-05 T`, `-1.69090909091e-05 T`
  - X/Y soft-iron scales: `1.088124410934`, `0.925080128205`
  - raw planar radius CV improved from `0.2938` to `0.0142` after offset/scale
  - Z hard/soft iron remains pending because it needs a 3D tilt/roll capture, not only an in-place yaw rotation
- `imu_localization.launch.py` starts EKF output on `/odometry/filtered`.

## Capture Evidence

Validated capture examples:

- Base + LiDAR:
  - `/home/arif/projects/makerpi-rp2040-ros2-navbot/captures/2026-03-24_22-28-45_small_area_motion_with_lidar_20260324`
- SLAM re-test:
  - `/home/arif/projects/makerpi-rp2040-ros2-navbot/captures/2026-03-24_22-42-51_slam_small_area_retest_20260324`
- IMU planar magnetometer calibration:
  - `/home/arif/projects/makerpi-rp2040-ros2-navbot/captures/2026-04-11_20-55-07_mag_planar_calibration`

## Still Not Closed

- Longer LiDAR/runtime validation after power-path cleanup
- Final wheel calibration values
- Broader map-quality validation
- Nav2/autonomy readiness
- Production diagnostics and recovery behaviors
