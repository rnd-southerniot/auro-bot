# navbot_localization

Wrapper around the upstream `robot_localization` EKF. Does not vendor
the package; provides launch + parameter tuning for Navbot.

## Launch files

- `launch/` — starts `ekf_node` with Navbot-specific YAML.

## Topics

Published (via upstream `ekf_node`):

- `/odometry/filtered` (nav_msgs/Odometry) — fused odom + IMU output.
- `/tf` — `odom → base_footprint` (when configured to publish TF).

Subscribed:

- `/odom` from `navbot_base`.
- `/imu/l3gd20_lsm303d/raw` from `navbot_imu`.

## Parameters

Key tuning knobs in `config/`. Adjust cautiously — changes here affect
the navigation stack's frame-of-reference assumptions.

## Dependencies

- ROS 2 Jazzy: `robot_localization` (apt install `ros-jazzy-robot-localization`).
- `navbot_base` and `navbot_imu` for inputs.

## Related docs

- Architecture + TF tree: [../../../docs/architecture/system.md](../../../docs/architecture/system.md)
