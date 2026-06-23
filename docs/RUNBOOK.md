# Navbot Runbook

Operator runbook for the Navbot Pi 5 + Maker Pi RP2040 platform. If you
are powering the robot on for the first time in a session, **start with
the pre-flight safety checklist** before any motion command.

Cross-links:

- System architecture: [architecture.md](architecture.md)
- Power/battery details: [power-architecture.md](power-architecture.md)
- Validation history: [VALIDATION.md](VALIDATION.md)
- Web console operator notes: [WEB_CONSOLE.md](WEB_CONSOLE.md)

---

## Pre-flight Safety Checklist

Run through this list every session before issuing any motion command,
SLAM command, or Nav2 goal. The checklist assumes the robot is
physically accessible and you can see it during the test.

### Power state

- [ ] **System 1 (Pi rail)**: battery pack switch state recorded:
      `________` (OFF / ON). 4× 18650 pack, 16.8V nominal.
- [ ] **System 2 (LiDAR rail)**: battery pack switch state recorded:
      `________` (OFF / ON). 2× 18650 pack, 8.4V nominal.
- [ ] **System 3 (Motor rail)**: battery pack switch state recorded:
      `________` (OFF / ON). 5V dedicated motor pack.
- [ ] Pi power source verified:
      `[ ] USB-C wall adapter` `[ ] System 1 battery` `[ ] both`.
- [ ] **CRITICAL — Pi 5V isolation** (only matters if test procedure
      assumes Pi is electrically isolated from System 1):
  - Pi 5 USB-C input and GPIO 5V pin OR together through internal
    diodes. Wall adapter alone does NOT isolate.
  - On 2026-04-20, 0.94 A was measured flowing through the INA238
    shunt while Pi was on USB-C — confirming real battery draw even
    with wall power present.
  - To actually isolate: physically disconnect GPIO 5V jumper OR
    switch System 1 battery pack OFF.
  - Verify by reading `/power/ina238/current_a` BEFORE motion.
    Expected if isolated: near 0 A. See
    [power-architecture.md](power-architecture.md#system-1-pi-compute).

### Physical state

- [ ] Robot footprint clear of obstructions (include a safety margin
      wider than the largest expected motion distance).
- [ ] All three wheels spin freely when manually rotated.
- [ ] LiDAR cable seated. **Arrow BACKWARD, cable FORWARD** — this is
      the C1 mount convention.
- [ ] No loose wires near wheels, no shipping zip ties left on motors.

### Emergency stop

- [ ] Emergency stop method confirmed and understood before motion.
      Primary: `Ctrl-C` in the bringup terminal. Secondary: web-console
      red STOP (if running). Tertiary: physically power-cycle System 3
      battery pack (motor rail).
- [ ] STOP latency tested on current session: commanded STOP stops the
      robot within one control cycle.

### Software state

- [ ] No stale ROS 2 nodes from prior session. Run
      `ros2 node list` — it should be empty before launching bringup.
- [ ] I²C devices responsive:
      ```bash
      i2cdetect -y 1
      ```
      Expect at minimum `0x40` (INA238). IMU addresses `0x69`, `0x19`,
      `0x1E` visible if IMU launch is planned.
- [ ] Serial-by-id paths present:
      `ls /dev/serial/by-id/` shows both the RP2040 and CP2102 entries.
- [ ] Git HEAD current, firmware version matches expected for this test.

---

## Three-Battery Power Architecture (Summary)

Three electrically-independent battery systems. Each has its own switch
and its own step-down converter. Summary here; full details in
[power-architecture.md](power-architecture.md).

| System | Battery | Purpose | Monitoring |
|---|---|---|---|
| System 1 | 4× 18650 (16.8V nom) | Pi 5 compute + I²C sensors | INA238 on Pi rail via I²C 0x40 |
| System 2 | 2× 18650 (8.4V nom)  | RPLIDAR C1 + RP2040 sensing | RP2040 ADC → `/base/lidar_voltage` |
| System 3 | 5V motor pack        | Maker Pi RP2040 VIN → motors | RP2040 VIN divider → `/base/motor_voltage` (rail-scaled artifact — see gotchas) |

**Do not assume "Pi on wall power = Pi isolated from System 1."** See
the critical safety callout in the pre-flight checklist.

---

## Startup Procedure

1. Pre-flight checklist complete.
2. Power state per the test plan (e.g. System 1 OFF if isolation test,
   System 1 ON if full-stack soak).
3. SSH to Pi:
   ```bash
   ssh arif@192.168.68.101
   ```
4. Source environment (new shell):
   ```bash
   source /opt/ros/jazzy/setup.bash
   source ~/projects/claude-navbot/ros2_ws/install/setup.bash
   ```
5. Launch the required bringup (base-only, base+lidar, or
   imu+localization — see Launch section).
6. Verify liveness in a second SSH session:
   ```bash
   ros2 node list | sort
   ros2 topic hz /scan                  # expect ~10 Hz
   ros2 topic echo /power/ina238/status --once
   ros2 topic echo /base/controller_state --once
   ```
   Controller state should be `IDLE OK`.
7. Only now issue motion commands.

---

## Shutdown Procedure

1. Issue a STOP and wait for the controller to report `IDLE OK`.
2. In each terminal running bringup/SLAM/Nav2, press `Ctrl-C`. Wait
   for each node to exit cleanly before closing the terminal.
3. Confirm `ros2 node list` is empty.
4. If running any capture, verify `capture_meta.json` wrote successfully
   (otherwise the capture is not usable).
5. Power down Pi cleanly:
   ```bash
   sudo shutdown -h now
   ```
   Wait for the Pi to go dark before removing power.
6. Switch OFF all three battery packs. Record final pack state in the
   session notes.

---

## Incident Response

### Motor runaway (unexpected continued motion)

1. Press `Ctrl-C` in the bringup terminal.
2. If motion continues, physically switch OFF the System 3 battery pack.
3. Inspect `/cmd_vel` and `/base/controller_state` topics to confirm
   what was commanded vs what was executed.
4. Do NOT re-enable System 3 until root cause is identified. Check
   firmware command-timeout behavior and ESTOP response before resuming.

### LiDAR thermal trip / `/scan` goes silent

1. Check `ros2 topic hz /scan`. If no output, check
   `journalctl -k --since "10 min ago" | grep -Ei "cp210|ttyUSB|disconnect"`.
2. If the CP2102 re-enumerated, `sllidar_node` is holding a deleted fd.
   Kill and relaunch the bringup.
3. If the LiDAR itself is hot to the touch, let it cool. The RPLIDAR C1
   has no thermal protection — extended runs on a poorly-ventilated
   mount can brown out.
4. Check System 2 voltage: `ros2 topic echo /base/lidar_voltage --once`.
   If low, charge System 2. A `-110` on CP210x control transfer `0x12`
   is often a low-battery symptom, not a USB-bus fault.

### Pi kernel panic or full freeze

1. Power-cycle the Pi: USB-C unplug + System 1 battery OFF.
2. After reboot, check `journalctl --since "30 min ago" --no-pager`
   for the crash trace. Save the output in the session notes.
3. Check `dmesg | tail -200` for driver errors around the time of
   the crash.
4. If a specific node is suspect, relaunch that node in isolation
   and try to reproduce before bringing the full stack back up.

### Battery low voltage (any system)

- **System 1 low** (Pi): INA238 rail drops toward 4.8 V. Expect USB
  devices to start dropping. Immediately stop the test, shut down
  the Pi, recharge System 1.
- **System 2 low**: `/base/lidar_voltage` trending low. LiDAR begins
  to report USB control-transfer errors. Stop, recharge.
- **System 3 low**: Motor torque starts falling off at the same PWM
  duty. Stop, recharge before tuning further.

---

## Build And Sync

```bash
cd /home/arif/projects/makerpi-rp2040-ros2-navbot
./scripts/sync_pi_repo.sh --hard --build
```

Use `--hard` only when GitHub should be treated as source truth and Pi-side source drift should be discarded. It does not remove ignored runtime outputs such as captures or `ros2_ws/install`.

Manual build:

```bash
cd /home/arif/projects/makerpi-rp2040-ros2-navbot
./scripts/build_ros2_ws.sh
```

Required runtime environment:

```bash
source /opt/ros/jazzy/setup.bash
source /home/arif/ros2_ws/install/setup.bash
source /home/arif/projects/makerpi-rp2040-ros2-navbot/ros2_ws/install/setup.bash
```

The external `/home/arif/ros2_ws/install/setup.bash` overlay provides the validated `sllidar_ros2` runtime.

## Launch

Base only:

```bash
ros2 launch navbot_bringup base.launch.py \
  serial_port:=/dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00
```

Base + LiDAR + INA238:

```bash
ros2 launch navbot_bringup base_lidar.launch.py
```

Base + LiDAR + INA238 + IMU + EKF:

```bash
ros2 launch navbot_bringup imu_localization.launch.py
```

Web console:

```bash
cd /home/arif/projects/makerpi-rp2040-ros2-navbot
./scripts/launch_web_console.sh port:=8081
```

Open:

```text
http://192.168.15.20:8081
```

SLAM:

```bash
./scripts/launch_slam.sh serial_port:=/dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00
```

For best C1 measurement accuracy, warm up the spinning LiDAR first:

```bash
LIDAR_WARMUP_SECONDS=120 ./scripts/launch_slam_with_warmup.sh serial_port:=/dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00
```

## Expected Devices

- RP2040:
  - `/dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00`
- LiDAR serial/data adapter:
  - `/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0`
- INA238:
  - Pi `i2c-1`, address `0x40`
- IMU:
  - gyro `0x69`, accelerometer `0x19`, magnetometer `0x1E`

The RPLIDAR C1 is individually powered. USB is still required for the CP2102 serial/data link, and USB re-enumeration can still make `/scan` stale.

## Smoke Checks

```bash
ros2 node list | sort
ros2 topic info /scan
ros2 topic info /power/ina238/status
ros2 topic info /imu/l3gd20_lsm303d/raw
ros2 topic info /imu/l3gd20_lsm303d/ypr
ros2 topic info /heading_controller/status
ros2 topic info /odometry/filtered
ros2 topic hz /scan
ros2 topic hz /imu/l3gd20_lsm303d/raw
ros2 topic echo /imu/l3gd20_lsm303d/ypr --once
ros2 topic echo /odometry/filtered --once
curl -fsS http://127.0.0.1:8081/api/status | python3 -m json.tool
```

Healthy recent rates:

- `/scan`: about `10 Hz`
- `/imu/l3gd20_lsm303d/raw`: about `20 Hz`

## Ground-Test Procedure

1. Confirm estop and STOP are reachable.
2. Confirm the web console shows ROS, base, LiDAR, INA238, and IMU as live.
3. Start with wheels clear or on open ground.
4. Press and release `Forward`.
5. Press and release `Backward`.
6. Press and release `Rotate Left`.
7. Press and release `Rotate Right`.
8. Press red `STOP`.
9. Only continue to SLAM if `/scan`, `/odom`, `/joint_states`, and `/base/controller_state` stay fresh.

Validated cautious SLAM sequence:

1. stationary sanity
2. short forward
3. idle
4. short left turn
5. idle
6. short forward
7. idle
8. short right turn
9. idle
10. short backward
11. idle
12. final stop

## Capture Workflow

The web console records:

```text
/scan
/odom
/tf
/tf_static
/joint_states
/base/controller_state
/base/estop
/cmd_vel
/imu/l3gd20_lsm303d/raw
/imu/l3gd20_lsm303d/mag
/imu/l3gd20_lsm303d/ypr
/heading_controller/status
/odometry/filtered
```

Expected output:

```text
captures/YYYY-MM-DD_HH-MM-SS_<label>/
```

Each capture should contain `capture_meta.json`, `record.log`, and bag data under `bag/`.

## Troubleshooting

If `/scan` is stale but `sllidar_node` exists:

```bash
pid=$(pidof sllidar_node)
ls -l /proc/$pid/fd | grep tty
```

If the fd points to `/dev/ttyUSB* (deleted)`, the CP2102 serial/data adapter re-enumerated. Restart the launch so it reopens the by-id path.

If power telemetry is stale:

```bash
ros2 topic echo /power/ina238/status --once
i2cdetect -y 1
```

Expected INA238 address: `0x40`.

If `/power/ina238/*` topics publish but all values are zero (voltage,
current, power) — **check the System 1 battery pack switch first**.
Zero readings with a healthy driver typically mean the Pi rail is being
fed from somewhere other than the buck (e.g. USB-C wall only, pack OFF),
not a driver bug. See [power-architecture.md](power-architecture.md).

If Pi undervoltage appears in kernel logs, treat it as real hardware risk:

```bash
journalctl -k --since "10 min ago" --no-pager | grep -Ei "under.?voltage|voltage|cp210|ttyUSB|disconnect"
```

Do not continue broader motion or SLAM on an unstable supply path.

### Nav2 lifecycle stuck in `inactive` with LiDAR off

When running Nav2 (`scripts/launch_nav.sh`) with **LiDAR power off** for
bench-level testing, `lifecycle_manager_navigation` does not auto-activate
all downstream nodes. `behavior_server`, `collision_monitor`, and
`velocity_smoother` will report `inactive [2]` and `drive_on_heading`
goals will be rejected.

Check lifecycle states:

```bash
for n in behavior_server collision_monitor velocity_smoother controller_server planner_server bt_navigator smoother_server; do
  echo "  /$n -> $(ros2 lifecycle get /$n 2>/dev/null)"
done
```

If any of the first three are `inactive`, manually activate:

```bash
ros2 lifecycle set /velocity_smoother activate
ros2 lifecycle set /collision_monitor activate
ros2 lifecycle set /behavior_server activate
```

These transition directly to `active [3]` and the full Nav2 action API
(including `drive_on_heading`) becomes available.

This workaround is needed every time Nav2 is restarted while LiDAR is
powered off. Tracked as an open item in
[project-status.md](project-status.md); permanent fix is either adjusting
the Nav2 lifecycle config to not block on `/scan` or documenting as
permanent LiDAR-off bench procedure.

### Counter-drive FAULT recovery

If CDRIVE telemetry shows `l_state=4` or `r_state=4` (FAULT) or any
non-zero `_fault` field, recovery is:

```text
STOP\n
```

over serial (or any equivalent CMD_STOP invocation). This invokes
`counter_drive_reset()` on both motors: states return to IDLE (0),
`last_fault` clears, the watchdog alarm disarms, and `shared_abort` is
released iff both motors are non-FAULT. `RESET\n` works similarly and
additionally clears a latched safety fault (ESTOP / STALL / RUN_TIMEOUT).
