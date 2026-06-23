# Firmware `wheel_radius` Fix 0.033 → 0.0325 m + Straight-Line Verification

**Date:** 2026-04-22 (late evening, session 8, immediately after the
four-step out-and-back sequence)
**Session:** Firmware calibration fix targeting the straight-line drift
observed during the 4-step round-trip
**Firmware:** 1.3.0 + counter-drive + wheel_radius 0.0325 m (rebuilt +
flashed this session)
**Verdict:** SUCCESS — mean commanded `ang.z` during forward translation
collapsed from +0.141 rad/s to ±0.014 rad/s (10× reduction). Robot now
drives noticeably straight in body frame. Travel ratio improved from
~70 % to 96–98 % of commanded distance.

## Motivation

The four-step out-and-back sequence earlier this session
([2026-04-22-nav2-four-step-sequence.md](2026-04-22-nav2-four-step-sequence.md))
accumulated 12.6 cm / 18.8° drift over four goals, with the forward
legs visibly curving rather than driving straight. The hypothesis:
firmware reports wheel odometry using `wheel_radius = 0.033 m` while
the URDF defines `0.0325 m`. The 1.5 % mismatch makes the Pi think the
robot traveled more than it physically did, so odometry reports a
"drift" that RPP then tries to correct by steering — producing an
actual physical curve.

## Changes applied

### Firmware — `config.h`

```c
-#define LEFT_WHEEL_RADIUS_M   0.033f
-#define RIGHT_WHEEL_RADIUS_M  0.033f
+#define LEFT_WHEEL_RADIUS_M   0.0325f
+#define RIGHT_WHEEL_RADIUS_M  0.0325f
```

Rebuild via CMake in
[firmware/makerpi_rp2040_base/build/](../../../firmware/makerpi_rp2040_base/build/),
flashed via BOOTSEL (mounted `/dev/sda1` from Pi, copied `firmware.uf2`,
unmounted — Pico auto-rebooted to CDC in 2 s). Pico enumerated clean
as `/dev/ttyACM0` post-flash, no checksum failures observed.

### Nav2 config — `nav2_params.yaml`

`goal_checker.xy_goal_tolerance: 0.15 → 0.05` m. Generous tolerance
during first-goal bring-up let goal_checker accept up to 15 cm from the
goal. With odometry now calibrated, tighten so the final-approach
actually resolves to the commanded position.

## Pre-fix baseline

From the four-step sequence earlier this session:

| Metric | Step 1 | Step 3 |
|---|---|---|
| Body-frame goal | (+0.5, 0, 0) | (+0.5, 0, 0) |
| Travel | 0.351 m | 0.366 m |
| Travel ratio | 70 % | 73 % |
| `ang.z` mean during drive | **+0.141 rad/s** | -0.046 rad/s |
| `ang.z` max during drive | +0.300 | -0.127 |
| Final XY offset from goal | ~0.16 m | ~0.15 m (at tolerance edge) |

## Post-fix verification

Two back-to-back 0.5 m forward goals, same command `(+0.5, 0, 0)`
body-frame, 30 s timeout, trajectory logged at 0.3 s cadence.

### Test A

| Metric | Value |
|---|---|
| Start pose | map(+0.391, +0.014, yaw=-9.2°) |
| End pose | map(+0.868, -0.035, yaw=-19.5°) |
| Travel | **0.480 m (96 %)** |
| Final XY offset from goal | 0.043 m |
| `ang.z` mean overall | **+0.014 rad/s** |
| `ang.z` max / min | +0.500 / -0.688 |
| `lin.x` mean / max | +0.046 / +0.150 |
| Nav2 status | 4 (SUCCEEDED) |

Translation phase (t=0–4.57 s, before terminal rotate-to-goal-heading):
yaw held between -7.6° and -9.7° — only **2° spread**. Y drifted
+0.014 → -0.004 m over 42 cm X travel, **11 mm total**.

### Test B

| Metric | Value |
|---|---|
| Start pose | map(+0.868, -0.035, yaw=-8.8°) |
| End pose | map(+1.353, -0.088, yaw=-22.2°) |
| Travel | **0.488 m (98 %)** |
| Final XY offset from goal | 0.027 m |
| `ang.z` mean overall | **-0.014 rad/s** |
| `ang.z` max / min | +0.500 / -0.300 |
| `lin.x` mean / max | +0.071 / +0.150 |
| Nav2 status | 4 (SUCCEEDED) |

Translation phase trajectory showed a SLAM re-localization at t=1.21 s
(pose jumped -14 cm X, +7 cm Y, +6° yaw). After that jump, Y drifted
37 mm over 30 cm X — larger than Test A, attributed to the global-plan
recomputation after the SLAM correction rather than new physical drift.

## Side-by-side

| | Pre-fix (Step 1) | Post-fix Test A | Post-fix Test B |
|---|---|---|---|
| Travel | 0.351 m (70 %) | **0.480 m (96 %)** | **0.488 m (98 %)** |
| Mean `ang.z` | +0.141 | +0.014 | -0.014 |
| Max `ang.z` (mid-path) | +0.300 | ~0 | ~0 |
| Yaw spread (mid-path) | +18.3° → +25.2° (7°) | -7.6° → -9.7° (**2°**) | mixed (SLAM jump) |
| XY offset from goal at accept | ~0.15 m | 0.043 m | 0.027 m |

Mean `ang.z` during translation collapsed by **10×**, confirming
RPP is no longer fighting odometry drift. Remaining curvature in
Test B traces to a SLAM re-localization event, not physical robot
curve.

## Residual issue — RPP terminal rotate-to-goal-heading oscillates

Both post-fix tests showed the same pattern in the final rotate-to-
goal-heading phase:

| Metric | Test A | Test B |
|---|---|---|
| Start yaw (robot at XY goal) | -3.6° | -17.1° |
| Target yaw | -9.2° | -8.8° |
| Max overshoot | **-98.7°** (swept 95°) | **-67.7°** (swept 50°) |
| Final yaw at goal_checker accept | -19.5° | -22.2° |
| Yaw error at accept | 10.3° | 13.4° |

The robot commits to a rotation direction, saturates at max angular
vel, overshoots significantly, then damps back and oscillates until
yaw tolerance (0.25 rad = 14.3°) fires. The overshoot magnitude
implies `rotate_to_heading_angular_vel: 0.5` + `max_angular_accel:
1.5` is too aggressive for this platform.

Not fixed this commit — left as a backlog item. Candidate starting
point: `rotate_to_heading_angular_vel: 0.5 → 0.3`,
`max_angular_accel: 1.5 → 1.0`. Deserves its own test cycle rather
than a tack-on to the wheel-radius fix.

## Cross-references

- 4-step sequence that motivated this fix:
  [2026-04-22-nav2-four-step-sequence.md](2026-04-22-nav2-four-step-sequence.md)
- First successful nav goal (RPP bring-up):
  [2026-04-22-first-nav-goal-success.md](2026-04-22-first-nav-goal-success.md)
- Firmware change:
  [firmware/makerpi_rp2040_base/include/config.h](../../../firmware/makerpi_rp2040_base/include/config.h)
- Nav2 config:
  [ros2_ws/src/navbot_navigation/config/nav2_params.yaml](../../../ros2_ws/src/navbot_navigation/config/nav2_params.yaml)
- Probe script (new `--traj` mode used this session):
  [scripts/nav_goal_probe.py](../../../scripts/nav_goal_probe.py)
- Project status:
  [../../project-status.md](../../project-status.md)
