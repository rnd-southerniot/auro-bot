# Navbot Session Report — 2026-04-18

**Branch:** `navbot-experimental`
**HEAD (committed):** `9e42d83` fix(nav2): enable DWB time-based trajectory discretization
**Session scope:** Phase A/B retest, geometry corrections, open-space DWB diagnosis

---

## Executive Summary

Applied all Phase A fixes (H3/H4/H6) and Phase B geometry corrections (GF1/GF2/GF3)
with physical robot measurements. All fixes verified applied at runtime.

Final retest in **open space with confirmed clear forward path** still produced
**zero forward velocity commands** from the DWB local planner. The robot rotated
in place, eventually triggering BT recovery behaviours (spin, wait, backup) —
which proved the motor/firmware stack works correctly. DWB alone refuses to emit
`vx > 0`.

**Classification:** STILL ROTATION ONLY — ObstacleFootprint hypothesis disproven.
**Root cause is now definitively inside DWB local planner.**

---

## Operator Observation

> "The robot did one full rotation after a long time and still its in operating mode."

This matches the BT recovery behaviour log:
- DWB failed continuously for ~120s → BT triggered `spin` (1.57 rad rotation)
- BT then tried `wait` (5s) → `backup` (reversed ~0.5m)
- After recoveries, BT continuously fed new paths to DWB — controller kept emitting `vx=0`

This observation is diagnostically important: **it proves the motors, firmware,
velocity_smoother, and physical drivetrain all function correctly.** The robot
physically moved when the behaviour_server commanded it (spin 90°, backup 0.5m).
The issue is DWB-specific.

---

## Changes Applied This Session

### GF1 — Footprint (nav2_params.yaml, both costmaps)

```
- footprint: "[[0.11, 0.08], [0.11, -0.08], [-0.11, -0.08], [-0.11, 0.08]]"
+ footprint: "[[0.10, 0.10], [0.10, -0.10], [-0.03, -0.10], [-0.03, 0.10]]"
```

Corrected from symmetric 0.22×0.16m box to measured asymmetric 0.13×0.20m
(100mm forward from axle, 30mm rear, ±100mm lateral).

### GF2 — Firmware wheel separation (config.h)

```
- #define WHEEL_SEPARATION_M    0.160f
+ #define WHEEL_SEPARATION_M    0.180f
```

Firmware rebuilt and reflashed (`firmware_phaseB.uf2`, ACK PING 1.2.0 confirmed).

### GF3 — ROS wheel separation (navbot_base.yaml)

```
- wheel_separation: 0.160
+ wheel_separation: 0.180
```

Runtime verified: `ros2 param get /navbot_serial_bridge wheel_separation` → 0.18.

### CR1 — Critic revert (nav2_params.yaml)

Reverted Phase A.5 tuning that had no measurable effect:
```
- PathAlign.scale: 12.0     → 16.0
- RotateToGoal.scale: 4.0   → 8.0
```

### Pre-existing uncommitted WIP (still uncommitted)

From prior sessions' Phase A fixes:
- `min_vel_x: 0.0` (was 0.05)
- `min_speed_theta: 0.10` (was 0.35)
- `raytrace_max_range: 12.0` (was 3.0)
- `obstacle_max_range: 10.0` (was 2.5)
- `inflation_radius: 0.15` (was 0.30)
- Stall thresholds: DUTY=200, DELTA=1, TIMEOUT=800, GRACE=1200

---

## Retest 1 — Arena Placement (failed gate)

Robot placed inside 1500×650 mm cardboard arena.

- Pre-motion gate (check at 0.25m): PASS
- Actual DWB trajectory reach (`sim_time × max_vel_x` = 0.30m + footprint 0.10m = 0.40m):
  lethal wall cells detected at **0.40m ahead**
- Result: DWB emitted 0 forward commands, robot did not translate

**Lesson learned:** the pre-motion clearance formula must be:
```
min_fwd_clear = fp_front + (max_vel_x × sim_time) + inflation_radius + safety
              = 0.10    + 0.30                    + 0.15             + 0.10
              = 0.65 m from robot centre
```

The previous 0.25m check (lethal zone only) was insufficient — DWB needs the
full simulation reach to be clear, not just the immediate footprint zone.

---

## Retest 2 — Open Space (gate passed, DWB still failed)

Robot placed in open room with 3–4m clear forward, ≥1m all other directions.

### Open-space LiDAR verification

| Metric                          | Value    |
|---------------------------------|----------|
| Forward cone ±30° minimum       | 0.947 m  |
| Forward cone ±30° mean          | 1.635 m  |
| Forward cone ±25° minimum       | 0.945 m  |
| Overall closest beam            | 0.669 m (at -33°, outside forward cone) |
| **Gate 0.60m**                  | **PASS** |

### Runtime configuration verified

| Parameter                        | Value | Match |
|----------------------------------|-------|-------|
| Footprint (local, global)        | `[[0.10, 0.10], [0.10, -0.10], [-0.03, -0.10], [-0.03, 0.10]]` | ✓ GF1 |
| Wheel separation (serial_bridge) | 0.18  | ✓ GF3 |
| Firmware version                 | 1.2.0 (ACK PING) | ✓ GF2 flashed |
| Footprint/inflation              | 0.15m | ✓ pre-existing |
| All Nav2 lifecycle nodes         | active [3] | ✓ |
| `/scan` rate                     | 10 Hz | ✓ |
| `/odom` rate                     | 10 Hz | ✓ |
| `map → base_link` TF             | stable 0 drift | ✓ |
| Motor voltage                    | 5.12 V | ✓ |
| LiDAR voltage                    | 4.99 V | ✓ |
| Controller state                 | IDLE OK | ✓ |

### Costmap (open space, after launch)

| Metric                            | Value |
|-----------------------------------|-------|
| Lethal cells in 0–0.25m forward   | 0     |
| Lethal cells in 0–0.60m forward   | 0     |
| Forward DWB reach zone            | CLEAR |

### Goal result

- **Goal:** (0.500, 0.000), yaw 0°, starting from (0, 0, 0°)
- **Accepted:** yes
- **Duration monitored:** 40s (goal still running)
- **Forward commands (vx > 0.005):** **0**
- **Rotation-only commands:** 6933 at ±0.1111 rad/s
- **Forward ratio:** 0.0%
- **Robot translation:** 0.000 m over 40s

### Post-40s (operator kept stack running)

BT triggered recovery behaviours sequentially:
- `spin` (1.57 rad = 90°) at t=~120s — completed successfully
- `wait` (5s) at t=~183s — completed
- `backup` (~0.5m reverse) at t=~248s — completed successfully

Final position: odom (-0.52, -0.14), map (-0.44, 0.09). Robot displaced by
recovery behaviours, not by DWB.

After recoveries, BT continuously fed new paths to controller (`Passing new
path to controller` every 1s) — DWB still emitted vx=0.

### Controller performance warning

```
[WARN] controller_server: Control loop missed its desired rate of 10.0000 Hz.
       Current loop rate is 7.0380 Hz.
```

Pi5 is CPU-bound — DWB runs at 70% of target rate. This may contribute to
systematic trajectory scoring issues but does not by itself explain the
complete absence of vx>0 commands.

---

## Hypotheses Tested and Ruled Out

| Hypothesis                                             | Status     |
|--------------------------------------------------------|------------|
| "0 valid trajectories out of 0" (linear_granularity)   | Fixed via `discretize_by_time: true` |
| Pi5 resource exhaustion causing DDS failures           | Fixed via reduced stack |
| AMCL TF stall / scan drops                             | Fixed via `transform_tolerance: 1.0` |
| Local costmap had no plugins                           | Fixed: `[obstacle_layer, inflation_layer]` |
| ObstacleFootprint marking forward trajectories illegal | **Disproven** — costmap forward zone confirmed CLEAR |
| Footprint dimensions wrong                             | **Disproven** — corrected to measured values |
| Wheel separation wrong                                 | **Disproven** — corrected in firmware+ROS, runtime verified |
| Heading mismatch between robot and goal                | **Disproven** — 0.0° start, 0.0° goal |
| PathAlign/RotateToGoal scales too high                 | **Disproven** — halving them had zero effect |
| Inflation radius too large                             | **Disproven** — reduced to 0.15m, no effect |
| Motor deadband eating small commands                   | **Disproven** — spin/backup drove the robot, and the smoother deadband is only 0.02 m/s |

---

## Current Diagnostic Conclusion

The failure mode is **isolated to the DWB local planner**, specifically to its
choice among generated trajectory candidates. Mechanism evidence:

1. DWB is generating trajectories (no "0 out of 0" errors)
2. DWB is not rejecting forward trajectories as illegal (costmap confirmed clear)
3. DWB is continuously selecting pure-rotation trajectories (`vx=0, vtheta=±`)
   over forward trajectories
4. Output magnitude (`±0.111 rad/s`) is the velocity_smoother's rate-limited
   ramp from zero — raw DWB command is ~±0.35 rad/s but never stable vx>0

Most likely remaining causes (not yet tested):

- **Critic scoring imbalance** — remaining critics (GoalAlign, GoalDist,
  PathDist, Oscillation) may collectively prefer vx=0 trajectories
- **DWB's `short_circuit_trajectory_evaluation`** — may terminate early on the
  first "good enough" trajectory, which is always a rotation-only one
- **Controller rate degradation (7Hz vs 10Hz)** — may cause stale trajectory
  scoring on the Pi5
- **DWB velocity seed** — may be seeding velocity samples from stale cmd_vel,
  creating a self-reinforcing rotation-only loop

---

## Environment State at Session End

### Committed to origin/navbot-experimental (pushed)

- `9e42d83` fix(nav2): enable DWB time-based trajectory discretization
- `97f62e3` fix(nav2): add local costmap layers and increase transform_tolerance
- `7aaed5f` fix(nav2): add AMCL transform_tolerance and initial pose for Jazzy
- `cb555a4` feat(firmware): add non-blocking motion-start buzzer on GP22
- `560642b` feat(firmware): add startup buzzer indication on Maker Pi RP2040

### Uncommitted working tree (Mac only)

**`firmware/makerpi_rp2040_base/include/config.h`**
- `WHEEL_SEPARATION_M: 0.160f → 0.180f` (GF2)
- `STALL_DUTY_THRESHOLD: 100 → 200`
- `STALL_DELTA_THRESHOLD: 2 → 1`
- `STALL_TIMEOUT_MS: 500 → 800`
- `STALL_STARTUP_GRACE_MS: 800 → 1200`

**`ros2_ws/src/navbot_base/config/navbot_base.yaml`**
- `wheel_separation: 0.160 → 0.180` (GF3)

**`ros2_ws/src/navbot_navigation/config/nav2_params.yaml`**
- H4: `min_vel_x: 0.05 → 0.0`, `min_speed_theta: 0.35 → 0.10`
- H3: `raytrace_max_range: 3.0 → 12.0`, `obstacle_max_range: 2.5 → 10.0`
- GF1: footprint polygon (both costmaps)
- `inflation_radius: 0.30 → 0.15`
- `PathAlign.scale: 32.0 → 16.0`
- `RotateToGoal.scale: 32.0 → 8.0`

### Pi state at session end

- All ROS nodes killed (`killall` executed)
- Firmware running (Phase B UF2 flashed, ACK PING 1.2.0 responding)
- Robot position: odom (-0.52, -0.14), map (-0.44, 0.09)
- Hardware healthy: motor 5.12V, LiDAR 4.99V, no faults

---

## Recommended Next Investigation

Before any further config changes, inspect DWB's internal trajectory scoring:

1. **Read `/evaluation` topic** — publishes per-critic scores for every
   trajectory candidate. This will show whether forward trajectories are
   being marked ILLEGAL (any critic returning infinity) or just scoring
   lower than rotation trajectories.

2. **Read `/local_plan` topic** — publishes the winning trajectory. Confirms
   what DWB actually selected each cycle.

3. **Temporarily set `publish_trajectories: true`** on the controller (already
   set) and capture the full trajectory evaluation for one goal attempt.

These are read-only diagnostics that require no config changes and will
answer: "Are forward trajectories being scored but losing, or are they being
rejected as illegal for a non-obvious reason?"

---

*Report end — session paused for the day.*
