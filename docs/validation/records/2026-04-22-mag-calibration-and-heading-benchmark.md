# Magnetometer Calibration, wheel_radius Audit, Heading Drift Benchmark (Session 10)

**Date:** 2026-04-22 (session 10, after session 9 IMU integration)
**Scope:** Three calibration tasks + empirical heading benchmark
**Firmware:** 1.3.0 with counter-drive (flashed with 0.0325 wheel_radius, session 8)
**Verdict:** MIXED — mag calibration succeeded but mag fusion degraded heading
during motion; wheel_radius alignment shipped cleanly; heading benchmark
quantified that raw /odom is excellent on this chassis (0.36° round-trip)
while mag-fused EKF was worse during motion (9.73°). Mag fusion reverted
to `use_mag: false`.

## Task 1 — Magnetometer hard-iron calibration

### Step 1 — saturation diagnosed

Initial 60 s rotation sweep (at default ±1.3 gauss gain) showed Y axis
saturating:

| Axis | min (gauss) | max (gauss) | peak-to-peak |
|---|---|---|---|
| X | -0.615 | +0.486 | 1.10 |
| Y | **-3.724** | **+1.844** | **5.57** |
| Z | -0.455 | +0.234 | 0.69 |

The +1.86 / -3.72 gauss values on Y are LSM303DLHC overflow codes at
the ±1.3 gauss gain. Y baseline (+1.4 gauss at rest, from motor hard-
iron bias) already sat at the +1.3 gauss ceiling; Earth's field swings
took it into saturation in both directions.

### Step 2 — gain raised to ±4.0 gauss

Patched [l3gd20_lsm303d_reader.py](../../../ros2_ws/src/navbot_imu/navbot_imu/l3gd20_lsm303d_reader.py):
`CRB_REG_M 0x20 → 0x80`. Updated sensitivities in config yaml per
datasheet Table 75:
- XY: `1 / (1100 × 10000) = 9.091e-8 T/LSB` → `1 / (450 × 10000) = 2.222e-7 T/LSB`
- Z:  `1 / (980  × 10000) = 1.020e-7 T/LSB` → `1 / (400 × 10000) = 2.500e-7 T/LSB`

### Step 3 — re-sweep with wider range

Second 60 s rotation sweep at ±4.0 gauss gain (clean data, no
saturation):

| Axis | offset (gauss) | half-range (gauss) |
|---|---|---|
| X | -0.047 | 0.56 |
| Y | +1.419 | 0.52 |
| Z | -0.226 | 0.20 |

XY mean radius 0.54 gauss — right in Earth's expected range
(0.3–0.5 gauss). Motor hard-iron bias on Y (+1.42 gauss) now cleanly
isolated as a constant offset.

### Step 4 — offsets applied, mag enabled

Wrote offsets to [l3gd20_lsm303d.yaml](../../../ros2_ws/src/navbot_imu/config/l3gd20_lsm303d.yaml)
as `mag_offset_{x,y,z}_t`. Patched driver to apply these offsets to
the published `/imu/mag` topic (previously only used internally for
YPR calc). Enabled `use_mag: True` in `imu_fusion.launch.py`.

### Step 5 — static rotation test (PASSED)

Baseline yaw captured stationary: `-5.16°`. Robot manually rotated
~90° clockwise by hand. Post-rotation yaw: `-107.84°`. Delta:
`-102.68°` — tracks physical rotation cleanly. Stability at new
heading: 0.07° spread over 3 s.

**Static mag fusion WORKS.**

## Task 2 — wheel_radius realignment

`grep -rn wheel_radius` found a stale value in
[navbot_base.yaml](../../../ros2_ws/src/navbot_base/config/navbot_base.yaml):
still `0.033` while firmware / URDF / everywhere else is `0.0325`
(session 8 fix). The navbot_serial_bridge uses this param for:
- `odometry.py` meters-per-count computation (line 49)
- wheel-velocity → angular-velocity conversion for JointState
  (`serial_bridge.py:365-366`)

Fixed: `0.033 → 0.0325`. Rebuilt `navbot_base`, restarted, verified
via `ros2 param get /navbot_serial_bridge wheel_radius`.

The Pi-side source tree was also observed to be on `dc04ba9` (pre-
session-8), so its copy of `firmware/config.h` still shows `0.033f`.
**The Pico running binary is correct** (flashed from Mac in session 8
via BOOTSEL), but a `git pull` on the Pi would be prudent. Noted
as a backlog item.

## Task 3 — heading drift benchmark

Two test designs run; v2 is the clean one.

### Test v1 — one-way 360° spin

Robot spun CCW at 0.5 rad/s for 13.5 s (nominal 387° command). Sampled
EKF and raw /odom yaw before/after. Error per 360° computed as
shortest-signed-angle delta.

| Trial | EKF err | Raw err |
|---|---|---|
| 1 | +22.74° | +19.96° |
| 2 | +27.40° | +18.94° |
| 3 | +21.12° | +18.51° |
| **mean** | **+23.75° ± 2.66°** | **+19.14° ± 0.61°** |

**Problem with v1:** what we measured isn't drift — it's
`(true rotation mod 360°) − 360°`. With a motor ratio closer to 99%
at this spin rate, the robot rotated ~383° per trial rather than
~329° (as session 7 Phase 0 low-speed characterization suggested).
Without a physical ground-truth reference, pure drift can't be
separated from command-rotation scaling. Test design superseded.

### Test v2 — spin-and-return (cleaner)

Robot spun CCW 13.5 s, settle, CW 13.5 s, settle. End yaw should equal
start yaw regardless of rotation amount. Any deviation is pure drift
plus asymmetric wheel slip.

| Trial | EKF drift | Raw /odom drift |
|---|---|---|
| 1 | +2.99° | -0.59° |
| 2 | -10.36° | -0.33° |
| 3 | +15.82° | -0.15° |
| **\|mean\|** | **9.73°** | **0.36°** |
| **stdev** | **10.69°** | **0.18°** |

Mid-trial CCW measurements were diagnostic:

| | Trial 1 | Trial 2 | Trial 3 |
|---|---|---|---|
| Raw CCW delta | +18.7° | +18.8° | +18.7° |
| EKF CCW delta | +11.7° | +9.3°  | +23.6° |

Encoders reported identical per-trial rotation (spread < 0.1°).
The EKF reported rotation varying by a factor of 2.5× between
trials for the exact same physical motion.

### Interpretation — motor-EM degrades mag during motion

The mid-trial CCW consistency disparity can't come from physical
rotation (identical each time, per encoders). It must come from sensor
fusion noise. The only sensor carrying yaw information into the
complementary filter is the magnetometer. The only time the mag sees
something different each trial is WHEN MOTORS ARE ACTIVE — motor coils
emit transient EM fields that distort the local magnetic reading at
the IMU's axle-height mount.

The complementary filter then applies these distorted readings to
correct gyro integration, yielding noisy and inconsistent yaw
estimates during/immediately-after motion. The effect also shows up
as a +4.67° EKF yaw jump between trial 2 end and trial 3 start (while
the robot was stationary and raw /odom showed 0.00° change) — the
mag field takes a few seconds to recover its stable reading once
motors stop.

This is a well-known issue with magnetometers mounted near BLDC or
brushed DC motors; the axle-height mount (just 35 mm from the motor
stack) is particularly bad for this.

### Decision — revert to use_mag: false

Per raw /odom's 0.36° round-trip drift, the wheel encoders on this
chassis are essentially drift-free under balanced motion — better than
most platforms. Gyro+accel complementary fusion (without mag) gives
stable orientation short-term; any long-term drift is corrected by
SLAM loop closure. Mag fusion actively harms during motion. The
calibration work (±4.0 gauss gain + hard-iron offsets) is kept in the
driver/yaml so `use_mag: true` is a one-line re-enable once the IMU
can be physically relocated further from the motor stack.

## Summary

**Classification:** MIXED
- Mag calibration succeeded: static heading tracks physical rotation
- Mag fusion FAILED during motion: motor EM induced 10° drift per rev
- Reverted use_mag:false; kept calibration infrastructure for future
- wheel_radius alignment shipped cleanly (0.033 → 0.0325)

**Key metrics:**
- Raw encoder-only round-trip drift: **0.36° per 360° spin-and-return**
- EKF with mag fusion during motion: **9.73° per 360° round-trip** (worse)
- Gyro noise at rest: <0.5 dps per axis
- Mag calibrated |vec| at rest: **0.42 gauss** (was 1.43 pre-cal)

**Files changed this session:**
- [navbot_imu/navbot_imu/l3gd20_lsm303d_reader.py](../../../ros2_ws/src/navbot_imu/navbot_imu/l3gd20_lsm303d_reader.py) — CRB 0x20→0x80 (±4.0G), /imu/mag offset subtraction
- [navbot_imu/config/l3gd20_lsm303d.yaml](../../../ros2_ws/src/navbot_imu/config/l3gd20_lsm303d.yaml) — sensitivities for ±4.0G, new hard-iron offsets
- [navbot_imu/launch/imu_fusion.launch.py](../../../ros2_ws/src/navbot_imu/launch/imu_fusion.launch.py) — docstring; `use_mag: False` (reverted from True after benchmark)
- [navbot_base/config/navbot_base.yaml](../../../ros2_ws/src/navbot_base/config/navbot_base.yaml) — wheel_radius 0.033 → 0.0325

**Backlog items opened:**
- Pi-side repo sync (git pull + colcon build) — Pi is at `dc04ba9`, missing session 8-9
- IMU physical relocation to reduce motor-EM exposure — if achievable,
  re-enable mag fusion and re-run the spin-and-return benchmark
- Consider `gain_mag: 0.01 → 0.001` alternative for future sessions
  (mag pulls heading slowly during static periods only)

## Cross-references

- Session 9 IMU integration:
  [2026-04-22-imu-integration.md](2026-04-22-imu-integration.md)
- wheel_radius origin: session 8 firmware fix (commit `afe3bbc`)
- Nav2 EKF consumer: [nav2_params.yaml odom_topic=/odometry/filtered](../../../ros2_ws/src/navbot_navigation/config/nav2_params.yaml)
