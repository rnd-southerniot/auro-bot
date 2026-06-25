# Navbot Project Status

**Last updated:** 2026-06-16 (session 13 — home reassembly, power reconfig, full peripheral bring-up, motor wiring fixes, IMU flipped-mount reconfigure)
**Branch:** `navbot-experimental`
**Location:** Moved from the office lab to **home** as of 2026-06-16. The
  `office_lab` / `office_lab_v2` maps are office-only and **no longer
  usable** — a fresh home-environment SLAM map is required before any
  AMCL / Nav2 work resumes.
**HEAD at update time:** Pi working tree on `navbot-experimental` (HEAD stale
  at `dc04ba9`, ~14 rsync'd uncommitted files); session-13 IMU driver/config
  edits applied to the Pi (backups `*.bak-20260616`) and staged on the Mac
  checkout — not yet committed.
**2026-06-25 note:** LiDAR `/scan` is **healthy again** (720 beams; the prior
  boot timeout was a flat LiDAR pack, now charged) — a fresh home SLAM map run is
  unblocked (`navbot-nav` still disabled until a map exists). Voice-side this
  session: cumulative **≤6 s/episode motion budget** (drive-chaining fix) and
  **visual search** (`look_around`+`turn`); both bench-validated on blocks. See
  [validation/records/2026-06-25-voice-motion-budget.md](validation/records/2026-06-25-voice-motion-budget.md)
  and [.../2026-06-25-visual-search.md](validation/records/2026-06-25-visual-search.md).
  A `CDRIVE` serial-bridge log-spam (firmware emits a record the bridge doesn't
  parse) was observed — open follow-up.
**Firmware version:** `1.3.0` (unchanged) with counter-drive + TEST_PWM +
  wheel_radius 0.0325 m. RP2040 confirmed live this session (`ACK PING
  1.3.0`, `STATE IDLE OK`).
**Key milestone commits:**
  `pre-counterdrive-code-v2` → `5185130` (FSM implemented, disabled) → `9b6d46a`
  (CD enabled) → `a65f008` (floor-validated 0.05 m/s) → `77375a2` (0.1 m/s) →
  `a445ffe` (STOP-CD bug fix, rotation validated) → `55badc6` (URDF wheel_offset_y
  calibrated to 0.091 m from empirical 360° rotation test).

This is the single source of truth for project state. It replaces
ad-hoc tracking of Phase C state in session transcripts. Update at the
end of each substantive session.

## Current State

The robot was **reassembled at home** with a new power architecture and
brought back to a **fully bench-operational** state on 2026-06-16
(session 13). All peripherals verified — see
[validation/records/2026-06-16-home-reassembly-bringup.md](validation/records/2026-06-16-home-reassembly-bringup.md).

**Power architecture (new):** 3S LiPo → 5V converter feeds the **Pi 5 only**
(`vcgencmd get_throttled` = `0x0`, no undervoltage — this retires the
undervoltage condition that capped the earlier v1.2.0 validation). The
INA238 was **moved from the Pi 5V rail to the motor power rail**, which
also powers the RP2040; it reads ~6.27 V (consistent with 6 V motors —
confirm nominal). LiDAR is separately powered.

**Drive train:** both motors verified under closed-loop `CMD_VEL` (forward,
balanced, no stall/runaway) after fixing reassembly wiring faults (left
direction inversion + dead/loose right M1 lead). Pin map unchanged: LEFT =
M2 (GP10/11, enc GP2/3, swap_dir false); RIGHT = M1 (GP8/9, enc GP4/5,
swap_dir true).

**IMU:** reinstalled flipped 180° about the forward axis; rather than
remount, added a new driver orientation mode `x_forward_flipped` (`(x,−y,−z)`)
and verified Z-up + correct +CCW yaw on hardware. EKF fuses yaw + yaw-rate
only, mag fusion stays disabled, so the orientation fix is fully sufficient
for nav. See [navbot_imu/README](../ros2_ws/src/navbot_imu/README.md).

**Known open items (non-blocking):** GP27 `motor_v` sense divider is
disconnected (telemetry reads false ~0 V; web console motor voltage wrong);
INA238 calibration in `navbot_power/config/ina238.yaml` is still set for the
old 5 V Pi rail and needs recomputing for the motor rail (need motor stall
current). **Maps:** `office_lab*` are stale (now at home) — capture a fresh
home map next session.

Earlier baselines still valid: first motion test <1 mm odom error
([testing/motion-tests.md](testing/motion-tests.md)); Foxglove default
layout ([operations/foxglove/README.md](operations/foxglove/README.md));
brake experiment reverted with forensics
([notes/brake-attempt-forensic.md](notes/brake-attempt-forensic.md)).

## Active Work

**No nav work in-flight — this session was hardware bring-up.** Session 13
(2026-06-16) reassembled the robot at home, reworked power, and brought all
peripherals back online. Full record:
[validation/records/2026-06-16-home-reassembly-bringup.md](validation/records/2026-06-16-home-reassembly-bringup.md).

- **Power:** 3S LiPo + 5V converter for the **Pi only** (clean, no
  undervoltage); INA238 relocated to the **motor rail** (~6.27 V, also
  powers the RP2040); LiDAR separately powered.
- **Bring-up:** Pi power PASS; RP2040 fw 1.3.0 (the initial "dead Pico"
  was a **charge-only USB cable** — swapped for a data cable); encoders
  PASS; LiDAR `/scan_raw` 9.97 Hz; INA238 alive at 0x40; IMU all three
  chips on the bus at 50 Hz.
- **Motor wiring fixes:** left direction inversion corrected; right motor
  was dead then inverted (loose/reversed **M1** lead) — leads swapped and
  reseated. Final closed-loop `CMD_VEL` forward: both wheels forward,
  L +2692 / R +2681 matched, no stall/runaway.
- **IMU reconfigure:** board remounted flipped 180° about the forward
  axis; added driver mode `x_forward_flipped` (`(x,−y,−z)`), verified
  accel Z-up (+10.99) and +CCW yaw (gyro_z +0.64 on a CCW spin). Mag
  recal deferred (fusion disabled, out of nav path).
- **Open follow-ups:** reconnect GP27 `motor_v` sense divider; recompute
  INA238 calibration for the motor rail (needs motor stall current).

**Session 12 (2026-04-23) — recorded retroactively, work DEFERRED to next
session:** built `maps/office_lab_v2` (a larger 9.75 × 7.80 m square-path
map, ~2× the session-11 area) to attack the AMCL sparse-map drift, and
pointed `map_server` at it. Session ended early — **AMCL validation on v2,
the multi-waypoint rerun, and higher-speed testing were all deferred and
remain queued.** ⚠️ The 2026-06-16 move to **home** makes the `office_lab*`
maps obsolete, so that queued nav work now restarts from a **fresh home
SLAM map** rather than `office_lab_v2`.

---

### Session history (pre-relocation, office lab)

Session 11 shipped map persistence + AMCL
localization end-to-end:

- **Saved map** `maps/office_lab.{pgm,yaml}` built from a programmatic
  spin+drive sweep (teleop_twist_keyboard didn't transmit keys over
  SSH, so switched to a drive script).
- **`navbot_bringup/localization.launch.py`** brings up the full
  map-based stack: base + LiDAR + IMU fusion + EKF + map_server +
  AMCL + Nav2.
- **`scripts/multi_waypoint.py`** executes a 4-leg route via
  `nav2_simple_commander.BasicNavigator`.
- **GATE 1 passed**: 0.3 m goal SUCCEEDED on saved map after
  /initialpose (quaternion normalization to < 1e-6 tolerance was
  required — Nav2 AMCL rejects malformed quaternions).
- **Multi-waypoint result**: 3/4 legs SUCCEEDED, return-to-origin
  accuracy 1.5 cm XY (excellent), 55.7° yaw (poor). AMCL has
  difficulty on the sparse-feature map built from a short drive;
  improving map quality is the unblocker for waypoint repeatability
  and higher-speed navigation.
- **Task 3 (higher speed) partial**: 0.20 m/s parameters verified
  live (lin.x peaked at 0.2000 exactly), but full-length goals
  TIMEOUT'd due to the same AMCL drift issue. Speed envelope
  extension deferred.

Full record:
[validation/records/2026-04-23-map-save-load-and-waypoints.md](validation/records/2026-04-23-map-save-load-and-waypoints.md).

Session 10 followed up on session 9 with
three calibration tasks: magnetometer hard-iron calibration,
`wheel_radius` audit, and a 3-trial spin-and-return heading drift
benchmark. Headline findings:

- **Raw /odom round-trip drift: 0.36° per 360°** — wheel encoders on
  this chassis are essentially drift-free under balanced motion.
  Better than most platforms. The prior "~11°" figure was dominated
  by command-rotation scaling mismatch, not sensor drift.
- **Mag fusion during motion degraded heading by 10× vs encoder-only**
  (EKF round-trip drift 9.73° with high per-trial variance). Diagnosed
  as motor-coil EM interference at the IMU's axle-height mount.
  Reverted `use_mag: true → false`; kept calibration infrastructure
  (±4.0 gauss gain, hard-iron offsets) for future re-enable if the
  IMU can be physically relocated.
- `wheel_radius` aligned everywhere to 0.0325 m (URDF + firmware +
  `navbot_base.yaml`).

Full record:
[validation/records/2026-04-22-mag-calibration-and-heading-benchmark.md](validation/records/2026-04-22-mag-calibration-and-heading-benchmark.md).

Session 9 delivered IMU integration end-to-end:
gyro + accel driver at 50 Hz, complementary filter producing fused
orientation, robot_localization EKF fusing wheel odometry (x, y, vx) with
IMU (yaw, vyaw), Nav2 switched to `/odometry/filtered`. A 180° in-place
rotation test executed as a clean monotonic sweep with zero oscillation,
a qualitative step up from the 50–90° overshoot behaviour documented
pre-IMU. Magnetometer deferred — local field is 1.4 gauss near the axle-
height mount, well above Earth's 0.65 gauss max, indicating a strong
hard-iron bias from the motor magnets that blocks compass fusion until
calibrated. Also shipped: RPP terminal-rotation damping
(`rotate_to_heading_angular_vel: 0.5 → 0.3`, `max_angular_accel: 1.5 → 1.0`).

Full record:
[validation/records/2026-04-22-imu-integration.md](validation/records/2026-04-22-imu-integration.md).

Session 8 delivered three Nav2 milestones (first autonomous goal,
4-step round-trip, wheel_radius fix):

1. **First autonomous nav goal SUCCESS** — three goals (1 m straight,
   0.3 m + 90°, return) all `STATUS_SUCCEEDED`, ~2.2 m total autonomous
   travel. Enabled by switching FollowPath DWB → RPP after two sessions
   of unsuccessful DWB critic tuning.
2. **4-step out-and-back sequence** — validated pure-rotation goals
   (steps 2 & 4) and round-trip composites. Observed visible curvature
   on forward legs; traced to firmware/URDF wheel_radius mismatch.
3. **`wheel_radius` fix + straight-line verification** — firmware
   0.033 → 0.0325 m (matches URDF). Mean commanded `ang.z` during
   forward translation dropped from +0.141 rad/s to ±0.014 rad/s
   (**10× reduction**); travel ratio improved from 70 % to 96–98 %
   of commanded. `xy_goal_tolerance` tightened 0.15 → 0.05 m.

Full records:
[first-nav-goal-success](validation/records/2026-04-22-first-nav-goal-success.md),
[four-step-sequence](validation/records/2026-04-22-nav2-four-step-sequence.md),
[wheel-radius-fix](validation/records/2026-04-22-wheel-radius-fix.md).

## Recent Milestones

- **2026-06-16 — home reassembly + power reconfig + full bring-up +
  motor/IMU fixes (session 13).** Relocated to home. New power: 3S+5V
  for Pi only (throttled=0x0, undervoltage blocker retired); INA238 moved
  to the motor rail (also powers RP2040, ~6.27 V). Full peripheral
  bring-up over SSH: found and fixed a charge-only USB cable (RP2040),
  a left motor direction inversion, and a dead→inverted right M1 motor
  lead. Closed-loop `CMD_VEL` forward verified (L+2692/R+2681, balanced,
  no stall). IMU remounted flipped 180° about forward axis → added driver
  mode `x_forward_flipped` (`(x,−y,−z)`), verified Z-up + +CCW yaw on HW.
  Open: GP27 motor_v sense wire, INA238 motor-rail recal. Full record:
  [validation/records/2026-06-16-home-reassembly-bringup.md](validation/records/2026-06-16-home-reassembly-bringup.md).
- **2026-04-23 — larger map for AMCL drift (session 12, deferred).** Built
  `maps/office_lab_v2` (9.75 × 7.80 m square-path drive, ~2× session-11
  area) to fix sparse-map AMCL yaw drift, and set `map_server` default to
  it. Ended early; AMCL validation + waypoint rerun + higher-speed testing
  deferred. Superseded by the home move — needs a fresh home map. Commit
  `dd860c4`.
- **2026-04-23 — map persistence + AMCL + multi-waypoint route
  (session 11).** Built 4.7 × 5.65 m reference map via a programmatic
  spin + drive, saved as `maps/office_lab.{pgm,yaml}`. Wrote
  `navbot_bringup/localization.launch.py` bringing up the full
  map-based stack (map_server + AMCL + Nav2). AMCL's initialpose
  validator rejected our first publishes as "malformed" — cause was
  quaternion precision slightly off unit length (|q|² = 0.9997 vs
  tolerance 1e-6); fix is to compute via `sin/cos(yaw/2)` and
  renormalize. GATE 1 passed with a 0.3 m goal succeeding cleanly.
  `scripts/multi_waypoint.py` uses `nav2_simple_commander` to run a
  4-leg square route. First run: 3/4 legs SUCCEEDED, 1.5 cm return-
  to-origin XY accuracy, 55.7° yaw error — AMCL has difficulty on
  the sparse-feature map. Higher-speed (0.20 m/s) params verified
  live via dynamic `ros2 param set` but goals still TIMEOUT on the
  same AMCL issue; speed envelope extension deferred. Full record:
  [validation/records/2026-04-23-map-save-load-and-waypoints.md](validation/records/2026-04-23-map-save-load-and-waypoints.md).
- **2026-04-22 late evening — mag calibration + wheel_radius audit +
  heading benchmark (session 10).** Magnetometer hard-iron calibration
  via 60 s rotation sweep succeeded after raising CRB_REG_M gain
  ±1.3 → ±4.0 gauss (original range was saturating on the Y axis
  because motor bias pushed baseline to the ceiling). Post-calibration
  |mag_vec| at rest: 0.42 gauss, right in Earth's band. Static
  rotation test: yaw tracked ~90° manual rotation cleanly (-5.2° →
  -107.8°, spread 0.07°). But 3-trial spin-and-return benchmark
  revealed mag fusion DEGRADES heading during motor activity —
  EKF round-trip drift 9.73° (stdev 10.69°) vs raw /odom 0.36°
  (stdev 0.18°). Reverted `use_mag: false`; mag-cal infrastructure
  preserved for future re-enable. Also aligned `navbot_base.yaml`
  `wheel_radius: 0.033 → 0.0325` (matches firmware + URDF). Full
  record:
  [validation/records/2026-04-22-mag-calibration-and-heading-benchmark.md](validation/records/2026-04-22-mag-calibration-and-heading-benchmark.md).
- **2026-04-22 late evening — IMU integration end-to-end (session 9).**
  Layers 1/2/3 all shipped in one session: L3G4200D gyro + LSM303DLHC
  accel + mag driver at 50 Hz (`navbot_imu/l3gd20_lsm303d_reader`),
  `imu_complementary_filter` producing `/imu/data` orientation at 50 Hz
  with `use_mag: false`, `robot_localization` EKF publishing
  `/odometry/filtered` at 30 Hz fusing wheel odom (x, y, vx) with IMU
  (yaw, vyaw). EKF now owns the `odom → base_footprint` TF
  (`navbot_serial_bridge.publish_tf: false`). Nav2 switched to
  `/odometry/filtered`. End-to-end validation: 180° in-place rotation
  executed as a clean monotonic sweep at -0.287 ± 0.013 rad/s across
  108 samples with zero oscillation and 12.4° terminal error — vs
  pre-IMU 50–90° overshoot with wild oscillation. Also shipped RPP
  terminal-rotation damping (`rotate_to_heading_angular_vel: 0.3`,
  `max_angular_accel: 1.0`). Magnetometer calibration deferred —
  local field 1.4 gauss near motor stack. Full record:
  [validation/records/2026-04-22-imu-integration.md](validation/records/2026-04-22-imu-integration.md).
- **2026-04-22 late evening — wheel_radius calibration fix + straight-
  line verification.** Firmware `LEFT_WHEEL_RADIUS_M` /
  `RIGHT_WHEEL_RADIUS_M` 0.033 → 0.0325 m (matches URDF). Rebuilt in
  [firmware/makerpi_rp2040_base/build/](firmware/makerpi_rp2040_base/build/),
  flashed via BOOTSEL (Pi-side mount of `/dev/sda1`, copy UF2, unmount —
  Pico auto-reboots to CDC in 2 s). `xy_goal_tolerance` tightened
  0.15 → 0.05 m now that odometry is calibrated. Two back-to-back
  0.5 m forward tests: mean `ang.z` during translation collapsed 10×
  (+0.141 → ±0.014 rad/s), travel ratio 70 → 96–98 %, XY convergence
  within 3–4 cm of goal. Full record:
  [validation/records/2026-04-22-wheel-radius-fix.md](validation/records/2026-04-22-wheel-radius-fix.md).
- **2026-04-22 late evening — 4-step out-and-back sequence.** Four
  goals (0.5 m fwd, 180° in place, 0.5 m fwd, 180° in place) all
  `STATUS_SUCCEEDED`. Pure in-place rotation goals validated: ang.z
  saturated at `rotate_to_heading_angular_vel: 0.5 rad/s` for 71
  samples with zero linear velocity. Net drift 12.6 cm / 18.8° over
  the round-trip, within the 4 × tolerance-stack budget but visible
  forward-leg curvature motivated the wheel_radius fix.
  [validation/records/2026-04-22-nav2-four-step-sequence.md](validation/records/2026-04-22-nav2-four-step-sequence.md).
- **2026-04-22 late evening — FIRST AUTONOMOUS NAV GOAL SUCCESS.**
  Three consecutive `navigate_to_pose` goals all returned
  `STATUS_SUCCEEDED`. Path: applied costmap inflation reductions
  (0.15 → 0.05 m in local_costmap, explicit 0.05 m in global_costmap
  overriding Nav2's 0.55 m default) and DWB `sim_time: 1.5 → 1.0 s`,
  then re-attempted — DWB still commanded zero forward velocity
  despite a 1.36 m clear forward corridor, confirming the controller
  was the blocker, not the costmap. Switched `FollowPath` from
  `dwb_core::DWBLocalPlanner` to
  `nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController`.
  Three goals executed cleanly on the first attempt: 1.0 m straight
  (0.846 m actual, 85 % ratio matching motor envelope), 0.3 m + 90°
  composite (0.313 m + 77.5°), and 1.1 m + 84° return. RPP's
  `rotate_to_heading_angular_vel: 0.5 rad/s` and `desired_linear_vel:
  0.15 m/s` were both hit exactly by the robot. Full record:
  [validation/records/2026-04-22-first-nav-goal-success.md](validation/records/2026-04-22-first-nav-goal-success.md).
- **2026-04-22 evening Nav2 tuning + second nav-goal attempt (PARTIAL IMPROVED).**
  Phase 0 stepped cmd_vel tests showed motor has no real deadband (moves
  down to 0.005 m/s / 0.05 rad/s at 80 % of commanded). First Nav2 tuning
  (commit `7d1a33e`) with `min_speed_xy: 0.02` + `min_vel_x: 0.02`
  starved DWB's trajectory sampler ("No valid trajectories out of 0!") —
  BT fell back to spin recoveries. Fix (commit `dc04ba9`): remove
  `min_speed_xy`, restore `min_vel_x: 0`. Third attempt: DWB produced
  trajectories, robot executed commanded rotation toward goal (130° CCW
  in ~18 s), but forward translation still blocked by `ObstacleFootprint`
  critic rejecting forward samples that project into costmap inflation
  around LiDAR-seen obstacles at ~30 cm. Full analysis:
  [validation/records/2026-04-22-nav2-tuning-partial.md](validation/records/2026-04-22-nav2-tuning-partial.md).
- **2026-04-22 URDF calibration + first nav-goal attempt (PARTIAL).** Task 1
  applied wheel_offset_y 0.08 → 0.091 m per empirical rotation calibration
  (commit `55badc6`). Task 2 synced Pi repo from `8cf3319` → `55badc6` and
  rebuilt 12 packages (13.5 s, zero warnings). Task 3 launched full Nav2
  stack: SLAM + Nav2 lifecycle auto-activated cleanly with LiDAR on (no
  manual workaround like 2026-04-21 needed). DWB produces commands,
  velocity_smoother and collision_monitor propagate, base_bridge receives —
  **pipeline validated end-to-end**. Robot doesn't move because DWB's
  commanded velocity (~6.75 mm/s wheel tangential after smoothing) is below
  the motor's static-friction threshold. Full analysis:
  [validation/records/2026-04-22-first-nav-goal-partial.md](validation/records/2026-04-22-first-nav-goal-partial.md).
- **2026-04-22 First rotation test + STOP-handler bug fix.** 17 trials
  across 90°/180°/360° in both directions, all with CD active. Coast
  mean 9.58° at 90° CCW (10.60° CW — 1.11× symmetry), 18.35° at 180°,
  28° at 360°. Zero FAULT states. Discovered and fixed a CD-activation
  bug: `NAVBOT_CMD_STOP` was force-resetting CD state, which had been
  masked in Phase 5/6 because a timing race with firmware's internal
  timeout path let CD fire anyway. With commit `a445ffe`, STOP now
  yields to CD cleanly. 360° calibration gives empirical
  wheel_separation ≈ 0.182 m (vs firmware's 0.180 — 1.2% low, OK) and
  confirms URDF's 0.160 is wrong by 12%. Full record at
  [validation/records/2026-04-22-rotation-test.md](validation/records/2026-04-22-rotation-test.md).
- **2026-04-21 Counter-drive firmware DELIVERED.** Full design, implementation,
  bench validation, and floor validation at both 0.05 m/s and 0.1 m/s.
  Coast reduction **97 %** at 0.05 m/s (13.15 mm → 0.44 mm mean) and
  **~91 %** at 0.1 m/s (~52 mm KE-scaled baseline → 4.82 mm). Zero FAULT
  states across all trials. Tags: `pre-counterdrive-code-v2`,
  `counterdrive-enabled-v1`, `counterdrive-bench-validated-v1`,
  `pre-counterdrive-bench-v1`, `counterdrive-floor-validated-v1`,
  `counterdrive-floor-validated-0.1ms-v1`. Full record at
  [validation/records/2026-04-21-counter-drive-floor.md](validation/records/2026-04-21-counter-drive-floor.md).
- **2026-04-21 INA238 motor-rail relocation validated on bench.**
  Multi-input power-selector bypass identified; solved by raising motor
  battery to 6.3 V. Commit `ae32de3`. Unblocked counter-drive session.
- **2026-04-20 (counter-drive session, deferred at Phase 0.5c)**
  `TEST_PWM` bench debug command added (commit `f2b6877`, tag
  `pre-counterdrive-code-v1`). INA238 physically relocated to motor
  rail. Shunt-current readout unresolved at session close — resolved
  2026-04-21 with power-selector finding.
- **2026-04-20** INA238 driver header updated to cite SBOSA20C and
  document DEVICE_ID rev (commit `90ecee5`). Firmware banner bumped
  to 1.3.0 (commit `abba930`). Docs restructured into semantic
  subdirectories with migrated session knowledge (commit `ddbb9a7`).
  Package/firmware READMEs filled in (commit `78c9cfe`). Ops
  hardening commit `c73a297` added opt-in static-IP stanza in
  setup-pi.sh, RUNBOOK pre-flight safety checklist, and
  power-architecture doc.
- **2026-04-20** INA238 driver fix validated (commit `b309625`).
  False-positive root-caused: zero readings observed earlier were
  because the System 1 battery pack was OFF — driver itself is
  correct.
- **2026-04-20** Discovered Pi 5 USB-C and GPIO 5V OR-together through
  internal diodes (measured 0.94 A through INA238 shunt while Pi on
  USB-C). Documented in [power-architecture.md](power-architecture.md).
- **2026-04-19** Pi static IP `192.168.68.101` set via netplan;
  cloud-init network regen disabled.
- **2026-04-19** Pre-wipe kinematic calibration validated — EXCELLENT,
  no calibration changes needed
  ([validation/records/2026-04-19-pre-wipe-calibration.md](validation/records/2026-04-19-pre-wipe-calibration.md)).
- **2026-04-18** DWB rotation-only diagnosis session — full writeup
  at
  [validation/records/2026-04-18-dwb-rotation-session.md](validation/records/2026-04-18-dwb-rotation-session.md).
- **~2026-04** Pi rebuild (fastcdr ABI mismatch trigger) with 5 silent
  bugs fixed — see [hardware/pi-rebuild.md](hardware/pi-rebuild.md).
- **~2026-04** Brake firmware experiment attempted and reverted
  (commits `dc87008` attempted, `dc07888` archived). Forensic at
  [notes/brake-attempt-forensic.md](notes/brake-attempt-forensic.md).
- **2026-04-13** v1.2.0 validation freeze: 33/33 bench tests passed,
  10.8 h soak with 0 crashes / 0 disconnects / 0 checksum failures
  ([validation/records/2026-04-13-record.md](validation/records/2026-04-13-record.md)).

## Phase C Backlog

### Closed (this quarter)

- [x] Pi rebuild + 5 silent bugs fixed
- [x] First motion test (120 mm straight drive at 0.05 m/s)
- [x] Foxglove default layout committed
- [x] Brake firmware attempt + forensic documentation (reverted as ineffective)
- [x] INA238 driver fix (false-positive diagnosis + driver docstring update)
- [x] Pi static IP (`192.168.68.101` via netplan)
- [x] RUNBOOK pre-flight safety + incident response
- [x] `docs/power-architecture.md` with Pi USB-C non-isolation finding
- [x] `scripts/setup-pi.sh` static-IP stanza (opt-in via env var)
- [x] Docs restructure + session knowledge migration
- [x] Package and firmware READMEs
- [x] Firmware version bump convention codified (1.2.0 → 1.3.0)
- [x] **INA238 motor-rail validation** (multi-input power-selector finding)
- [x] **Active counter-drive firmware** — 5-state per-motor FSM with shared
      abort, HW watchdog, encoder-gated termination, 15 % PWM cap. Floor-
      validated at 0.05 m/s (coast 0.44 mm) and 0.1 m/s (coast 4.82 mm).
- [x] **Higher-speed motion test at 0.1 m/s** — Phase 6, 5 trials, clean pass
- [x] **First rotation test** — 2026-04-22. 17 trials at 90°/180°/360°
      in both directions with CD active. Coast 9.58° at 90° CCW (1.11×
      symmetry CW/CCW). Zero faults. Also discovered and fixed the
      STOP→CD bypass bug (commit `a445ffe`).
- [x] **STOP-handler CD bypass bug fix** — `NAVBOT_CMD_STOP` was calling
      `reset_counter_drive_both()`, short-circuiting CD activation when
      the Pi bridge sends STOP on zero cmd_vel. Fix removes the reset
      from STOP; ESTOP/RESET still reset CD.
- [x] **URDF `wheel_offset_y` 0.08 → 0.091 m** (commit `55badc6`).
- [x] **Pi repo sync** — Pi now at HEAD `55badc6`, 12 packages rebuilt.
- [x] **Firmware `wheel_radius` 0.033 → 0.0325 m** — matches URDF
      (commit this session). Verified: mean commanded `ang.z` during
      forward translation collapsed 10× (+0.141 → ±0.014 rad/s), travel
      ratio 70 → 96–98 %.
- [x] **IMU integration end-to-end** — L3G4200D + LSM303DLHC driver
      at 50 Hz, complementary filter `/imu/data`, robot_localization
      EKF fusing `/odom` (x, y, vx) with `/imu/data` (yaw, vyaw),
      Nav2 switched to `/odometry/filtered`. 180° in-place rotation
      is now a clean monotonic sweep, no oscillation.
- [x] **RPP terminal rotate-to-heading oscillation damped** —
      `rotate_to_heading_angular_vel: 0.5 → 0.3`, `max_angular_accel:
      1.5 → 1.0`. Eliminated 50–90° overshoot + back-and-forth
      oscillation; converges monotonically within yaw_goal_tolerance.
- [x] **`wheel_radius` aligned everywhere** — `navbot_base.yaml` was
      still `0.033` while firmware / URDF were `0.0325`. Now `0.0325`
      across firmware, URDF, and bridge config.
- [x] **Magnetometer hard-iron calibration done** (session 10). Gain
      raised to ±4.0 gauss, offsets applied, static rotation tracks
      cleanly. Note: `use_mag: false` in the complementary filter —
      mag fusion during motor activity is unreliable on this mount.
      Infrastructure is one-line re-enable if the IMU relocates.

### Open — High Priority

- [x] **First autonomous navigation goal.** SUCCEEDED 2026-04-22 late
      evening. Three consecutive goals (1.0 m straight, 0.3 m + 90°,
      return to origin) all returned STATUS_SUCCEEDED. Costmap inflation
      reduced to 0.05 m and global_costmap plugins made explicit (Nav2
      default was 0.55 m inflation); FollowPath switched DWB → RPP. See
      [validation/records/2026-04-22-first-nav-goal-success.md](validation/records/2026-04-22-first-nav-goal-success.md).
- [ ] **Higher-speed motion test beyond 0.1 m/s** (0.2, 0.3 m/s). Current
      firmware CD parameters are conservative; may need to raise PWM cap
      or rebalance debounce for higher speeds. Session 11 attempted
      0.20 m/s via dynamic param set — the controller reached
      `lin.x = 0.20` exactly, but full goals TIMEOUT'd because of
      AMCL drift on a sparse map. Completion gated on richer map.
- [ ] **Map quality — richer build drive needed.** Session 11's
      office_lab map was built from one spin-drive-spin-return pass
      (60 s). AMCL has too few distinctive features for reliable
      localization during motion — particle filter drifts during
      rotation, causing xy errors up to 31 cm and yaw errors up to
      82° at goal-check time. Fix: a longer map-build drive that
      traces the full perimeter + spins at 3-4 offset positions.
- [ ] **AMCL yaw drift during motion.** Even with correct initial
      pose, AMCL yaw estimate drifts during motion, particularly
      during end-of-leg rotations. Candidate tunings:
      `max_beams: 60 → 120`, `max_particles: 2000 → 3000`, or
      revisit `laser_likelihood_max_dist`. Partially coupled to
      the map-quality item above — both contribute to the
      ~55° return-to-origin yaw error in session 11.
- [ ] **Higher-precision wheel_separation calibration.** Tonight's "~11°
      short of start" was eyeball-level. A protractor laid at center of
      rotation, or a laser pointer with wall marks, would refine the
      0.182 m estimate to sub-degree precision.

### Open — Medium Priority

- [ ] **`/base/motor_voltage` topic now unreliable.** The GP27 ADC
      divider was physically disconnected during the 2026-04-20 INA238
      relocation. Topic currently reports ~0 V. Either restore the
      divider or deprecate the topic in favour of
      `/power/ina238/bus_voltage_v` (once INA238 motor-rail shunt
      diagnosis is resolved). Supersedes the earlier "C7 bug" item.
- [ ] **Pi-rail INA238 now absent** — the existing chip was relocated
      to the motor rail, so System 1 (Pi compute rail) currently has
      no current monitoring. A second INA238 (or restoration of this
      one after counter-drive work) is the medium-term fix.
- [ ] **Motor-EM interference makes mag fusion unreliable during
      motion** (session 10). With the IMU mounted at 35 mm axle
      height, directly above the motor stack, motor-coil EM fields
      distort the magnetometer reading during active spin. Mag
      fusion added 9.7° per-revolution drift (stdev 10.7°) vs 0.4°
      for encoder-only. Current mitigation: `use_mag: false`.
      Potential fixes, in order of desirability:
      (a) Physical relocation — mount IMU 5+ cm away from motors
          (vertical riser or different chassis position) and re-test.
      (b) Adaptive fusion — disable mag when angular-velocity > X
          rad/s (requires filter replacement; stock
          `imu_complementary_filter` doesn't support this).
      (c) Reduced mag gain — set `gain_mag: 0.01 → 0.001` so mag
          only corrects heading slowly during long static periods.
          Halfway measure; may or may not be enough.
      Full observation:
      [validation/records/2026-04-22-mag-calibration-and-heading-benchmark.md](validation/records/2026-04-22-mag-calibration-and-heading-benchmark.md).
- [ ] **Pi-side repo sync.** Pi is at commit `dc04ba9` (pre-session-8);
      source tree shows old values for firmware `wheel_radius` etc.
      No runtime impact — the Pico binary was flashed from Mac via
      BOOTSEL and is correct; ROS-side configs have been rsync'd
      per-session. But any future `colcon build` on Pi without a
      `git pull` would build stale code. `cd ~/projects/claude-
      navbot && git pull && colcon build` when convenient.
- [ ] **Pre-EKF base bring-up now broken.** `navbot_base.yaml` has
      `publish_tf: false` as the default because the EKF owns
      `odom → base_footprint`. Running base-only (no `ekf_node`)
      leaves the TF chain open. Either expose a launch arg to flip
      the param for bench testing, or document the override as a
      permanent RUNBOOK step.
- [ ] **Pi-side CDRIVE telemetry parsing.** `navbot_serial_bridge`
      currently logs `WARN: unknown serial record: CDRIVE …` for every
      CD telemetry line. Add parsing + publish `/base/counter_drive_state`
      (std_msgs/String JSON-ified) per Phase 1 design plan. Not on safety
      path; forensic convenience.
- [ ] **Nav2 lifecycle auto-activation with LiDAR off.** When LiDAR
      power is off for bench-level testing, `lifecycle_manager_navigation`
      leaves `behavior_server`, `collision_monitor`, and `velocity_smoother`
      inactive (waiting on `/scan` or similar). Manual activation workaround
      is documented in [RUNBOOK.md](RUNBOOK.md). Fix is either (a) adjust
      Nav2 config to not block activation on `/scan` presence, or (b)
      document as permanent operator step for LiDAR-off sessions.
- [ ] **`scripts/launch_nav.sh` `set -u` bug.** The script's `set -euo
      pipefail` clashes with Jazzy's `setup.bash` which references
      `AMENT_TRACE_SETUP_FILES` before checking if it's set. Same
      workaround pattern as `setup-pi.sh` `configure_kernel_tuning()`.
      Fixed in Phase 7 commit.

### Open — Lower Priority

- [ ] **IMU integration (MPU-6050)** — ~10 hr. Adds a 6DOF IMU on top
      of the existing L3GD20+LSM303D cluster. Needed for reliable
      Nav2 rotation handling in real environments.
- [ ] **First navigation goal** — blocked on rotation test.
- [ ] **3D model integration** — awaiting CAD files.
- [ ] **NOPASSWD sudo removal** — needs physical keyboard access to
      the Pi to avoid locking out SSH.

## Known Issues / Gotchas

- **Pi USB-C does not isolate from System 1 battery rail.** Internal
  OR-diodes. Measured 0.94 A through INA238 shunt in this exact
  state (2026-04-20). See
  [power-architecture.md](power-architecture.md#important-usb-c-does-not-isolate-pi-from-this-system).
- **`/base/motor_voltage` reads rail-scaled**, not true battery voltage.
- **Nav2 `drive_on_heading` deceleration params are Kilted/Rolling
  only**, not Jazzy. Do not try to re-add them on Jazzy — reverted at
  commit `8cf3319`.
- **CP210x `-110` on control transfer `0x12`** from LiDAR is usually
  System 2 battery undervoltage, not a USB bus fault.
- **INA238 zero readings with driver healthy** → check System 1
  battery pack switch first. Zero readings do not imply a driver bug
  when the pack is OFF. See
  [hardware/ina238.md](hardware/ina238.md#troubleshooting-matrix).
- **`sllidar_node` holds deleted fd when CP2102 re-enumerates** →
  restart bringup; the node does not error out on its own.

## Decisions Log

- **`base_footprint` chosen as primary 2D nav frame** (commit
  `d7aa26c`). SLAM 33 mm offset was the smoking gun. Full rationale:
  [hardware/pi-rebuild.md](hardware/pi-rebuild.md) bug #3.
- **CycloneDDS chosen over FastDDS.** Required 16 MB kernel socket
  buffers (commit `9178451`) — baked into `setup-pi.sh` so future Pi
  rebuilds inherit the tuning.
- **LiDAR filter pipeline: `+Inf` → NaN, 16 m range cap** (commit
  `4565c25`). Per Slamtec guidance.
- **Foxglove bridge as primary dashboard**; `navbot_web` retained
  for the rosbag capture workflow until Foxglove covers that path.
- **Active counter-drive over regenerative brake** for creep-speed
  stop-on-command — regen brake was validated ineffective below a
  coast threshold that sits above our current motion envelope
  ([notes/brake-attempt-forensic.md](notes/brake-attempt-forensic.md)).
- **Firmware version bumps on every experiment-and-revert cycle**, not
  just net functional changes. Established 2026-04 along with the
  1.2.0 → 1.3.0 bump. See [../firmware/makerpi_rp2040_base/README.md](../firmware/makerpi_rp2040_base/README.md#firmware-version-banner).
- **Opt-in static-IP for setup-pi.sh** (`NAVBOT_CONFIGURE_STATIC_IP=1`)
  rather than default-on, so idempotent re-runs on a working Pi do
  not silently change networking.
- **Docs restructure into semantic subdirectories** (not numbered
  prefixes). Abandoned the partial `04-dashboards` / `06-validation`
  numbering experiment.

## References

- Full docs index: [index.md](index.md)
- Root project README: [../README.md](../README.md)
- Agent startup rules: [../AGENTS.md](../AGENTS.md)
