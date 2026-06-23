# navbot_lidar

Wrapper around the upstream `sllidar_ros2` driver for the RPLIDAR C1.
This package does not vendor the driver; it only provides launch files,
parameters, and the filter pipeline that match our deployment.

## Launch files

- `launch/` — wrapper launches that start `sllidar_node` with the
  Navbot-specific serial path, frame ID, and filter chain.

## Topics

Published (via upstream `sllidar_node`):

- `/scan` (sensor_msgs/LaserScan) — frame `laser_link`, 720 beams,
  ~10 Hz.

## Serial path

Stable by-id expected:

```text
/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0
```

udev symlink available at `/dev/navbot_lidar` (see
[../../../scripts/setup-pi.sh](../../../scripts/setup-pi.sh)).

## Filter pipeline

1. `+Inf` beams replaced with NaN so Nav2 does not treat max-range
   hits as phantom walls (commit `4565c25`).
2. slam_toolbox range cap at 16 m (commit `4565c25`) — C1 spec maxes
   at ~12 m; longer readings are low-fidelity per Slamtec's guidance.

## Dependencies

- Upstream `sllidar_ros2` must be installed on the target (provided
  via vcs import in `scripts/setup-pi.sh`).
- Hardware: RPLIDAR C1 on CP2102 USB serial adapter.

## Related docs

- Mount convention (arrow BACKWARD, cable FORWARD):
  [../../../docs/hardware/lidar-mount.md](../../../docs/hardware/lidar-mount.md)
- Power (System 2): [../../../docs/power-architecture.md](../../../docs/power-architecture.md)
