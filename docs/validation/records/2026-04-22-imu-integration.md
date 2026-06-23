# IMU Integration (Session 9) — Layer 1 + 2 + 3 Complete

**Date:** 2026-04-22 late evening, session 9
**Scope:** Two tasks — RPP terminal rotation damping (Task A) and
9-DOF IMU integration (Task B). Both shipped.
**Firmware:** 1.3.0 + counter-drive + wheel_radius 0.0325 m
**Verdict:** SUCCESS. IMU driver publishing at 50 Hz, complementary
filter producing orientation quaternions at 50 Hz, robot_localization
EKF publishing `/odometry/filtered` at 30 Hz. Nav2 switched over to
the fused odometry. 180° in-place rotation executed as a clean
monotonic sweep with zero oscillation — previously oscillated 50–90°.

## Task A — RPP terminal rotation damping

Quick YAML fix motivated by the oscillation observed in
[2026-04-22-wheel-radius-fix.md](2026-04-22-wheel-radius-fix.md).

```yaml
FollowPath:
  rotate_to_heading_angular_vel: 0.5 → 0.3
  max_angular_accel:              1.5 → 1.0
```

**Verification:** 1.0 m + 90° composite goal. Robot rotated steadily
at ~0.29 rad/s (matching new cap) through 150° of arc with no visible
back-and-forth. Committed as `69b5e75`.

## Task B — IMU integration

### Hardware

| Chip | I²C address | Function | Identity verified |
|---|---|---|---|
| L3G4200D | 0x69 | Gyro | WHO_AM_I = 0xD3 ✓ |
| LSM303DLHC accel | 0x19 | Accel | STATUS_REG_A responds ✓ |
| LSM303DLHC mag | 0x1E | Mag | IDA/IDB/IDC = "H43" ✓ |

Physical mount: at ~35 mm from ground (axle height), centred
fore-aft, sensor-X pointing robot-forward. IMU had been at chassis
top (~80 mm) before this session; relocating brought it closer to
the robot's centre of rotation.

### Phase 0 — raw sensor verification

```
Gyro (L3G4200D) at rest:
  Noise per axis < 1 dps, ~0.25 dps RMS
  Clean, low-noise gyro

Accel (LSM303DLHC) flat:
  X = -0.006 g, Y = +0.023 g, Z = +0.897 g
  |vec| = 0.897 g (11 % low scale factor — typical for this chip)
  Z positive → mounted Z-up
  Axes verified via tilt test (below)

Mag (LSM303DLHC):
  X = +0.273, Y = +1.385, Z = -0.256 gauss
  |vec| = 1.434 gauss (2.3× Earth's max of 0.65 gauss)
  Strong local magnetic source — almost certainly the motor gearbox
  permanent magnets now closer to the sensor after axle-height mount.
  Hard-iron bias of this magnitude blocks meaningful compass fusion
  without calibration → mag deferred (backlog item).
```

#### Axis mapping verification

User performed two physical tests after repositioning:

**Test 1 — tilt nose-down by ~23°:**
```
accel.x = -3.331 m/s²  (-0.34 g, negative as expected for X-forward)
accel.y = +0.153 m/s²  (stayed ~zero)
accel.z = +7.963 m/s²  (reduced from rest by cos(23°) factor)
```
Computed tilt: arcsin(3.33/8.63) = 22.7°. Confirms **sensor-X aligns
with robot-forward**.

**Test 2 — rotate robot 90° CCW:**
```
quaternion.z = +0.6667 → yaw = +83.6°
```
Positive yaw for CCW rotation confirms **right-hand-rule Z-up
convention** is correct.

Final mapping: identity (`sensor_orientation: x_forward` in config).
No remap of axes required.

### Phase 1 — IMU driver node

Used the existing `navbot_imu` package (Pi-side skeleton from session
3 or 4) with two patches:

1. Added `sensor_orientation` parameter — `"x_forward"` or `"y_forward"`.
   `"x_forward"` is identity (new mount); `"y_forward"` is the original
   `(robot_x = sensor_y, robot_y = -sensor_x)` remap.
2. Bumped `poll_hz: 20 → 50` for higher-rate filter fusion.

Topics (after launch remap to standard names):

| Topic | Type | Rate | Notes |
|---|---|---|---|
| `/imu/data_raw` | `sensor_msgs/Imu` | 50 Hz | Gyro + accel, orientation zeroed |
| `/imu/mag` | `sensor_msgs/MagneticField` | 50 Hz | Published but unused (use_mag=false) |
| `/imu/l3gd20_lsm303d/ypr` | `geometry_msgs/Vector3Stamped` | 50 Hz | Legacy compass YPR (kept for backwards compat) |
| `/imu/l3gd20_lsm303d/status` | `std_msgs/String` | 50 Hz | JSON probe status |

URDF `imu_joint` moved from `(0, 0, ${base_height} = 0.06)` to
`(0, 0, 0.035)` to match the new axle-height mount.

### Phase 2 — complementary filter

`imu_complementary_filter` (apt-installed) consumes `/imu/data_raw`
(with optional `/imu/mag`) and publishes `/imu/data` with the
orientation quaternion filled in.

Key parameters (set in `imu_fusion.launch.py`):
```python
use_mag: False       # mag deferred — local field too distorted
do_bias_estimation: True
do_adaptive_gain: True
gain_acc: 0.01       # trust gyro short-term; slow accel correction
publish_tf: False    # EKF owns the TF
```

Verified `/imu/data` publishing at 50 Hz with valid orientation
quaternion.

### Phase 3 — robot_localization EKF

`ros-jazzy-robot-localization` EKF fusing wheel odometry (x, y, vx)
and IMU fused output (yaw, vyaw). Magnetometer excluded.

Key config in [ekf.yaml](../../../ros2_ws/src/navbot_localization/config/ekf.yaml):
```yaml
use_sim_time: false
frequency: 30.0
two_d_mode: true
publish_tf: true
base_link_frame: base_footprint
world_frame: odom

odom0: /odom
odom0_config: [true, true, false,      # x, y
               false, false, false,    # no yaw from wheels
               true, false, false,     # vx
               false, false, false,
               false, false, false]

imu0: /imu/data
imu0_config: [false, false, false,
              false, false, true,      # yaw (ABSOLUTE)
              false, false, false,
              false, false, true,      # vyaw
              false, false, false]
```

#### Launch-time gotcha — fixed

`ekf.launch.py` had `parameters=[params_file, {"use_sim_time": LaunchConfiguration("use_sim_time")}]`.
At launch time, the `LaunchConfiguration` resolves to a **string**.
`robot_localization` does not coerce string→bool for `use_sim_time`,
so it treats any non-empty string (including `"false"`) as truthy and
blocks forever on `"Waiting for clock to start..."`.

Fix: removed the dict override entirely. `use_sim_time: false` now
lives only in the yaml (read as a proper bool).

#### TF-chain coordination

With EKF publishing `odom → base_footprint`, the wheel-odometry TF
broadcaster in `navbot_serial_bridge` had to stop publishing that
transform or the two would fight. Flipped `publish_tf: true → false`
in [navbot_base.yaml](../../../ros2_ws/src/navbot_base/config/navbot_base.yaml).

Pre-EKF bring-up (no `ekf_node` in the launch) now requires re-enabling
`publish_tf: true` via launch argument or yaml override.

### Nav2 integration

Switched Nav2's `odom_topic` from `/odom` to `/odometry/filtered` in
both `bt_navigator` and `velocity_smoother` config blocks. Confirmed
at runtime via `ros2 param get`.

## End-to-end validation — 180° in-place rotation

Goal: body-frame `(0, 0, +π)` from start yaw = -22.5°. 30 s timeout.

| Metric | Value |
|---|---|
| Start yaw | -22.5° |
| Goal yaw | +157.5° |
| End yaw | +169.9° |
| Terminal overshoot | **12.4°** (well within `yaw_goal_tolerance: 0.25 rad = 14.3°`) |
| Rotation duration | 10.65 s |
| Rotation rate | ~16°/s = 0.28 rad/s (matches `rotate_to_heading_angular_vel: 0.3`) |
| `cmd_vel_nav.ang.z` | 108 samples at **-0.287 ± 0.013 rad/s** (no reversal) |
| `cmd_vel_nav.lin.x` | all zeros |
| Nav2 status | 4 (SUCCEEDED) |

**Pre-EKF baselines for the same behaviour:**

| Session | Setup | Terminal yaw behavior |
|---|---|---|
| Session 8 | Pre-damping, wheel-odom yaw | 95° overshoot + oscillation |
| Session 9 Task A | Damped rotation, wheel-odom yaw | 13° error + one direction reversal |
| Session 9 Phase 3 | **Damped + EKF + IMU yaw** | **Clean monotonic 157° arc, no reversal, no oscillation** |

The 12.4° terminal error is essentially the goal_checker's "settling
delay" — one or two control cycles past the exact goal yaw before
acceptance — not a control system oscillation. The `cmd_vel_nav`
stream shows 108 samples at a constant -0.287 rad/s with tiny jitter
(σ = 0.013 rad/s = 4 % of setpoint), which is what stable yaw input
to a rotate-to-heading controller is supposed to produce.

## TF chain summary

```
map → odom             (slam_toolbox)
odom → base_footprint  (ekf_filter_node  ← NEW owner this session)
base_footprint → base_link, laser_link, imu_link  (URDF)
```

Prior: `odom → base_footprint` was published by `navbot_serial_bridge`
from wheel encoders only.

## Topic summary

| Topic | Owner | Rate | Consumers |
|---|---|---|---|
| `/odom` | `navbot_serial_bridge` | 10 Hz | EKF (topic only, NOT TF) |
| `/imu/data_raw` | `l3gd20_lsm303d_reader` | 50 Hz | complementary filter |
| `/imu/mag` | `l3gd20_lsm303d_reader` | 50 Hz | (unused, backlog cal) |
| `/imu/data` | `imu_complementary_filter` | 50 Hz | EKF |
| `/odometry/filtered` | `ekf_filter_node` | 30 Hz | **Nav2**, user code |

## Known residuals / backlog

1. **Magnetometer calibration deferred.** Hard-iron offset of ~1.4 gauss
   means raw mag readings are useless for absolute heading until we
   do a figure-8 or 3D-rotation calibration pass and subtract the
   bias at read time (or recompute it whenever the IMU's physical
   relationship to motors changes). `use_mag: false` in the
   complementary filter for now. Opening as backlog item.
2. **Terminal rotation still overshoots by ~12°** even with EKF-stable
   yaw. This is a goal_checker "one-cycle-past-goal" artifact at
   0.3 rad/s × 10 Hz loop = 3° per cycle plus detection delay. Can
   be tightened by lowering `rotate_to_heading_angular_vel` further
   or tightening `yaw_goal_tolerance` — trade-off is slower
   convergence. Acceptable as-is for first integration.
3. **Pre-EKF bring-up procedure broken.** `navbot_base.yaml` now has
   `publish_tf: false` as the default. If an operator wants to run
   base-only (no EKF), they must override the param. Document in
   RUNBOOK; consider adding a launch arg to toggle.
4. **`wheel_radius` in `navbot_base.yaml` still reads `0.033`** —
   firmware was fixed to 0.0325 in session 8 but ROS-side config
   wasn't updated. Need to audit whether the bridge uses this value
   for any local calculation, and align if so.

## Cross-references

- RPP damping (Task A), this session: commit `69b5e75`
- IMU integration (Task B), this session: the commit this record lands in
- Pre-IMU heading drift context:
  [2026-04-22-nav2-four-step-sequence.md](2026-04-22-nav2-four-step-sequence.md),
  [2026-04-22-wheel-radius-fix.md](2026-04-22-wheel-radius-fix.md)
- IMU driver: [ros2_ws/src/navbot_imu/navbot_imu/l3gd20_lsm303d_reader.py](../../../ros2_ws/src/navbot_imu/navbot_imu/l3gd20_lsm303d_reader.py)
- IMU config: [ros2_ws/src/navbot_imu/config/l3gd20_lsm303d.yaml](../../../ros2_ws/src/navbot_imu/config/l3gd20_lsm303d.yaml)
- Fusion launch: [ros2_ws/src/navbot_imu/launch/imu_fusion.launch.py](../../../ros2_ws/src/navbot_imu/launch/imu_fusion.launch.py)
- Stack launch: [ros2_ws/src/navbot_bringup/launch/slam_imu.launch.py](../../../ros2_ws/src/navbot_bringup/launch/slam_imu.launch.py)
- EKF config: [ros2_ws/src/navbot_localization/config/ekf.yaml](../../../ros2_ws/src/navbot_localization/config/ekf.yaml)
- URDF imu_link update: [ros2_ws/src/navbot_description/urdf/navbot.urdf.xacro](../../../ros2_ws/src/navbot_description/urdf/navbot.urdf.xacro)
- Project status: [../../project-status.md](../../project-status.md)
