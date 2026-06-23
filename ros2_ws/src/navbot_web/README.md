# navbot_web

Local-network browser ground-test console. Provides hold-to-move teleop,
an explicit STOP, base/LiDAR/IMU/power/estop freshness, and rosbag
capture start/stop for selected topics.

> **Status note (2026-04 onward):** this package is being succeeded by
> Foxglove bridge for new Navbot work. It is still shipped and still
> the canonical way to run rosbag captures; for visualization-only
> sessions, prefer Foxglove (see
> [../../../docs/operations/foxglove/README.md](../../../docs/operations/foxglove/README.md)).
> Full operator notes and transition context live in
> [../../../docs/operations/web-console.md](../../../docs/operations/web-console.md).

## Nodes / Executables

- `web_console` — HTTP/WebSocket server on the Pi. Serves the static
  operator UI and proxies ROS topics / capture commands.

## Subscribed / published

The console reads the topics documented in the capture workflow in
[../../../docs/operations/web-console.md](../../../docs/operations/web-console.md)
and publishes `/cmd_vel` for teleop commands.

## Launch

```bash
cd ~/projects/claude-navbot
./scripts/launch_web_console.sh port:=8081
```

Then open `http://<pi-ip>:8081`.

## Dependencies

- ROS 2 Jazzy: `rclpy`, `geometry_msgs`, `std_msgs`, `sensor_msgs`,
  `nav_msgs`.
- External: the Python HTTP stack bundled with the package.

## Related docs

- Operator detail: [../../../docs/operations/web-console.md](../../../docs/operations/web-console.md)
- Recommended successor: [../../../docs/operations/foxglove/README.md](../../../docs/operations/foxglove/README.md)
