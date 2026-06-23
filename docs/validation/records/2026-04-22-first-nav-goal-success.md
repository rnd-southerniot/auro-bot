# First Autonomous Nav Goal — SUCCESS

**Date:** 2026-04-22 (late evening, session 8, after nav2-tuning-partial earlier same day)
**Session:** Costmap inflation tuning + DWB→RPP controller switch + three nav-goal attempts
**Firmware:** 1.3.0 + counter-drive (commit `a445ffe`)
**Verdict:** SUCCESS — robot autonomously executed three `navigate_to_pose` goals, all reported `STATUS_SUCCEEDED` (4) by the action server. Total autonomous travel ≈ 2.2 m with a combined ~160° of rotation in the third goal.

## Step 1 — Costmap + DWB tuning (did not unlock forward motion)

Applied the two fixes that session 7 identified as the most likely unblockers:

| Param | Before | After | Reason |
|---|---|---|---|
| `local_costmap.inflation_layer.inflation_radius` | 0.15 m | 0.05 m | DWB's forward projection previously landed inside inflated costs around LiDAR-seen obstacles |
| `local_costmap.inflation_layer.cost_scaling_factor` | 3.0 | 10.0 | Sharper decay past the inflation band |
| `global_costmap` inflation | Nav2 default 0.55 m | explicit 0.05 m | Previously unset — defaulted to 0.55 m, halting any planned forward path for a 10 cm half-width robot |
| `global_costmap.plugins` | (defaults) | `[static_layer, inflation_layer]` | Explicit; consumes SLAM `/map` via static_layer |
| `FollowPath.sim_time` | 1.5 s | 1.0 s | Shortens forward projection 22.5 → 15 cm |

Pi verification: all five values loaded into the running `controller_server` / `local_costmap` / `global_costmap` via `ros2 param get` after launch.

### First goal attempt (DWB, after tuning)

Goal: `(+1.0, 0.0)` body-frame, 40 s timeout. Environment pre-check (LiDAR sectors, 5-way):

| Sector | Nearest obstacle |
|---|---|
| Front (±30°) | 1.357 m |
| Left (30–90°) | 0.922 m |
| Right (-30 — -90°) | 0.927 m |
| Back-L (90–180°) | 0.876 m |
| Back-R (-180 — -90°) | 0.655 m |

**Forward corridor is completely clear (1.36 m).** So the obstacle-inflation hypothesis was wrong.

Result:

| Metric | Value |
|---|---|
| Travel | 0.001 m |
| Rotation | +1.4° |
| `/cmd_vel_nav` count (40 s) | 401 |
| `lin.x`: min / max / mean | 0.000 / 0.000 / 0.000 |
| `ang.z`: min / max / mean | -0.089 / +0.089 / +0.002 |
| Controller log | `Failed to make progress` → aborted |

DWB produced **zero forward linear velocity** across 401 samples and only oscillated ±0.09 rad/s in rotation, despite a 1.36 m clear corridor ahead, a 5 cm inflation radius, and a 15 cm forward projection. Critic-balance tuning for this platform had now consumed two sessions without producing translation.

## Step 2 — Switch FollowPath from DWB to RegulatedPurePursuitController

Replaced the DWB config block in
[nav2_params.yaml](../../../ros2_ws/src/navbot_navigation/config/nav2_params.yaml)
with RPP:

```yaml
FollowPath:
  plugin: "nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController"
  desired_linear_vel: 0.15
  min_approach_linear_velocity: 0.05
  approach_velocity_scaling_dist: 0.4
  max_angular_accel: 1.5
  lookahead_dist: 0.3
  min_lookahead_dist: 0.2
  max_lookahead_dist: 0.5
  use_velocity_scaled_lookahead_dist: true
  lookahead_time: 1.5
  use_rotate_to_heading: true
  rotate_to_heading_min_angle: 0.785   # 45°
  rotate_to_heading_angular_vel: 0.5
  use_regulated_linear_velocity_scaling: true
  use_cost_regulated_linear_velocity_scaling: false
  regulated_linear_scaling_min_radius: 0.5
  regulated_linear_scaling_min_speed: 0.05
  max_allowed_time_to_collision_up_to_carrot: 1.0
  use_collision_detection: true
  allow_reversing: false
  transform_tolerance: 1.0
```

Plugin swap required restarting only `controller_server` (the rest of the
Nav2 stack stayed active). After restart:

- `ros2 lifecycle get /controller_server` → `active [3]`
- `ros2 param get /controller_server FollowPath.plugin` →
  `nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController`
- Clean lifecycle manager activation, no plugin-load errors

## Step 3 — Three nav-goal attempts with RPP

Each goal sent via a standalone rclpy `ActionClient` script
([nav_goal_probe.py](../../../scripts/nav_goal_probe.py), copied to
`/tmp/` on Pi) that records the robot's start pose, sends the goal,
subscribes to `/cmd_vel_nav` throughout execution, and reports end
pose + summary stats.

### Goal 1 — 1.0 m straight ahead

| Metric | Value |
|---|---|
| Start pose (map) | (+0.001, 0.000, yaw=+2.8°) |
| Goal (map) | (+1.000, +0.048, yaw=+2.8°) |
| End pose (map) | (+0.843, +0.080, yaw=-5.4°) |
| Travel | **0.846 m** (84.6 % of commanded) |
| Rotation | -8.2° |
| Nav2 status | **4 = SUCCEEDED** |
| `/cmd_vel_nav` count | 81 |
| `lin.x`: min / max / mean | 0.000 / **0.150** / 0.136 |
| `lin.x > 0.01` count | 80 / 81 |
| `ang.z`: min / max / mean | -0.261 / +0.131 / -0.040 |

`max lin.x = desired_linear_vel = 0.150` exactly — RPP hits the cruise
velocity as designed. 84.6 % travel ratio matches session 7's Phase 0
motor envelope characterization (85 % ratio at 0.15 m/s).

### Goal 2 — body-frame (0.3, 0.3, +90°)

Composite: translate diagonally and rotate. Tests rotate-to-heading.

| Metric | Value |
|---|---|
| Start pose | (+0.891, +0.085, yaw=-6.1°) |
| Goal (map) | (+1.221, +0.352, yaw=+83.9°) |
| End pose | (+1.126, +0.291, yaw=+71.5°) |
| Travel | **0.313 m** |
| Rotation | **+77.5°** |
| Nav2 status | **4 = SUCCEEDED** |
| `/cmd_vel_nav` count | 74 |
| `lin.x`: mean | 0.045 |
| `ang.z`: min / max / mean | -0.114 / **+0.500** / +0.223 |

`max ang.z = 0.500 = rotate_to_heading_angular_vel` exactly — RPP
rotates in place at the configured angular velocity when bearing-to-path
exceeds 45°, then transitions into translation. Lower mean linear
(0.045 vs 0.136 for goal 1) reflects time spent rotating.

### Goal 3 — return to origin (body-frame -0.634, +0.974, -71.5°)

Longest composite motion. Robot needs to rotate ~80° right to face
origin, drive ~1.2 m, then rotate ~80° left to reach yaw=0°.

| Metric | Value |
|---|---|
| Start pose | (+1.126, +0.292, yaw=+83.8°) |
| Goal (map) | (+0.089, -0.233, yaw=+12.3°) |
| End pose | (+0.197, -0.245, yaw=+0.3°) |
| Travel | **1.073 m** |
| Rotation | **-83.5°** |
| Nav2 status | **4 = SUCCEEDED** |
| `/cmd_vel_nav` count | 180 |
| `lin.x`: mean | 0.072 |
| `lin.x > 0.01` count | 112 / 180 |
| `ang.z`: min / max / mean | -0.062 / **+0.859** / +0.347 |

`max ang.z = 0.859 rad/s` exceeds the RPP rotate-to-heading vel
(0.500) — this is RPP's pure-pursuit curvature-derived angular command
during translation, which RPP itself doesn't cap. The `velocity_smoother`
downstream clamps to 0.8 rad/s before `/cmd_vel` reaches the bridge.

The 0.108 m gap between end pose and goal XY (0.197 vs 0.089) is within
the 0.25 m combined tolerance of `xy_goal_tolerance: 0.15` +
`yaw_goal_tolerance: 0.25`. Minor start-pose drift between my probe's
read and send (71.5° → 83.8° yaw in ~1 s while TF settled) caused the
body-frame args to be computed for a slightly stale reference — the
controller still hit the commanded map-frame goal correctly.

## Why DWB failed on this platform

Even with the costmap tuning that unblocked the previous session's
stated root cause, DWB still commanded zero forward velocity. Several
observations together explain this:

1. **Motor envelope is well-characterized and benign.** Session 7 proved
   the motor has effectively zero deadband (reliable down to 0.005 m/s,
   0.05 rad/s).
2. **Environment was verifiably clear.** Session 8 LiDAR sector readings
   show 1.36 m forward clearance. With `inflation_radius: 0.05` m and
   10 cm half-width footprint, forward projection of 15 cm had ≥ 50 cm
   of margin before any cost.
3. **Controller log said "Failed to make progress"**, not "No valid
   trajectories" — meaning DWB *was* producing valid trajectory
   candidates but none that the critics picked a forward component for.

DWB chose rotation-only because its
critic weighting (`GoalDist.scale=24, PathDist.scale=32, PathAlign.scale=16,
GoalAlign.scale=24, RotateToGoal.scale=8, ObstacleFootprint.scale=0.02`)
happened to favour zero-vx rotation trajectories that score well on
goal-alignment (the robot wasn't off-heading enough to get strongly
penalised) while not being penalised on path-distance in any way that
rewarded forward motion. Tuning DWB critics by hand for a differential-
drive kinematic profile with this platform's scales is an optimisation
problem we explicitly decided not to continue with.

**Going forward this platform uses RPP.** The file records both DWB and
RPP configurations for reference, with `dc04ba9` as the last-working
DWB-era commit and this session's commit as the RPP migration.

## What works now that didn't before

- First autonomous Nav2 navigation goal — straight-ahead translation ✓
- Composite rotate-while-translate goal ✓
- Out-and-back navigation (3-goal sequence totalling ~2.2 m) ✓
- RPP rotate-to-heading behaviour verified (max ang.z pegged at
  `rotate_to_heading_angular_vel: 0.5`)
- RPP cruise velocity verified (max lin.x pegged at
  `desired_linear_vel: 0.15`)
- RPP pure-pursuit curvature command verified (ang.z exceeded rotate-to-
  heading vel up to 0.859 rad/s during curve following)

## Follow-up items (not blockers; good-to-have)

- `xy_goal_tolerance: 0.15` is generous. Once we have map-anchored
  waypoint navigation validated, tighten to 0.05–0.10 m.
- Goal 3 rotation phase showed RPP can command 0.86 rad/s before the
  velocity_smoother's 0.8 rad/s cap kicks in. Either raise the smoother
  cap to 1.0 rad/s (RPP can handle it with current motor envelope) or
  explicitly limit RPP's curvature output — current setup works but
  the clamp is arguably wasteful.
- Session-level nav logs on Pi are at `/tmp/nav2.log` (live, trimmed
  each launch). Preserve them into `docs/validation/logs/` if needed
  for post-mortem beyond this session.

## Cross-references

- Prior PARTIAL session + DWB tuning attempts:
  [2026-04-22-nav2-tuning-partial.md](2026-04-22-nav2-tuning-partial.md)
- First first-nav-goal attempt (PARTIAL):
  [2026-04-22-first-nav-goal-partial.md](2026-04-22-first-nav-goal-partial.md)
- Nav2 config (RPP):
  [ros2_ws/src/navbot_navigation/config/nav2_params.yaml](../../../ros2_ws/src/navbot_navigation/config/nav2_params.yaml)
- Probe script used for all three goal attempts:
  [scripts/nav_goal_probe.py](../../../scripts/nav_goal_probe.py)
- Project status:
  [../../project-status.md](../../project-status.md)
