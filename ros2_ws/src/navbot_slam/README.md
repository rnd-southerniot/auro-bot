# navbot_slam

Wrapper around `slam_toolbox` for Navbot. Does not vendor
slam_toolbox; provides launch + parameter tuning.

## Launch files

- `launch/` — starts `slam_toolbox` in online-async mode with
  Navbot-specific params (range cap 16 m per
  [../../../docs/hardware/lidar-mount.md](../../../docs/hardware/lidar-mount.md)).

## Topics

Published (via `slam_toolbox`):

- `/map` (nav_msgs/OccupancyGrid) — updated online.
- `/tf` — `map → odom`.

Subscribed:

- `/scan` from `navbot_lidar`.
- `/odom` (or `/odometry/filtered` if EKF is running).

## Dependencies

- ROS 2 Jazzy: `slam_toolbox`
  (apt install `ros-jazzy-slam-toolbox`).
- Requires `navbot_lidar` and `navbot_base` (or the bringup equivalent)
  to be producing `/scan` and odometry.

## Warm-up recommendation

For best map quality, warm up the LiDAR motor for 2+ minutes before
starting SLAM. Use `scripts/launch_slam_with_warmup.sh` which bundles
the warm-up with the launch. See
[../../../docs/RUNBOOK.md](../../../docs/RUNBOOK.md).

## Related docs

- LiDAR mount and filters:
  [../../../docs/hardware/lidar-mount.md](../../../docs/hardware/lidar-mount.md)
- Pre-Pi-rebuild DWB session:
  [../../../docs/validation/records/2026-04-18-dwb-rotation-session.md](../../../docs/validation/records/2026-04-18-dwb-rotation-session.md)
