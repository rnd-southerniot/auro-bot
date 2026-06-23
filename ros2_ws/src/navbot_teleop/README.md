# navbot_teleop

Convenience launches for teleoperation. No custom nodes — only
wraps upstream `teleop_twist_keyboard`, `teleop_twist_joy`, and the
`joy` driver with Navbot-specific topic remaps and joystick mapping.

## Launch files

- `launch/` — keyboard and joystick teleop launches.

## Topics

Published:

- `/cmd_vel` (geometry_msgs/Twist) — drive command to `navbot_base`.

## Dependencies

- ROS 2 Jazzy: `teleop_twist_keyboard`, `teleop_twist_joy`, `joy`,
  `joy-linux`
  (apt install `ros-jazzy-teleop-twist-keyboard ros-jazzy-teleop-twist-joy ros-jazzy-joy ros-jazzy-joy-linux`).
- Hardware: optional Xbox/PS4/generic USB gamepad. udev rules in
  `scripts/setup-pi.sh` handle permissions.

## Launch

Keyboard:

```bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard
```

Joystick (Xbox-style):

```bash
ros2 launch teleop_twist_joy teleop-launch.py joy_config:=xbox
```

Web/phone teleop is now preferred via Foxglove (see
[../../../docs/operations/foxglove/README.md](../../../docs/operations/foxglove/README.md))
or via the legacy `navbot_web` console
([../navbot_web/README.md](../navbot_web/README.md)).
