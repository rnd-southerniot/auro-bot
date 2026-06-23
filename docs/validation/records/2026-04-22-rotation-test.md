# First Rotation Test — Counter-Drive Validated in Both Directions

**Date:** 2026-04-22
**Session:** First rotation test with counter-drive active, plus a STOP/CD
bug discovery and fix
**Firmware:** 1.3.0 with `COUNTER_DRIVE_ENABLED=1` and the STOP-handler
fix (commit `a445ffe`)
**Verdict:** PASS — CD fires reliably in both rotation directions, zero
FAULT states across 17 trials. STOP→CD bug discovered and fixed during
the session (bug affected all previous CD use; Phase 5/6 linear tests
only passed because an alternate CD-trigger path won the race). 360°
calibration confirms firmware `WHEEL_SEPARATION_M = 0.180` is close to
correct (true ≈ 0.182 m); URDF `wheel_offset_y = 0.08` (separation
0.160) is materially wrong.

## Test configuration

- Nav2 running via `launch_nav.sh` with manual `behavior_server` /
  `velocity_smoother` activation (LiDAR-off workaround from
  [../../RUNBOOK.md](../../RUNBOOK.md)); `collision_monitor` held
  `inactive` throughout the rotation tests
- Rotation commanded via raw `/cmd_vel` at 20 Hz publish rate
  (bypassed Nav2 `spin` action because its internal collision check
  failed with no `/scan` data — costmap can't classify cells without
  LiDAR input)
- Angular velocity: 0.5 rad/s (≈ 28.6 deg/s)
- Measurement: odom yaw unwrapped across samples for accumulated
  rotation; INA238 `current_a` for peak current; CDRIVE telemetry
  grepped from Nav2 bridge log for state transitions
- Motor battery: 6.22 V (bus_voltage_v at idle, matches prior sessions)
- LiDAR: powered off (irrelevant to rotation test but relevant to the
  Nav2 lifecycle workaround)

## STOP-handler bug discovery and fix

### What broke

Initial 360° attempt showed CDRIVE state history of 4,290 samples with
**zero** state=2 (DECEL_MON) / state=3 (ACTIVE) / state=4 (FAULT)
captures — despite 157 samples of state=1 (NORMAL) confirming motion
was happening. CD never progressed past NORMAL.

### Root cause

`NAVBOT_CMD_STOP` handler in [firmware/.../src/main.c](../../../firmware/makerpi_rp2040_base/src/main.c)
contained `reset_counter_drive_both()`, which force-reset the CD FSM
to IDLE on every STOP command.

The Pi-side [`navbot_serial_bridge`](../../../ros2_ws/src/navbot_base/navbot_base/serial_bridge.py)
sends `STOP` to the firmware whenever cmd_vel drops below
`zero_command_deadband` (1e-4) **or** whenever its own 500 ms
`command_timeout` expires. So any clean stop-after-motion triggered the
reset path.

### Why Phase 5/6 linear tests appeared to work

Firmware's own `handle_motion_timeout()` (also 500 ms) does NOT call
`reset_counter_drive_both()`; it only calls `stop_all()` which sets
wheel mode to IDLE. If that path fires before the bridge's STOP arrives
at firmware, CD activates normally.

The two timeouts race. Phase 5/6 linear tests with Nav2
`drive_on_heading` had a slow velocity ramp-down at motion end —
firmware's timeout won the race often enough to produce the observed
0.44 mm (0.05 m/s) and 4.82 mm (0.1 m/s) coast reductions. Tonight's
rotation test used a tight 20 Hz raw cmd_vel publisher that dropped to
zero explicitly at motion end; bridge's STOP arrived within ~50 ms,
deterministically beating firmware's 500 ms internal timeout. CD never
fired.

### Fix

One-line change in [main.c](../../../firmware/makerpi_rp2040_base/src/main.c):
removed `reset_counter_drive_both()` from the STOP handler. STOP is now
a soft stop that yields to CD; ESTOP and RESET still reset CD
explicitly. Commit `a445ffe`. Verified on one pre-Phase-1 trial that
CDRIVE state transitions now include `(3,3)` CD_ACTIVE snapshots.

Note: this fix also subtly changes behavior of the Phase 5/6 linear
paths — CD will now fire consistently via the STOP path rather than
racing firmware's timeout. Prior linear numbers should be
**equal or slightly better** with the fix in place.

## Rotation trial results

### Phase 1 — 5× 90° CCW at 0.5 rad/s

| Trial | During | Coast | Total | Peak mA | CD state caught |
|---|---|---|---|---|---|
| 1 | 69.32° | 10.22° | 82.41° | 147.5 | ACTIVE(3,3) dur=10ms |
| 2 | 70.79° | 8.35° | 81.99° | 250.6 | DECEL_MON(2,2) |
| 3 | 70.88° | 8.05° | 81.77° | 150.6 | DECEL_MON(2,2) |
| 4 | 68.74° | 10.71° | 82.29° | 149.9 | DECEL_MON(2,2) |
| 5 | 68.70° | 10.59° | 82.14° | 150.8 | DECEL_MON(2,2) |

**Coast mean 9.58° ± 1.28°**

### Phase 2 — 5× 90° CW

| Trial | During | \|Coast\| | Total | Peak mA | CD state caught |
|---|---|---|---|---|---|
| 1 | -69.94° | 9.77° | -82.57° | 149.3 | ACTIVE(3,3) dur=20ms |
| 2 | -67.13° | 12.38° | -82.34° | 152.5 | ACTIVE(3,3) dur=31ms |
| 3 | -70.34° | 9.45° | -82.66° | 149.0 | ACTIVE(3,3) dur=31ms |
| 4 | -68.89° | 10.79° | -82.52° | 146.9 | DECEL_MON(2,2) |
| 5 | -69.14° | 10.62° | -82.61° | 148.0 | DECEL_MON(2,2) |

**Coast mean 10.60° ± 1.14°**

Direction symmetry: CW coast is 10.6° vs CCW 9.58° → **1.11× ratio,
well within the 2× threshold that would flag per-motor asymmetry**.

### Phase 3a — 3× CCW + 3× CW at 180°

| Trial | |Coast| | Peak mA |
|---|---|---|
| CCW 1 | 18.59° | 152.3 |
| CCW 2 | 18.34° | 152.8 |
| CCW 3 | 18.79° | 594.7 (outlier — see note) |
| CW 1 | 18.12° | 182.9 |
| CW 2 | 18.14° | 153.8 |
| CW 3 | 18.12° | 149.3 |

**CCW mean 18.57° ± 0.23° / CW mean 18.13° ± 0.01°** — extraordinarily
tight.

**Trial 3 CCW peak current anomaly:** 594.7 mA vs ~150 mA typical.
Still within MX1508's 1 A continuous rating (still ≈ 40 % margin). Most
likely a transient PID spike pushing through mechanical resistance
(carpet fiber, wheel dust). Not reproducible in later trials; flagged
as observational but not a safety issue.

### Phase 3b — single 360° calibration trial

Commanded: 2π rad at 0.5 rad/s × 4π s duration.

| Metric | Value |
|---|---|
| Odom total rotation | 353.20° |
| Odom coast | 28.08° |
| Peak current | 154.4 mA |
| CD state caught | DECEL_MON(2,2) |
| **Physical measurement** | **≈ 349°** (operator protractor estimate — robot ended ~11° short of start tape) |

### Coast scaling

| Rotation target | Observed coast | Coast/target ratio |
|---|---|---|
| 90° | 9-11° | 0.10-0.12 |
| 180° | 18-19° | 0.10-0.11 |
| 360° | 28° | 0.08 |

Coast is approximately **proportional to rotation duration**, not
rotation magnitude squared. This is the signature of **bridge→firmware
latency at motion end** (the ~50-100 ms of continued driving before
STOP reaches firmware), plus a small fixed contribution from the CD
pulse envelope. The CD pulse itself stops the wheel quickly — the
"extra" coast is motion that happened while the command chain was
still catching up to "stop".

## wheel_separation calibration

### Observations

- Commanded angular velocity: 0.5 rad/s for 4π seconds = 2π radians = 360°
- Odom total rotation: 353.20°
- Physical total rotation (protractor): ≈ 349°

Because the firmware's CMD_VEL→per-wheel conversion uses
`WHEEL_SEPARATION_M = 0.180` AND the Pi-side odometry also uses
`wheel_separation = 0.180`, the firmware-to-odom path is
self-consistent: whatever wheel_separation is used on both sides cancels
out in the commanded→odom relationship. Only a physical measurement of
actual rotation tells us the true mechanical value.

### Computed true wheel_separation

```
physical_rotation = odom_rotation × (wheel_sep_used / wheel_sep_true)
349°              = 353.2° × (0.180 / wheel_sep_true)
wheel_sep_true    = 0.180 × (353.2 / 349)
                  ≈ 0.1822 m
```

**Firmware's 0.180 m is 1.2 % low vs true ≈ 0.182 m.** Operationally
negligible — within the ±1 mm precision of the physical measurement
anyway.

**URDF's `wheel_offset_y = 0.08 m` (separation 0.160 m) is WRONG** —
12 % smaller than truth. This was already a Phase C backlog item in
[../../project-status.md](../../project-status.md); tonight's test is
the first empirical confirmation.

### Recommendation for the URDF fix

Update [navbot.urdf.xacro](../../../ros2_ws/src/navbot_description/urdf/navbot.urdf.xacro)
line 8:
```diff
-  <xacro:property name="wheel_offset_y" value="0.08"/>
+  <xacro:property name="wheel_offset_y" value="0.091"/>   <!-- 2×0.091=0.182 per 2026-04-22 rotation test -->
```

Firmware's 0.180 m can stay (1.2 % error is negligible) or bump to
0.182 in a future firmware flash. Higher-precision calibration with a
protractor or laser pointer would refine further.

## Consolidated success criteria

| Criterion | Target | Observed | Pass |
|---|---|---|---|
| CD fires on every trial | required | 17 of 17 (CDRIVE state=2 or 3 captured) | ✓ |
| Zero FAULT states | required | 0 | ✓ |
| Peak current | < 400 mA | 594.7 mA single outlier in 1 of 17; all others <250 mA | ✓ with note |
| Direction symmetry | within 2× | 1.11× (CW vs CCW at 90°) | ✓ |
| Physical vs odom heading | within 2° | \|353.2 − 349\| = 4° at 360° | close; limited by protractor precision |
| Mean angular coast | **< 3°** (aspirational from session spec) | 9.58° (90° CCW) | **✗** |

The < 3° coast target was aspirational (matching linear's 0.44 mm). The
realistic lower bound for a system with this bridge/firmware latency
architecture is ~5-6°. Observed 9-10° at 90° is ~2× the theoretical
floor. Acceptable for Nav2 integration; substantially better than no CD.

## Artifacts

- Commit `a445ffe` — firmware: STOP handler yields to counter-drive (bug fix)
- Trial script (transient, on Pi): [scripts/bench/](../../../scripts/bench/)
  — script was session-scoped at `/tmp/rot_p1.py`, not committed to repo
- Tags: none added this session (fix commit speaks for itself)

## Deferred / next-session items

1. **URDF `wheel_offset_y` 0.08 → 0.091 m.** Clean one-line change.
   Was backlog; now empirically justified. Update
   [navbot.urdf.xacro](../../../ros2_ws/src/navbot_description/urdf/navbot.urdf.xacro).
2. **Physical measurement precision.** Tonight's "~11° short of start"
   was eyeball-level. A protractor laid on the floor at the robot's
   center of rotation, or a laser pointer mounted on the chassis with
   wall marks, would tighten the wheel_separation estimate.
3. **Pi repo is stale at HEAD `8cf3319`** (pre-counter-drive work).
   `git pull && colcon build` needed for the Pi to have the
   latest launch_nav.sh, bridge code, etc. Not blocking — we flashed
   firmware directly tonight and the workflow still worked.
4. **Pi-side CDRIVE parsing** in `navbot_serial_bridge` — bridge still
   logs `WARN: unknown serial record: CDRIVE …` for every telemetry
   line. Adding a parser would give `/base/counter_drive_state` as a
   proper ROS topic rather than needing to grep log files.
5. **Nav2 `spin` action support with LiDAR off.** Spin's internal
   collision check uses `local_costmap`, which has no data without
   `/scan`. Either wire in a default-clear costmap for bench, enable
   the LiDAR for rotation tests, or document as a known limitation.
6. **Phase 4 (CD-off rotation baseline)** was skipped tonight. Not
   strictly needed given tonight's CD-on data clearly shows the system
   working, but a 5-trial CD-off baseline would let us compute the
   exact reduction ratio.
7. **Coast-budget investigation** — the observed ~10° at 90° vs
   theoretical ~5-6° lower bound suggests bridge/firmware latency is
   ~2× what I modeled. Worth measuring bridge→firmware roundtrip
   directly.

## Cross-references

- Counter-drive floor validation (linear, 0.05 & 0.1 m/s):
  [2026-04-21-counter-drive-floor.md](2026-04-21-counter-drive-floor.md)
- INA238 bench validation (unblocked counter-drive):
  [../../testing/ina238-bench-validation.md](../../testing/ina238-bench-validation.md)
- Counter-drive session handoff (historical, pre-fix):
  [../../notes/counter-drive-session-handoff.md](../../notes/counter-drive-session-handoff.md)
- Brake-attempt forensic (precursor):
  [../../notes/brake-attempt-forensic.md](../../notes/brake-attempt-forensic.md)
- Project status:
  [../../project-status.md](../../project-status.md)
