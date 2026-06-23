# navbot_power

INA238-based power telemetry for the Pi 5 compute rail (System 1).
Chip, wiring, and troubleshooting detail is in
[../../../docs/hardware/ina238.md](../../../docs/hardware/ina238.md);
this README covers the ROS 2 package shape only.

## Nodes / Executables

- `ina238_reader` — polls the INA238 at 2 Hz and publishes rail
  voltage, current, power, shunt voltage, and die temperature.

## Topics

Published:

- `/power/ina238/bus_voltage_v` (std_msgs/Float32, volts)
- `/power/ina238/current_a` (std_msgs/Float32, amperes, signed)
- `/power/ina238/power_w` (std_msgs/Float32, watts)
- `/power/ina238/temperature_c` (std_msgs/Float32, °C)
- `/power/ina238/shunt_voltage_v` (std_msgs/Float32, volts)
- `/power/ina238/status` (std_msgs/String) — JSON envelope with
  `available` flag and human message.

## Dependencies

- ROS 2 Jazzy: `rclpy`, `std_msgs`.
- External: `smbus2`.
- Hardware: INA238 breakout on Pi I²C-1, address `0x40`.

## Launch

```bash
ros2 launch navbot_power ina238.launch.py
```

Auto-launched by `navbot_bringup/base_lidar.launch.py` and
`navbot_bringup/imu_localization.launch.py`.

## Related docs

- Chip detail and troubleshooting matrix:
  [../../../docs/hardware/ina238.md](../../../docs/hardware/ina238.md)
- Three-battery power architecture + Pi USB-C non-isolation finding:
  [../../../docs/power-architecture.md](../../../docs/power-architecture.md)
