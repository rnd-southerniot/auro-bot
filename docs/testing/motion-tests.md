# Motion Tests

Documented motion-test results for the Navbot platform. Each test is
reproducible; values below are what was actually measured, not targets.

For the broader project state and the list of pending tests, see
[../project-status.md](../project-status.md).

## First motion test — 120 mm forward drive

### Test configuration

- **Nav2 action:** `drive_on_heading`
- **Command:** `target.x = 0.10 m`, `speed = 0.05 m/s`
- **Commanded travel:** 100 mm
- **Surface:** indoor lab floor
- **Firmware:** 1.2.0 (this version was baseline; see
  [../../firmware/makerpi_rp2040_base/include/navbot_protocol.h](../../firmware/makerpi_rp2040_base/include/navbot_protocol.h)
  for the current version on subsequent tests)
- **Wheel radius (URDF):** `0.0325 m`

### Results

| Metric | Value |
|---|---|
| Commanded distance | 100 mm |
| Odom-reported distance | 119.3 mm |
| Physical tape measurement | 120 mm |
| Action reported `done` at | 102.6 mm commanded-frame |
| Odom vs physical error | 0.7 mm over 120 mm (~0.6%) |
| Lateral (Y) drift | 0.25 mm |
| Heading drift | 0.088° |

### Interpretation

**Odom accuracy:** 0.7 mm over 120 mm is within measurement noise of a
hand tape. The `wheel_radius = 0.0325 m` URDF value (commit `1952f6a`)
is validated against reality at this speed — no recalibration needed.

**Why the action reported done early (102.6 mm):** `drive_on_heading`
uses the commanded-frame displacement integral, not the odom integral.
The action considers itself done when it has *commanded* 100 mm worth
of motion, then yields back to the BT. By that moment, the robot has
actually traveled further due to coast-on.

**Coast-on:** 17 mm total between action-done and final rest. Breakdown:

- **~14 mm mechanical inertia** — the robot keeps rolling after the
  motor commands go to zero because of geartrain momentum and wheel
  inertia. This is not tunable in software; it is a physical property
  of the 30:1 gearbox + wheel mass at this speed.
- **~2.5 mm velocity_smoother ramp-down** — the
  `velocity_smoother` node interpolates between commanded velocities
  over a fixed window; the final ramp-down distance is a function of
  that window, not of `drive_on_heading`'s decel-envelope config.
- Remaining ~0.5 mm is measurement noise.

**Lateral and heading drift** are both within what you'd expect from
a differential-drive chassis at this low speed; they do not indicate
a wheel-sign or encoder issue.

### Why not Nav2 deceleration parameters

The `drive_on_heading` decel envelope parameters we attempted (commit
`fc4afff`) are only supported on Nav2 Kilted / Rolling — **not on
Jazzy** (our distro). That attempt was reverted at commit `8cf3319`.
Do not try to re-add these parameters without verifying the Jazzy API
first.

The currently-effective levers on coast-on are:

1. Lower commanded speed (already at 0.05 m/s here — going lower
   further reduces the mechanical inertia contribution but is also
   impractical for real navigation).
2. Firmware-side active counter-drive (in Phase C backlog; replaces
   the ineffective regen-brake experiment at
   [../notes/brake-attempt-forensic.md](../notes/brake-attempt-forensic.md)).
3. Tighter `velocity_smoother` window (currently minor contribution).

Counter-drive is the path being actively pursued. **Result: validated 2026-04-21
— see next section.**

## Counter-Drive Validation (2026-04-21)

Firmware active counter-drive implemented at commit `5185130` (FSM,
disabled), activated at commit `9b6d46a`, floor-validated at commits
`a65f008` (0.05 m/s) and `77375a2` (0.1 m/s). Full details in
[../validation/records/2026-04-21-counter-drive-floor.md](../validation/records/2026-04-21-counter-drive-floor.md).

### Design summary

- Per-motor 5-state FSM: IDLE → NORMAL → DECEL_MON → ACTIVE → (IDLE | FAULT)
- Triggered by cmd_vel transition to zero + 50 ms debounce + measured
  \|v\| ≥ 20 mm/s
- 15% reverse PWM applied during ACTIVE
- Encoder-gated termination: |v| < 6 mm/s for 3 consecutive 10 ms ticks
- HW watchdog alarm (RP2040 default alarm pool) caps pulse at 200 ms
- Shared abort: any motor FAULT cuts PWM on both motors
- No firmware current-fault check (Pi-side INA238 at 2 Hz is too slow);
  safety bounded by PWM cap + watchdog + encoder gating + shared abort

### Measured results (drive_on_heading, 5 trials each)

| Configuration | Commanded | Action-done | Physical tape | Coast mean | Coast stdev | Peak current |
|---|---|---|---|---|---|---|
| CD-off, 0.05 m/s | 100 mm | ~101 mm | ~115 mm | **13.15 mm** | 4.38 mm | ~155 mA |
| CD-on, 0.05 m/s | 100 mm | ~101 mm | ~101 mm | **0.44 mm** | 0.49 mm | ~155 mA |
| CD-on, 0.10 m/s | 300 mm | ~306 mm | ~311 mm | **4.82 mm** | 0.95 mm | ~280 mA |

**Reductions:** 97 % at 0.05 m/s, ~91 % at 0.1 m/s (vs KE-scaled baseline
expectation ~52 mm). Zero FAULT states across 15 trials total.

### Parameter origins

- `COUNTER_DRIVE_PWM_MAX = 150` (15 % of `MOTOR_PWM_WRAP=999`) — conservative
  initial cap; bench data showed motor stall current at 50 % PWM locked
  rotor ≈ 150 mA, giving ≫ 5× headroom to MX1508's 1 A continuous rating
- `COUNTER_DRIVE_V_STOP_MMS = 6` — raised from originally-designed 2 mm/s
  because 100 Hz control loop + 3943 CPR encoder gives single-count noise
  floor at ~5 mm/s
- `COUNTER_DRIVE_MAX_DURATION_MS = 200` — HW watchdog envelope, observed
  actual pulses terminate encoder-gated in < 150 ms
- `COUNTER_DRIVE_DEBOUNCE_TICKS = 5` (= 50 ms) — debounce ensures command
  chatter (cmd_vel oscillating around 0) doesn't trigger spurious pulses

## First rotation test — counter-drive in both directions (2026-04-22)

Firmware at commit `a445ffe` (CD-on with STOP-handler fix, see below).
Full trial data at
[../validation/records/2026-04-22-rotation-test.md](../validation/records/2026-04-22-rotation-test.md).

### Key result: STOP handler was preventing CD from firing

A bug was discovered this session: `NAVBOT_CMD_STOP` handler called
`reset_counter_drive_both()`, which force-reset the CD FSM to IDLE on
every STOP command. Because the Pi bridge sends `STOP` whenever cmd_vel
drops below its zero-deadband (1e-4), CD was reset before it could
fire. **Phase 5/6 linear tests passed only because firmware's internal
`handle_motion_timeout()` occasionally won a race with bridge's STOP**
— slow Nav2 velocity ramp-downs let firmware timeout fire first, which
does NOT reset CD. Tonight's rotation test with tight raw `/cmd_vel=0`
publishes lost the race deterministically.

Fix: remove `reset_counter_drive_both()` from STOP handler (commit
`a445ffe`). ESTOP/RESET still reset CD explicitly. STOP is now a soft
stop that yields to CD.

### Rotation results (17 trials total, all with CD active)

| Configuration | Coast mean | Stdev | N |
|---|---|---|---|
| 90° CCW | 9.58° | 1.28° | 5 |
| 90° CW | 10.60° | 1.14° | 5 |
| 180° CCW | 18.57° | 0.23° | 3 |
| 180° CW | 18.13° | 0.01° | 3 |
| 360° (calibration) | 28.08° | — | 1 |

**Direction symmetry at 90°: 1.11× (CW/CCW)** — well within the 2×
threshold that would flag per-motor asymmetry.

**Zero FAULT states** across all 17 trials. Peak current max 594.7 mA
(single outlier on one 180° CCW trial), typical ~150 mA.

### Coast-on scaling

Coast scales **approximately linearly with rotation duration**, not
with rotation magnitude squared. This is the signature of
**bridge→firmware latency at motion end** (~50-100 ms of continued
driving before STOP reaches firmware), plus a small fixed contribution
from the CD pulse. CD itself stops the wheel quickly; the extra coast
is motion happening while the command chain is still catching up.

| Rotation commanded | Coast | Coast / rotation |
|---|---|---|
| 90° | 9-11° | 0.10-0.12 |
| 180° | 18-19° | 0.10-0.11 |
| 360° | 28° | 0.08 |

### wheel_separation calibration

360° calibration trial: odom reported 353.2° total rotation. Physical
measurement: robot stopped ~11° short of start tape (physical ≈ 349°).

Back-solving:
```
wheel_sep_true = 0.180 × (353.2 / 349) ≈ 0.182 m
```

Firmware's `WHEEL_SEPARATION_M = 0.180` is **1.2% low** — acceptable as
is. **URDF's `wheel_offset_y = 0.08` (separation 0.160) is 12% low and
should be updated to 0.091 m**. This was a backlog item in
[../project-status.md](../project-status.md); tonight's test is the
first empirical confirmation of the magnitude.

## First Nav2 navigation goal (2026-04-22) — PARTIAL

First `navigate_to_pose` attempt with full Nav2 stack (SLAM + Nav2 behaviors).
Full record at
[../validation/records/2026-04-22-first-nav-goal-partial.md](../validation/records/2026-04-22-first-nav-goal-partial.md).

### What worked end-to-end

- `slam.launch.py` + `navbot_navigation/nav2.launch.py` brings up all nodes
  cleanly with LiDAR on. Lifecycle auto-activates without the manual
  workaround needed on 2026-04-21.
- SLAM publishes `/map` and `map → odom` TF.
- `navigate_to_pose` action accepts goals.
- DWB produces velocity commands (observed 81 msgs in 15 s on `/cmd_vel_nav`).
- velocity_smoother and collision_monitor propagate commands to `/cmd_vel`.
- base_bridge subscribes to `/cmd_vel` and ACKs commands to firmware.
- **The entire Nav2 pipeline is demonstrably wired correctly.**

### Why the robot didn't move

Goal: 0.5 m forward from current pose. DWB output:

| Stage | linear.x | angular.z |
|---|---|---|
| `/cmd_vel_nav` | 0.0 | -0.111 rad/s |
| `/cmd_vel_smoothed` | 0.0 | -0.075 rad/s |
| `/cmd_vel` | 0.0 | -0.075 rad/s |

At 0.075 rad/s angular, per-wheel tangential speed is **6.75 mm/s** — roughly
1/7 the speed where rotation tests worked (45 mm/s). The PID's output duty
is below the motor's static-friction threshold; wheels are commanded but
don't move.

DWB preferring rotation-only with a forward goal is a critic-weight tuning
issue (RotateToGoal.scale 8.0 vs GoalDist.scale 24.0). The `min_speed_theta`
floor of 0.10 rad/s is then sabotaged by velocity_smoother's ramp-up from
zero.

### Action items before next nav-goal attempt

1. Tune DWB (or switch to Regulated Pure Pursuit) so commanded velocity
   never drops below the motor's minimum-reliable-velocity threshold.
2. Empirically measure the robot's minimum-reliable-velocity via stepped
   CMD_VEL tests over serial.
3. Raise velocity_smoother's deadband to match.

## Current speed envelope

| Speed | Status |
|---|---|
| 0.05 m/s straight | **Validated** (Phase 5) — CD on, coast 0.44 ± 0.49 mm |
| 0.10 m/s straight | **Validated** (Phase 6) — CD on, coast 4.82 ± 0.95 mm |
| > 0.10 m/s | Not tested |
| 0.5 rad/s rotation | **Validated** (2026-04-22) — CD on, coast 9.58-10.60° at 90°, symmetric both directions |
| Higher angular velocities | Not tested |
| Nav2 `navigate_to_pose` | **Pipeline validated; controller-tuning blocks robot motion.** See nav-goal-partial record. |
| Sub-motion-threshold velocities | < 45 mm/s wheel tangential = robot won't physically move (static friction). Sets a floor for Nav2 velocity commands. |

## Related records

- Counter-drive floor validation (both speeds):
  [../validation/records/2026-04-21-counter-drive-floor.md](../validation/records/2026-04-21-counter-drive-floor.md)
- INA238 bench validation (unblocked CD work):
  [ina238-bench-validation.md](ina238-bench-validation.md)
- Counter-drive prior session handoff (historical; deferred at Phase 0.7):
  [../notes/counter-drive-session-handoff.md](../notes/counter-drive-session-handoff.md)
- Pre-wipe kinematic calibration:
  [../validation/records/2026-04-19-pre-wipe-calibration.md](../validation/records/2026-04-19-pre-wipe-calibration.md)
- Pre-Pi-rebuild DWB rotation-only diagnosis session:
  [../validation/records/2026-04-18-dwb-rotation-session.md](../validation/records/2026-04-18-dwb-rotation-session.md)
- Brake-attempt forensic (precursor to counter-drive):
  [../notes/brake-attempt-forensic.md](../notes/brake-attempt-forensic.md)
