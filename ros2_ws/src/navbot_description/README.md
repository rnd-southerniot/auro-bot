# navbot_description

Robot description (URDF/Xacro) and RViz assets for the Navbot platform.

## Contents

- `urdf/` — Xacro sources for the robot body, wheels, caster, and
  LiDAR mount. The physical measurements here are ground truth — see
  [../../../docs/hardware/lidar-mount.md](../../../docs/hardware/lidar-mount.md)
  for the current offsets and the history of corrections.
- `launch/` — `robot_state_publisher` launch(es) that consume the
  Xacro and publish `/tf_static` + `/robot_description`.
- `rviz/` — RViz configurations for visualization.

## Topics published (via robot_state_publisher)

- `/robot_description` (std_msgs/String) — serialized URDF.
- `/tf_static` — `base_footprint → base_link → *` joint tree.

## Key constants

- `wheel_radius = 0.0325 m` (validated — see
  [../../../docs/testing/motion-tests.md](../../../docs/testing/motion-tests.md)).
- `laser_link` X offset from `base_link`: 35 mm.

## Related docs

- Hardware convention: [../../../docs/hardware/lidar-mount.md](../../../docs/hardware/lidar-mount.md)
- Pi rebuild (URDF-related bugs fixed): [../../../docs/hardware/pi-rebuild.md](../../../docs/hardware/pi-rebuild.md)
