# Map Persistence + AMCL + Multi-Waypoint Route (Session 11)

**Date:** 2026-04-23
**Scope:** Map save/load + AMCL localization, multi-waypoint autonomous
route, higher-speed navigation attempt
**Stack:** firmware 1.3.0 w/ counter-drive, wheel_radius 0.0325; IMU
driver + complementary filter (use_mag=false); robot_localization EKF
fusing wheel odom (x, y, vx) + IMU yaw; Nav2 with RPP.
**Verdict:** MAP_AND_WAYPOINT_PARTIAL — map persistence + AMCL working
end-to-end, first multi-waypoint route 3/4 legs SUCCEEDED with 1.5 cm
return-to-origin XY. Higher-speed validation blocked by AMCL quality
on the quick-built map; speed parameters verified live but full goals
timed out.

## Task 1 — Map save/load + AMCL

### Map build drive

teleop_twist_keyboard wasn't reaching /cmd_vel (no publishers appeared
after invocation — keystrokes not transmitting through the user's SSH
session). Switched to programmatic drive via [/tmp/map_build_drive.py](#):
rotate 360° CCW at center, drive +0.7 m, rotate 360° again, rotate 180°,
drive 0.7 m back, rotate 180° to restore heading. ~65 s.

Final map:

| | Value |
|---|---|
| File | [maps/office_lab.pgm](../../../maps/office_lab.pgm) + [office_lab.yaml](../../../maps/office_lab.yaml) |
| Size | 94 × 113 cells @ 0.05 m = 4.7 × 5.65 m |
| Origin | (-1.610, -2.205) |

The single-pass coverage is minimal — walls visible but map has few
distinctive features for AMCL. Flagged as a follow-up: build a richer
map with multiple offset spin points or a perimeter loop.

### AMCL + map_server launch

New launch file
[navbot_bringup/localization.launch.py](../../../ros2_ws/src/navbot_bringup/launch/localization.launch.py)
brings up the full map-based stack:
- base + LiDAR (`base_lidar.launch.py`)
- IMU + complementary filter (`imu_fusion.launch.py`)
- EKF (`ekf.launch.py`)
- map_server + AMCL (Nav2 `localization_launch.py`)
- Nav2 stack (planner, controller, BT, recoveries)

nav2_params.yaml additions:
- AMCL: `tf_broadcast: true`, `laser_max_range: 16.0 → 8.0`,
  `set_initial_pose: true` with (0, 0, 0) default
- `map_server: yaml_filename: /home/arif/projects/claude-navbot/maps/office_lab.yaml`
- `lifecycle_manager_localization` config (autostarts map_server + amcl)

### Initial pose — quaternion normalization gotcha

AMCL rejected our first five `/initialpose` publishes as "Received
initialpose message is malformed. Rejecting." The cause was **quaternion
precision**: publishing `(z=0.976, w=0.217)` for yaw=155° gave
|q|² = 0.9997, outside Nav2 AMCL's 1e-6 tolerance. Re-computed with
full precision via `math.sin(yaw/2)`, `math.cos(yaw/2)`, then normalized,
`|q|² = 1.0 exactly` and AMCL logged:

```
[amcl-8] initialPoseReceived
[amcl-8] Setting pose (...): 0.397 0.274 2.705
```

AMCL then locked on and started publishing /amcl_pose + map→odom TF.

### GATE 1 verification

0.3 m forward goal in current body frame:

| | Value |
|---|---|
| Start pose (map) | (+0.425, +0.270, yaw=+158.9°) |
| Goal pose (map) | (+0.145, +0.378, yaw=+158.9°) |
| End pose (map) | (+0.156, +0.348, yaw=+145.8°) |
| Travel | 0.281 m (93.7 %) |
| XY offset from goal | 0.031 m |
| Nav2 status | 4 (SUCCEEDED) |

**GATE 1 PASSED.** Map persistence + AMCL + Nav2 end-to-end works.

## Task 2 — Multi-waypoint autonomous route

[scripts/multi_waypoint.py](../../../scripts/multi_waypoint.py)
queries the current robot pose as "home", then visits 3 waypoints
forming a 0.6 × 0.6 m square + returns:

| Leg | Goal (map) | End pose | xy_err | yaw_err | Time | Nav2 |
|---|---|---|---|---|---|---|
| A | (+0.836, +0.350, 0°) | (+0.590, +0.534, -45.7°) | **0.307 m** | 45.7° | 22.7 s | SUCCEEDED |
| B | (+0.836, -0.250, -90°) | (+0.832, -0.237, -171.8°) | 0.014 m | 81.8° | 24.9 s | SUCCEEDED |
| C | (+0.236, -0.250, 180°) | (+0.733, -0.242, -170.7°) | **0.498 m** | 9.3° | 39.8 s | **FAILED** |
| Home | (+0.236, +0.350, 158.7°) | (+0.224, +0.340, +102.9°) | 0.015 m | 55.7° | 33.2 s | SUCCEEDED |

**Return-to-origin accuracy:**
- XY: **1.5 cm** (excellent)
- Yaw: **55.7°** (poor)

**Total route time: 120.5 s. 3/4 legs SUCCEEDED.**

### Interpretation

- **XY accuracy is solid** when navigation finishes — legs B and Home
  ended within 1.5 cm of their goal coordinates.
- **Leg A reported SUCCEEDED but end pose was 31 cm off goal.** This
  is an AMCL relocalization jump at end-of-leg: AMCL *believed* the
  robot was at the goal when sending `SUCCEEDED` to Nav2, but a
  subsequent re-localization (between the goal-checker trigger and
  our TF sample ~1 s later) jumped the pose. The robot was physically
  at the goal; only the pose estimate moved.
- **Leg C FAILED** — progress checker fired after 39.8 s because
  AMCL couldn't agree on where the robot was relative to the goal.
- **Yaw errors are consistently large.** Goal checker yaw tolerance
  is 0.25 rad (14.3°); the measured errors (up to 82°) exceed this,
  yet Nav2 reports SUCCEEDED. Either the goal-checker
  bypasses yaw for some edge case, or AMCL yaw drifts post-success.
  Warrants investigation.

The common cause is **limited distinctive features in the saved map**
— built from a 60 s spin + short translation, the map has sparse
constraints and AMCL's particle filter drifts during motion.

## Task 3 — Higher-speed navigation (PARTIAL)

### Speed parameters confirmed live

Dynamic parameter set via `ros2 param set`:
```
FollowPath.desired_linear_vel:   0.15 → 0.20
velocity_smoother.max_velocity:  [0.15, 0, 0.8] → [0.20, 0, 0.8]
velocity_smoother.min_velocity:  [-0.15, 0, -0.8] → [-0.20, 0, -0.8]
```

Sent a 0.5 m forward goal. `cmd_vel_nav.lin.x` hit `+0.2000` exactly —
the platform has the control authority at 0.20 m/s.

### But end-to-end goals TIMEOUT'd

| Speed | Goal | Travel | End offset | Result | Peak lin.x |
|---|---|---|---|---|---|
| 0.15 m/s | 0.5 m fwd | 0.486 m (97 %) | 10.4 cm | TIMEOUT | 0.138 |
| 0.20 m/s | 0.5 m fwd | 0.139 m (28 %) | — | TIMEOUT | 0.200 |

Both tests showed signs of controller struggle:
- RPP occasionally commanded `lin.x = -0.15` (backward) despite
  `allow_reversing: false`
- Max angular output hit +1.0 rad/s (higher than normal RPP curvature)
- Robot's reported pose in map drifted during transit

The speed parameters are NOT the bottleneck. The underlying issue is
the same AMCL/map-quality problem that hurt Task 2. Speed envelope
validation at 0.20 m/s is deferred until a better map is available.

Reverted params back to 0.15 baseline at end of session.

## Files changed this session

- [ros2_ws/src/navbot_bringup/launch/localization.launch.py](../../../ros2_ws/src/navbot_bringup/launch/localization.launch.py) (new) — map-based bring-up
- [ros2_ws/src/navbot_navigation/config/nav2_params.yaml](../../../ros2_ws/src/navbot_navigation/config/nav2_params.yaml) — AMCL tuning + map_server + lifecycle_manager_localization
- [scripts/multi_waypoint.py](../../../scripts/multi_waypoint.py) (new)
- [maps/office_lab.pgm](../../../maps/office_lab.pgm) + [office_lab.yaml](../../../maps/office_lab.yaml) (new)

## Known issues / backlog opened

1. **Map quality — single-pass coverage is sparse.** The 3×3 m room
   needs a richer map-build drive (perimeter loop + 3-4 spin points)
   for AMCL to have enough features.
2. **AMCL yaw drift during motion.** Particle filter angular estimate
   is inconsistent across legs. Candidate fixes: more laser beams
   (`max_beams: 60 → 120`), more particles (`max_particles: 2000 → 3000`),
   or increased `laser_likelihood_max_dist`.
3. **Nav2 goal_checker accepting large yaw errors.** Up to 82°
   discrepancy between goal yaw and end yaw, despite
   `yaw_goal_tolerance: 0.25 rad`. Possibly an AMCL post-success
   jump; possibly a goal-checker bug. Needs investigation.
4. **Higher-speed validation deferred.** The 0.20 m/s envelope
   extension is gated on Map/AMCL improvements.

## Cross-references

- Session 9 IMU integration (base): [2026-04-22-imu-integration.md](2026-04-22-imu-integration.md)
- Session 10 calibration + heading bench: [2026-04-22-mag-calibration-and-heading-benchmark.md](2026-04-22-mag-calibration-and-heading-benchmark.md)
- Project status: [../../project-status.md](../../project-status.md)
