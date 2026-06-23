# RPLIDAR C1 Mount

Physical mount conventions, filter pipeline, and power details for the
RPLIDAR C1 on the Navbot platform. For electrical power and monitoring,
see [../power-architecture.md](../power-architecture.md#system-2-lidar)
(System 2).

## Orientation convention

**Arrow BACKWARD, cable FORWARD.**

The C1 has a small arrow engraved on the top of the rotor housing that
indicates the sensor's own "forward" axis. For this robot, we mount the
C1 so that the arrow points BACKWARD relative to the robot chassis and
the data cable exits toward the FRONT. This means the LiDAR's 0° is
robot-rear, not robot-front.

This is compensated in the URDF by rotating the `laser_link` frame
relative to `base_link`. The `sllidar_ros2` driver publishes `/scan` in
the LiDAR's native frame; the URDF rotation makes Foxglove, Nav2, and
slam_toolbox see a scan that aligns with a "robot forward = +X" world.

**Pre-flight check:** visually confirm the arrow orientation every
session before launch. A rotated LiDAR produces a scan that looks
roughly right but is rotated, which causes subtle SLAM map drift and
confusing Nav2 costmap behavior.

## Physical mount measurements

| Axis | Offset from `base_link` | Source |
|---|---|---|
| X  (forward+)  | 35 mm | Physical measurement (commit `1952f6a`) |
| Y  (left+)     | 0 mm  | On robot centerline |
| Z  (up+)       | (measure per build) | URDF `laser_link` origin |

The X offset was previously declared as 70 mm in the URDF — wrong.
Commit `1952f6a` corrected it to the measured 35 mm. See
[pi-rebuild.md](pi-rebuild.md) for the bug #4 writeup.

## Serial / data path

- USB serial via the CP2102 USB-to-UART bridge on the LiDAR tail.
- Stable by-id path:

  ```text
  /dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0
  ```

- Baud: default handled by `sllidar_ros2` driver.
- Enumeration fragility: the CP2102 can re-enumerate under transient
  low battery or USB-hub disturbance. `sllidar_node` keeps the old fd
  open (points to `/dev/ttyUSB* (deleted)`), so `/scan` goes stale but
  the node doesn't error out. See [../RUNBOOK.md](../RUNBOOK.md)
  troubleshooting section for the fix recipe.

## Scan filter pipeline

Configured in `navbot_lidar` package and `navbot_bringup` launches.

1. **`+Inf` beam filter** (commit `4565c25`): replaces infinite-range
   beams with NaN. The C1 reports `+inf` for out-of-range hits; Nav2
   costmap treats `+inf` as a hit at max range, which produces
   phantom walls at the sensor's horizon. NaN is correctly treated
   as "no return" by Nav2.
2. **slam_toolbox range cap at 16 m** (commit `4565c25`): the C1 spec
   maxes out around 12 m in practice; 16 m is a generous cap that
   rejects any reading beyond that as unreliable. Per Slamtec's own
   C1 developer guidance, longer-range readings are low-fidelity.

See the filter YAML in
[../../ros2_ws/src/navbot_lidar/config/](../../ros2_ws/src/navbot_lidar/config/)
for the runtime values.

## Warm-up

Per Slamtec's C1 manual, best measurement accuracy requires the scan
motor to be spinning for more than 2 minutes before collecting data.
The helper script that bundles warm-up with SLAM:

```bash
LIDAR_WARMUP_SECONDS=120 ./scripts/launch_slam_with_warmup.sh \
  serial_port:=/dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00
```

Omitting warm-up is fine for bench teleop but produces noisier early
scan frames that can hurt initial SLAM map quality.

## Known symptom: CP210x `-110` on control transfer `0x12`

This error in dmesg is usually **System 2 battery undervoltage**, not
a USB bus fault. The LiDAR brown-outs on low pack voltage produce
USB control-transfer timeouts that surface as `-110`. Check
`/base/lidar_voltage` before assuming USB is the problem. See
[../power-architecture.md](../power-architecture.md#system-2-lidar).

## Cable routing and strain relief

- Route the USB cable forward and down, away from the rotating LiDAR
  top. The C1 has no slip-ring, so a cable snagged near the rotor
  will over-rotate the housing relative to its base and damage the
  internal encoder.
- Use strain relief at the Pi-side USB connector. Repeated hot-plug
  stresses the CP2102 breakout's USB contact.
