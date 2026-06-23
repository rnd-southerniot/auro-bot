# First Navigation Goal — PARTIAL

**Date:** 2026-04-22
**Session:** URDF calibration fix + Pi sync + first autonomous nav goal attempt
**Firmware:** 1.3.0 with counter-drive enabled and STOP-handler fix (commit `a445ffe`)
**Verdict:** PARTIAL — full Nav2 pipeline launched, lifecycle auto-activated cleanly with LiDAR on, SLAM producing map, DWB producing velocity commands end-to-end to base_bridge — but commanded velocity magnitude lands below the motor's static-friction threshold. Robot accepts the goal and the chain works, but doesn't physically move.

## What succeeded

1. **Pi repo sync** — pulled from `8cf3319` to `55badc6`, dropped two stale locally-uncommitted files on `navbot_power` (content already captured in earlier commits). 12 ROS 2 packages rebuilt in 13.5 s, zero warnings.
2. **Base smoke test** — `ros2 launch navbot_bringup base.launch.py` confirms bridge connecting at `firmware 1.3.0`.
3. **Full Nav2 launch** (SLAM + Nav2 as two detached launches):
   - `slam.launch.py` brings up base + LiDAR + slam_toolbox
   - `navbot_navigation/nav2.launch.py` brings up Nav2 stack
   - **All Nav2 nodes auto-activated to `active [3]`** — no manual lifecycle activation needed because LiDAR was ON (unlike the prior rotation-test session which had LiDAR off)
4. **SLAM** — publishes `/map` (96 × 69 cells at 0.05 m/pix → ~4.8 × 3.45 m map), `/tf` includes `map → odom`, robot localized at (0, 0, 0°) in map frame
5. **Raw `/cmd_vel` path** — publishing `linear.x = 0.1` directly to `/cmd_vel` for 2.5 s with `collision_monitor` deactivated moves the robot 125 mm physically (~50 % of nominal due to ramp losses and CD at end). Confirms the cmd_vel → base_bridge → firmware → motors pipeline is functional end-to-end.
6. **Nav2 goal acceptance** — `navigate_to_pose` action accepts the goal. `controller_server` logs `Passing new path to controller` every ~1 s indicating the controller is receiving paths and actively trying to follow.

## The blocker

After sending a `navigate_to_pose` goal to (0.5, 0, 0°), a 15 s parallel capture of the three stages of the cmd_vel pipeline showed:

| Stage | Topic | Rate (15 s) | Content |
|---|---|---|---|
| DWB raw output | `/cmd_vel_nav` | 81 msgs | linear.x = 0.0, angular.z ≈ -0.111 rad/s |
| After velocity_smoother | `/cmd_vel_smoothed` | 168 msgs | linear.x = 0.0, angular.z ≈ -0.075 rad/s |
| After collision_monitor | `/cmd_vel` | 84 msgs | linear.x = 0.0, angular.z ≈ -0.075 rad/s |

**The commanded velocity lands at 0.075 rad/s angular.** For our diff-drive geometry:

- Per-wheel tangential speed: 0.075 × 0.090 m ≈ **6.75 mm/s**
- Previous successful rotation tests were at 45 mm/s tangential (0.5 rad/s × 0.090 m) — **6.7× faster**

At 6.75 mm/s the wheels cannot overcome static friction. The PID commands a duty cycle that produces no measurable motion. Robot sits commanded but motionless for the entire 20 s action window before it times out.

## Why DWB is outputting rotation-only

With the robot at (0.141, 0.001, 0°) and goal at (0.5, 0, 0°), the bearing to goal is essentially along the x-axis — no significant rotation required. DWB's `RotateToGoal` critic combined with the trajectory-sampling grid appears to score a slow-rotation trajectory highest. This is a **controller-tuning artifact**, not a design-level issue:

- `min_speed_theta = 0.10 rad/s` — above the motor's static-friction threshold at wheel level
- After velocity_smoother's deadband and ramp-up from zero, effective commands are below the 0.10 threshold DWB itself intended
- The DWB critic weights (RotateToGoal.scale: 8.0; GoalDist.scale: 24.0) may under-incentivize forward motion relative to heading correction

## Interactions with collision_monitor

During diagnosis we toggled `collision_monitor` on and off:

- **Active** (lifecycle `active [3]`): expected Nav2 config; passes `/cmd_vel_smoothed` through to `/cmd_vel`
- **Inactive** (`inactive [2]`): the `/cmd_vel_smoothed` → `/cmd_vel` bridge disappears → Nav2's commands never reach base_bridge. Raw manual publishes to `/cmd_vel` still work (nothing else is publishing zero to override).

For a working Nav2 chain with this robot's software stack, `collision_monitor` must be active. When LiDAR is **off** (as in the rotation test on 2026-04-21), `collision_monitor` must be deactivated or bypassed because its footprint check has no scan data to clear.

## Action items for the next session

Ordered by impact on the first-nav-goal goal:

1. **Tune DWB (or switch to RPP) for our motor envelope.** Either:
   - Raise DWB's `min_speed_theta`, `min_vel_x`, and maybe velocity_smoother's deadband so DWB never commands sub-friction velocities
   - Reduce velocity_smoother's smoothing (effectively passing DWB's full output through)
   - Switch to `nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController` which is simpler and more predictable for differential-drive platforms. RPP has explicit `min_approach_linear_velocity` and `min_lookahead_dist` tunables that map naturally to "don't command anything below X m/s".
2. **Verify firmware's minimum-reliable-velocity experimentally.** Run a stepped `CMD_VEL` test via serial: 0.005, 0.010, 0.015, ..., 0.05 m/s linear. Find the threshold below which wheels don't move reliably. That number bounds how slow DWB is allowed to command.
3. **Consider a one-off relay node.** If the velocity_smoother deadband is too aggressive, a simple `cmd_vel_smoothed → cmd_vel` relay sidesteps collision_monitor — but loses its safety. Only as a diagnostic, not production.

## Related findings flagged during this session

- `/docking_server` appears in Nav2's node list even when we don't configure docking. Harmless but noisy.
- Two `/robot_state_publisher` instances briefly appeared in early diagnostic — self-resolved after an aggressive `pkill` and clean launch. Likely residue from an incomplete prior launch.
- `slam_toolbox` `transform_publish_period = 0.05 s` (20 Hz) by default in our config — confirmed adequate for TF timing at this robot's speeds.

## Cross-references

- URDF `wheel_offset_y` fix — commit `55badc6`, backlog item empirically justified by
  [2026-04-22-rotation-test.md](2026-04-22-rotation-test.md)
- Nav2 config — [ros2_ws/src/navbot_navigation/config/nav2_params.yaml](../../../ros2_ws/src/navbot_navigation/config/nav2_params.yaml)
- Nav2 launch — [ros2_ws/src/navbot_navigation/launch/nav2.launch.py](../../../ros2_ws/src/navbot_navigation/launch/nav2.launch.py)
- Project status — [../../project-status.md](../../project-status.md)
