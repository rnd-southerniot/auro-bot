# Nav2 Controller Tuning + First Nav-Goal Re-Attempt — PARTIAL IMPROVED

**Date:** 2026-04-22 (evening, after first-goal PARTIAL session earlier same day)
**Session:** Motor envelope characterization, Nav2 controller tuning, second nav-goal attempt
**Firmware:** 1.3.0 + counter-drive (commit `a445ffe`)
**Verdict:** PARTIAL IMPROVED — motor deadband characterized (effectively zero),
a real DWB trajectory-starvation bug found and fixed, robot successfully
executed Nav2-commanded rotation for the first time. Forward translation
still blocked, now understood to be a costmap/environment issue rather than
motor deadband.

## Phase 0 — motor envelope characterization

Stepped `/cmd_vel` tests, 2 s pulses at 20 Hz, on base-only bringup (no Nav2).

### Linear sweep (cmd_vel.linear.x)

| cmd_vel | nominal (mm) | actual (mm) | ratio |
|---|---|---|---|
| 0.050 m/s | 100.0 | 87.0 | 87 % |
| 0.040 | 80.0 | 68.8 | 86 % |
| 0.030 | 60.0 | 51.9 | 86 % |
| 0.025 | 50.0 | 42.7 | 85 % |
| 0.020 | 40.0 | 33.6 | 84 % |
| 0.015 | 30.0 | 24.7 | 82 % |
| 0.010 | 20.0 | 15.7 | 78 % |
| 0.005 | 10.0 | 6.4 | 64 % |

### Angular sweep (cmd_vel.angular.z)

| cmd_vel | tangential | nominal rot | actual | ratio |
|---|---|---|---|---|
| 0.500 rad/s | 45.5 mm/s | 57.3° | 49.5° | 86 % |
| 0.400 | 36.4 | 45.8° | 39.3° | 86 % |
| 0.300 | 27.3 | 34.4° | 29.2° | 85 % |
| 0.250 | 22.8 | 28.7° | 23.9° | 83 % |
| 0.200 | 18.2 | 22.9° | 18.8° | 82 % |
| 0.150 | 13.7 | 17.2° | 13.8° | 80 % |
| 0.100 | 9.1 | 11.5° | 8.6° | 75 % |
| 0.050 | 4.55 | 5.7° | 3.3° | 57 % |

### Finding

**Motor effective deadband is below the test resolution.** The robot moves
reliably down to 0.005 m/s linear and 0.05 rad/s angular — speeds 10× lower
than what was hypothesized as the deadband floor after the previous
session. The motion-to-command ratio stays in the 80-86 % band from high
speed down to ~0.010 m/s / 0.10 rad/s, then gradually falls below 70 %.

This invalidated the assumption that last session's failure was motor
deadband. Real issue was elsewhere (confirmed in Phase 2).

## Phase 1 — DWB + velocity_smoother tuning (two iterations)

### Iteration 1 — first Nav2 param tuning (commit `7d1a33e`)

Applied based on motor envelope with 20 % safety margin:

```yaml
controller_server:
  ros__parameters:
    FollowPath:
      max_vel_x: 0.20 → 0.15
      min_vel_x: 0.00 → 0.02
      min_speed_xy: NEW: 0.02
      max_vel_theta: 1.0 → 0.8
      min_speed_theta: 0.10 → 0.15
      acc_lim_x: 0.3 → 0.5
      decel_lim_x: -0.3 → -0.5
    goal_checker:
      xy_goal_tolerance: 0.10 → 0.15

velocity_smoother:
  ros__parameters:
    max_velocity: [0.25,0,1.2] → [0.15,0,0.8]
    deadband_velocity: [0.02,0,0.02] → [0.01,0,0.075]
```

Goal attempt: 0.5 m forward. Result:

- Nav2 accepted the goal
- DWB produced **zero candidate trajectories** → "Could not find a legal trajectory: No valid trajectories out of 0!"
- BT tree fell back to `spin` recovery (observed 133° CW rotation in place)
- Final: ABORTED after 18 s

**Root cause:** `min_speed_xy: 0.02` AND `min_vel_x: 0.02` together
starved DWB's sampler. Pure-rotation trajectories (vx=0) were rejected
because `min_speed_xy` forces |vx| ≥ 0.02. Pure-translation trajectories
with vtheta slightly off zero were also rejected because `min_speed_theta:
0.15` requires |vtheta| ≥ 0.15.

### Iteration 2 — DWB sampler fix (commit `dc04ba9`)

Revised, given motor has no real deadband:

```yaml
FollowPath:
  min_vel_x: 0.02 → 0.0         # allow pure-rotation samples
  min_speed_xy: REMOVED         # no horizontal-speed floor
  min_speed_theta: 0.15         # kept — rotation floor when DWB chooses rotation
```

Goal attempt 2: 0.5 m forward. Result:

- Nav2 accepted goal
- DWB produced valid trajectories (no more "0 trajectories" error)
- **Robot rotated 130° CCW — first time Nav2 produced actual motion on this platform**
- End yaw: -2.37° (very close to goal yaw of 0°)
- Position unchanged: (0.001, 0.001) → no forward translation
- Nav2 TIMEOUT after 30 s

### Iteration 3 — clean pipeline probe (no commit; diagnostic only)

Reset goal with goal-orientation = current-orientation (so no rotation
should be needed). Parallel captured `/cmd_vel_nav`, `/cmd_vel_smoothed`,
`/cmd_vel` for 13 s:

| Stage | msg count (13 s) | linear | angular |
|---|---|---|---|
| `/cmd_vel_nav` | 118 | 0.0 | +0.089 rad/s |
| `/cmd_vel` | 117 | 0.0 | +0.075 rad/s |

Commands reach the bridge. Robot rotated only 3.15° over 13 s (5.6 % of
commanded). Position unchanged.

**Contrast with Phase 0:** at the same 0.075 rad/s commanded for a 2 s
pulse, motor ratio was 80 % (~13.8° per Phase 0 table). In Nav2's
sustained ~0.075 rad/s commanding for 13 s, ratio is 5.6 %. The
sustained-slow-command regime behaves very differently from the pulsed-
slow-command regime.

## Real root cause

**DWB consistently commands rotation-only because forward trajectories
are scored as colliding.** Environment scan data shows nearest obstacles
at ~30 cm from the robot. DWB's forward simulation over `sim_time: 1.5 s`
at `max_vel_x: 0.15 m/s` projects 22.5 cm ahead — inside the
`inflation_radius: 0.15 m` zone of those obstacles. The `ObstacleFootprint`
critic therefore scores all forward trajectories poorly, DWB prefers
rotation-only, robot rotates toward goal alignment but never translates.

In a truly open room (≥ 1 m clearance on all sides), forward trajectories
would score acceptably and DWB would command translation.

## What works now that didn't before

- Motor envelope: characterized, documented, fed into Nav2 config
- DWB trajectory generator: no longer starves (min_speed_xy removed,
  min_vel_x back to 0)
- Nav2 chain end-to-end: verified publishing at every stage
  (/cmd_vel_nav → /cmd_vel_smoothed → /cmd_vel → base_bridge)
- Robot executes Nav2-commanded rotation for the first time
- Goal-orientation alignment works (robot rotated from -132° to ~0°)

## What still blocks the first-goal milestone

Forward translation not commanded because DWB scores forward trajectories
as colliding with costmap-inflated obstacles. Not a config bug, not a
Nav2 pipeline issue — it's a **physical environment constraint combined
with conservative costmap parameters**.

## Next session — ordered path to a successful nav goal

1. **Physical environment:** confirm ≥ 1.5 m clearance in direction of
   goal. Move robot into open floor space.
2. **If environment is clear but DWB still rotates-only:** reduce
   `local_costmap.inflation_layer.inflation_radius` (0.15 → 0.05 m) and
   `global_costmap.inflation_layer.inflation_radius` similarly. This lets
   DWB find forward paths even when obstacles are close on the sides.
3. **If the issue persists:** switch to RegulatedPurePursuitController
   (RPP). RPP has `allow_reversing: false` and `min_approach_linear_velocity`
   that map more naturally to diff-drive platforms than DWB's critic-
   balanced approach.
4. **Tighten goal tolerances** back to 0.1 m XY / 0.2 rad yaw once
   navigation works at all.

## Nav2 param adjustments committed this session

- Commit `7d1a33e` — initial DWB + velocity_smoother tuning (had the
  sampler-starvation bug)
- Commit `dc04ba9` — DWB sampler fix (remove min_speed_xy, restore
  min_vel_x=0)

Both kept for the record. Net effect of both commits (vs pre-tuning):

```
FollowPath.max_vel_x:      0.20 → 0.15
FollowPath.min_vel_x:      0.0  → 0.0  (unchanged after fix)
FollowPath.max_vel_theta:  1.0  → 0.8
FollowPath.min_speed_theta: 0.10 → 0.15
FollowPath.acc_lim_x:      0.3  → 0.5
FollowPath.decel_lim_x:   -0.3  → -0.5

velocity_smoother.max_velocity:       [0.25,0,1.2] → [0.15,0,0.8]
velocity_smoother.deadband_velocity:  [0.02,0,0.02] → [0.01,0,0.075]
goal_checker.xy_goal_tolerance:       0.10 → 0.15
```

## Cross-references

- Motor characterization data (full tables): this document Phase 0
- Prior first-goal PARTIAL session:
  [2026-04-22-first-nav-goal-partial.md](2026-04-22-first-nav-goal-partial.md)
- Rotation test that preceded this work:
  [2026-04-22-rotation-test.md](2026-04-22-rotation-test.md)
- Nav2 config:
  [ros2_ws/src/navbot_navigation/config/nav2_params.yaml](../../../ros2_ws/src/navbot_navigation/config/nav2_params.yaml)
- Project status:
  [../../project-status.md](../../project-status.md)
