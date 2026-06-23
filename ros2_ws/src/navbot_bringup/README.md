# navbot_bringup

Top-level launch composition package. Wires together `navbot_base`,
`navbot_description`, `navbot_lidar`, `navbot_power`, `navbot_imu`,
`navbot_localization`, `navbot_slam`, and `navbot_navigation` into
operator-facing launch files.

## Launch files

- `launch/base.launch.py` — base bridge + robot description + TF only.
- `launch/base_lidar.launch.py` — base + LiDAR + INA238 power
  telemetry. Canonical starting point for ground tests.
- `launch/imu_localization.launch.py` — base + LiDAR + INA238 + IMU +
  `robot_localization` EKF producing `/odometry/filtered`.
- `launch/slam.launch.py` — wraps `navbot_slam` on top of a running
  base+lidar stack.
- `launch/navigation.launch.py` — wraps `navbot_navigation` (Nav2).

## Dependencies

All other `navbot_*` packages in this workspace.

## Launch

Typical bench run:

```bash
ros2 launch navbot_bringup base_lidar.launch.py
```

See [../../../docs/RUNBOOK.md](../../../docs/RUNBOOK.md) for the full
pre-flight and startup procedure.
