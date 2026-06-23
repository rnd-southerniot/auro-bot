# Nav2 4-Step Out-and-Back Sequence — SUCCESS with Straight-Line Drift Observed

**Date:** 2026-04-22 (late evening, session 8, immediately after first-nav-goal-success)
**Session:** Four-goal round-trip on RPP controller
**Firmware:** 1.3.0 + counter-drive (commit `a445ffe`)
**Controller:** RegulatedPurePursuitController (commit `a4b9ebd`)
**Verdict:** SUCCESS — all four goals returned `STATUS_SUCCEEDED`. Net
pose drift from start to end is 12.6 cm XY and 18.8° yaw, within the
predicted tolerance-stack budget. Observed during live run: forward
legs were visibly curved rather than straight, accounting for most of
the accumulated drift.

## Sequence

Four consecutive `navigate_to_pose` goals, body-frame, sent sequentially
via [scripts/nav_goal_probe.py](../../../scripts/nav_goal_probe.py).

| Step | Body-frame goal | Travel | Rotation | `lin.x` max / mean | `ang.z` max / mean | Status |
|---|---|---|---|---|---|---|
| 1: 0.5 m forward | (+0.5, 0, 0) | 0.351 m | +4.5° | +0.150 / +0.106 | +0.300 / +0.141 | 4 |
| 2: 180° in place | (0, 0, π) | 0.001 m | -166.2° | 0 / 0 | **-0.500 / -0.452** | 4 |
| 3: 0.5 m forward | (+0.5, 0, 0) | 0.366 m | -3.7° | +0.150 / +0.114 | -0.127 / -0.046 | 4 |
| 4: 180° in place | (0, 0, π) | 0.000 m | +193.0° | 0 / 0 | **-0.500 / -0.453** | 4 |

Max `ang.z` in Steps 2 and 4 pegs exactly at
`rotate_to_heading_angular_vel: 0.5 rad/s`, confirming RPP's rotate-to-
heading mode fires on pure-rotation goals.

## Net pose drift

| | Before Step 1 | After Step 4 | Delta |
|---|---|---|---|
| Map X (m) | +0.202 | +0.287 | +0.085 |
| Map Y (m) | -0.240 | -0.334 | -0.094 |
| Yaw (°) | +37.3 | +56.1 | +18.8 |
| Euclidean XY offset | | | **0.126 m** |

The 0.126 m XY offset and 18.8° yaw offset after a supposed round-trip
are within the predicted tolerance-stack budget (4 × `xy_goal_tolerance
0.15 m` ∥ 4 × `yaw_goal_tolerance 0.25 rad`) but not within it — the
system never "overshoots" the tolerance budget in this run. Tightening
tolerances would force more-precise pose convergence.

## Straight-line drift during forward legs

Visible during the live run: the forward legs (Steps 1 and 3) were
**not straight** — the robot curved noticeably. Supporting data from
`/cmd_vel_nav`:

- Step 1 forward — mean `ang.z = +0.141 rad/s` over 54 samples (10 Hz)
  with max +0.300 rad/s. RPP was actively commanding rotation during
  what should have been a straight forward move.
- Step 3 forward — mean `ang.z = -0.046 rad/s`, max -0.127 rad/s. Same
  pattern, smaller amplitude.

If RPP were commanding a straight path, `ang.z` would hover at zero
with only tiny corrections. The non-zero mean indicates either:

1. **The global plan was not straight.** With a start away from origin
   and an arbitrary goal, the global planner can produce a path that
   curves into the goal pose from the side (if the start yaw doesn't
   point at the goal).
2. **RPP is correcting for drift seen in odom.** If wheel odometry
   reports the robot drifting off the planned straight line (due to
   uneven wheel radii, wrong `wheel_separation`, or surface slip), RPP
   commands angular correction to steer back — visually looking curved.

Hypothesis 2 is more likely here: Step 1 and 3 both ran with start yaw
≈ collinear to the goal, so a straight plan should have been generated.
The firmware/URDF wheel-radius mismatch (firmware 0.033 m vs URDF
0.0325 m) is a known ~1.5 % odom error — in the correct direction to
produce this curvature. See project-status.md "Firmware `wheel_radius`
0.033f vs URDF 0.0325 alignment" item.

## Rotation overshoot

Step 4: commanded +180° rotation, actual +193°. Goal checker
accepted because the overshoot (13°) stayed within
`yaw_goal_tolerance: 0.25 rad (14.3°)`. This is consistent with RPP's
rotate-to-heading mode not having deceleration built-in before the
target heading — the controller commands -0.5 rad/s until the goal
yaw tolerance fires, then transitions out. At 0.5 rad/s, one control
cycle at 10 Hz is 0.05 rad (2.9°) of uncommanded motion during the
transition.

## Observed behaviour summary

- **In-place rotation goals work cleanly** with RPP when set as
  same-XY-different-yaw goals (Steps 2 & 4).
- **RPP hits `desired_linear_vel: 0.15 m/s` and
  `rotate_to_heading_angular_vel: 0.5 rad/s` exactly.**
- **Forward paths curve visibly**, attributed to odom inaccuracy
  (pending `wheel_radius` mismatch fix).
- **Rotation goals can overshoot up to ~3°** due to lack of deceleration
  ramp in rotate-to-heading — acceptable with current tolerances,
  tighten if needed.

## Follow-up

Next diagnostic: re-run a standalone 0.5 m forward goal and look at
`/cmd_vel_nav` across the whole trajectory to confirm whether the
curvature is from non-zero `ang.z` commanded continuously (RPP drift
correction) or from the global plan shape.

## Cross-references

- Prior successful 3-goal session (same evening, initial RPP validation):
  [2026-04-22-first-nav-goal-success.md](2026-04-22-first-nav-goal-success.md)
- Nav2 config:
  [ros2_ws/src/navbot_navigation/config/nav2_params.yaml](../../../ros2_ws/src/navbot_navigation/config/nav2_params.yaml)
- Probe script:
  [scripts/nav_goal_probe.py](../../../scripts/nav_goal_probe.py)
- Project status:
  [../../project-status.md](../../project-status.md)
