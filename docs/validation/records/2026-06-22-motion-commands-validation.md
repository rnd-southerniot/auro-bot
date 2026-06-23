# Motion Commands Validation (closed-loop CMD_VEL)

**Date:** 2026-06-22
**Branch:** `navbot-experimental`
**Firmware:** v1.3.0 (`ACK PING 1.3.0`)
**Operator:** Arif — confirmed clear space / wheels free before each run

Hardware validation of the five `/navbot:*` **motion** slash commands (closed-loop
`CMD_VEL`, distinct from the PID-bypassed `TEST_PWM` bench tests). Each ran ~2.5 s
(turn-reverse ~5.2 s) at conservative speed, then auto-`STOP`. All passed with
`STATE CMD_VEL OK` throughout — no `FAULT STALL`, no runaway.

| Command | CMD_VEL (lin, ang) | LEFT Δ | RIGHT Δ | Result |
|---------|--------------------|--------|---------|--------|
| `move-forward`    | +0.10, 0    | +4458 | +4425 | straight, balanced (~0.7%) |
| `move-backward`   | −0.10, 0    | −4429 | −4447 | straight reverse, balanced |
| `soft-turn-left`  | +0.10, +0.4 | +2853 | +5288 | left arc — right (outer) ~1.85× left |
| `soft-turn-right` | +0.10, −0.4 | +5603 | +2841 | right arc — left (outer) ~1.97× right |
| `turn-reverse`    | 0, +0.6     | −5139 | +5143 | in-place CCW, symmetric |

## Notes

- Straight runs are well-balanced (<1% L/R mismatch), confirming the drive-train
  fixes from the 2026-06-16 bring-up hold under closed-loop control.
- Arc differentials are correct (outer wheel travels more) and the two arcs
  mirror each other.
- In-place spin is near-perfectly symmetric (±5140), consistent with the
  validated gyro yaw sign (CCW → +).
- `turn-reverse` angle is open-loop/time-based; ~180° is approximate and varies
  with battery/load — tune `SECS` in the command if needed.
- Power note unchanged: RP2040 `motor_v` still reads false ~0 (GP27 sense wire
  open); does not affect driving.

See [../../operations/bench-test-commands.md](../../operations/bench-test-commands.md)
for the command reference and the earlier per-motor bench tests
([2026-06-16-home-reassembly-bringup.md](2026-06-16-home-reassembly-bringup.md)).
