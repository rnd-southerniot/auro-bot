# navbot_base

Serial bridge between the Pi 5 ROS 2 stack and the Maker Pi RP2040 base
controller, plus a small heading controller for closed-loop orientation
use.

## Nodes / Executables

- `serial_bridge` — opens the RP2040 USB serial port, translates
  `/cmd_vel` into the line-based navbot protocol, and publishes
  odometry + joint states + controller state back to the ROS graph.
- `heading_controller` — higher-level controller that holds a heading
  while driving; consumes odom/IMU, emits `/cmd_vel`.

## Launch files

- `launch/base_bridge.launch.py` — serial bridge only.
- `launch/heading_controller.launch.py` — heading controller node on
  top of an already-running bridge.

## Topics

Published:

- `/odom` (nav_msgs/Odometry) — Pi-side integrated odometry.
- `/joint_states` (sensor_msgs/JointState) — wheel joints for TF chain.
- `/tf` — `odom → base_footprint` (odometry TF only; description
  publishes the rest).
- `/base/controller_state` (std_msgs/String) — RP2040 mode + fault.
- `/base/estop` (std_msgs/Bool) — RP2040 estop state.
- `/base/lidar_voltage` (std_msgs/Float32) — System 2 rail voltage from
  RP2040 ADC.
- `/base/motor_voltage` (std_msgs/Float32) — System 3 rail voltage.
  **Note:** currently rail-scaled due to firmware "C7 bug" — see
  [../../../docs/project-status.md](../../../docs/project-status.md).
- `/heading_controller/status` (std_msgs/String) — when the heading
  controller is running.

Subscribed:

- `/cmd_vel` (geometry_msgs/Twist) — drive command.

## Dependencies

- ROS 2 Jazzy: `rclpy`, `geometry_msgs`, `nav_msgs`, `sensor_msgs`,
  `std_msgs`, `tf2_ros`.
- External: `pyserial` for USB serial.
- Hardware: Maker Pi RP2040 running the firmware in
  [../../../firmware/makerpi_rp2040_base/](../../../firmware/makerpi_rp2040_base/).
- Serial path expected at `/dev/serial/by-id/usb-Raspberry_Pi_Pico_*`
  (see udev rules in `scripts/setup-pi.sh`).

## Related docs

- Architecture: [../../../docs/architecture/system.md](../../../docs/architecture/system.md)
- Runbook: [../../../docs/RUNBOOK.md](../../../docs/RUNBOOK.md)
- Motion test results: [../../../docs/testing/motion-tests.md](../../../docs/testing/motion-tests.md)
