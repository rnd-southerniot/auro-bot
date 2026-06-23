# Attempted brake patch — 2026-04-20

Speed-gated regenerative brake for the MX1508 H-bridge was tried and
found **INEFFECTIVE** at creep speeds. The firmware change is archived
here for future reference, not committed to the build.

## Hypothesis that was tested

On `cmd_vel = 0`, the firmware previously put the MX1508 into COAST
(IN1 = IN2 = LOW). Wheels freewheeled through the 30:1 gearbox until
BEMF decayed — measured first-motion session 2026-04-19 showed
~17 mm of coast past the action-reported stop point.

Proposed fix: on `cmd_vel = 0`, enter MX1508 BRAKE (IN1 = IN2 = HIGH,
shorting the winding for regenerative brake). Speed-gate at 0.15 m/s
so brake only engages once wheel speed is low enough that brake
current stays within the MX1508's 1 A/channel limit. Above threshold,
coast and let BEMF decay naturally, then next control tick engages
brake once under threshold.

## What the patch does

- Adds `BRAKE_SPEED_THRESHOLD_MPS = 0.15f` to `config.h`.
- Adds static `wheel_motor_brake()` to `wheel.c` — sets both PWM
  channels to `MOTOR_PWM_WRAP` (effectively 99.9 % HIGH on both
  `pin_fwd` and `pin_rev`).
- Adds static `wheel_apply_idle_output()` — checks safety (coasts
  on fault), reads `w->speed_filtered`, chooses brake vs coast based
  on the threshold.
- Calls `wheel_apply_idle_output()` from both `wheel_stop()` (on
  explicit stop) and `wheel_tick()` (every control tick while in
  `WMODE_IDLE`, so the brake engages automatically once a coasting
  wheel decays below threshold).
- Normal `WMODE_SPEED` forward/reverse drive path: untouched.
- Safety faults: always force coast (preserves ESTOP semantics —
  wheels free for manual push).

Zero impact on normal drive, zero impact on cmd_vel parsing, zero
impact on encoder/odometry layer. Minimal surface change: two files,
~40 added lines.

## Measured result — BRAKE INEFFECTIVE

Test command identical to first-motion session:
`drive_on_heading target.x = 0.10 m, speed = 0.05 m/s`.

| | Session 1 (pre-brake) | Run 1 (brake) | Run 2 (brake) |
|---|---:|---:|---:|
| Commanded | 100 mm | 100 mm | 100 mm |
| Action feedback done | 102.6 mm | 101.3 mm | 101.7 mm |
| Odom Δ | 119.3 mm | 118.4 mm | 119.9 mm |
| Physical tape | 120 mm | 120 mm | 120 mm |
| Overshoot (odom − feedback) | **16.7 mm** | **17.1 mm** | **18.2 mm** |

Post-brake overshoots are statistically unchanged (actually marginally
larger, within measurement noise) vs the pre-brake baseline. No
audible brake "thunk" was detected with the ceiling fan off and the
user's ear close to the chassis.

Firmware health stayed clean through both runs: `controller_state =
IDLE OK`, `checksum_failures = 0`, `reconnect_count = 1`,
`motor_voltage ≈ 5.13 V` with no sag during the stop. The patch
didn't break anything — it just doesn't produce useful braking at
0.05 m/s.

## Why it failed at creep speed

Regenerative brake current through a shorted motor winding is
BEMF / R_winding. For our MG513-class motors at 0.05 m/s wheel speed:

- BEMF ≈ 100–300 mV (estimate; a small fraction of rated BEMF).
- Winding resistance ≈ 0.5–1 Ω.
- Brake current ≈ 100–600 mA, well below the 1 A/channel MX1508 limit.
- Motor shaft torque = Kt × I_brake ≈ a few mN·m.
- After 30:1 gearbox reduction the wheel sees a somewhat larger
  braking torque, but it's still tiny versus the combined
  gearbox/rotor inertia at this low speed.

The fundamental problem is that regenerative brake is
BEMF-proportional, and BEMF is speed-proportional — so at the very
speed where you most want active deceleration (during a creep-speed
stop), the regenerative effect is weakest. Textbook limitation of
resistive-short regen braking, not a patch bug.

## What would work instead

**Active counter-driving.** Instead of shorting the winding, drive
the H-bridge in reverse with a PWM duty cycle that produces a
closed-loop-controlled deceleration. Sequence:

1. On `cmd_vel = 0` (or drive_on_heading done), capture
   `w->speed_filtered` as the initial velocity to decelerate.
2. Run a short deceleration profile at the opposite-direction PWM
   channel, proportional to |speed_filtered|, for a bounded number
   of control ticks (say 5–20 ms envelope).
3. Monitor encoder delta each tick; when encoder stops ticking for
   ≥ 2 consecutive ticks, transition to true stop (both channels 0,
   WMODE_IDLE).

Safety: the counter-drive pulse is bounded in time and amplitude,
and a safety fault would immediately kill it via existing
`safety_is_faulted()` coast override. Risk: overshooting into
reverse if the decel profile is too aggressive. Recommend starting
with a 50 % duty counter-pulse for ≤ 20 ms, tuning up from there.

Alternative: firmware-side closed-loop velocity control with a zero
setpoint and aggressive integral. The PID already runs, but the
`STOP_SETPOINT_CPS_DEADBAND` (20 cps) short-circuits it below a
threshold. Raising or removing the deadband may let the PID itself
actively brake, at the cost of possibly chattering around zero at
rest. Would need encoder noise characterization first.

## Artifact

The full diff is in `attempted_brake_patch.patch` next to this
README. To re-apply in a future session:

```bash
cd firmware/makerpi_rp2040_base
git apply docs/notes/attempted_brake_patch.patch
```

The patch still compiles cleanly against the current source tree as
of the commit that archives it — revisit in a future active-brake
iteration as a starting structure before switching from
regenerative-short to counter-drive logic.

## Related Phase C items surfaced during this session

- **Right wheel travels ~5 mm less than left wheel** over a 120 mm
  straight command (user observation). Matches the small right-turn
  yaw drift in odom (-0.34° at end of run 2). Not an encoder CPR
  issue (LEFT 3943 vs RIGHT 3946, 0.08 % difference). Likely wheel
  diameter mismatch, differential rolling resistance, or per-motor
  PID calibration asymmetry. Separate investigation.
- **Firmware `LEFT_WHEEL_RADIUS_M = RIGHT_WHEEL_RADIUS_M = 0.033`**
  still uses the pre-correction wheel radius. URDF was updated to
  `0.0325` earlier this session. Odom scale is ~1.5 % high as a
  result. Fix by updating both firmware constants to `0.0325f`.
  Coordinate with next firmware flash.
