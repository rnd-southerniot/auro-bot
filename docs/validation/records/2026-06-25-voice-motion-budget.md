# Voice-drive cumulative motion budget — finding + fix

**Date:** 2026-06-25
**Scope:** P5 gated voice teleop — a single voice command could drive far beyond
the documented ≤3 s clamp by chaining drives. Added a per-episode motion budget.
**Stack:** robot `navbot-pi`, autostart appliance (P7) running
`navbot-bringup`/`web`/`voice`; brain = headless Claude Code (`claude_brain.py`).
LiDAR + camera both recovered earlier this session.
**Verdict:** FIXED + LIVE-VALIDATED on blocks.

## Finding

While checking voice-control driving (robot on blocks), the command
*"Jarvis, drive robot for 40 seconds"* produced **~3.93 m of wheel-spin
(~33 s at the 0.12 m/s clamp)**, and the brain replied *"I drove forward at a
gentle pace for the full forty seconds and then stopped safely."*

Root cause traced in source:

- **Per-call clamp works.** `SafetyGate.clamp()` caps `duration→≤3 s`,
  `|linear|≤0.12`; `RobotTools.drive()` loops `cmd_vel` only until that ≤3 s
  deadline. One call can never exceed 3 s.
- **But the brain chains calls.** The headless-Claude brain emits multiple
  `drive` tool-calls (the `claude` CLI can issue many `tool_use` blocks per turn,
  up to `--max-turns 8`), so "40 s" became ~11 back-to-back clamped 3 s drives.
- **Net effect:** the per-command `≤3 s` bound that CLAUDE.md's safety model
  relied on did **not** bound total motion per utterance. Speed stayed clamped
  (0.12 m/s), so on the floor this is a multi-metre creep, not a high-speed bolt —
  but it is well outside the intended envelope and compounds the known
  windowed-"stop" gap (a "stop" shouted mid-chain is not heard).

Also observed (separate, minor, **not fixed here**): `navbot_serial_bridge` logs
`unknown serial record: CDRIVE …` — the RP2040 1.3.0 firmware emits `CDRIVE`
counter-drive telemetry (`firmware/.../telemetry.c:85`) the current bridge parser
doesn't recognize (`serial_bridge.py:328`). Cosmetic log spam + dropped telemetry;
firmware↔bridge protocol drift. Filed as a follow-up.

## Fix

`SafetyGate` gains a cumulative per-episode motion budget
(`ros2_ws/src/navbot_voice/navbot_voice/safety.py`):

- `reserve_motion(duration) -> (granted_s, reason)` — grants drive-time against a
  `MAX_EPISODE_S` budget (default **6.0 s**, env `NAVBOT_MAX_EPISODE_S`). Drives
  chained within one wake-episode share the budget; a quiet gap of
  `EPISODE_IDLE_S` (default 10 s, env `NAVBOT_EPISODE_IDLE_S`) starts a fresh one.
  Budget also resets on `halt()` and any `set_drive_mode()` toggle. Reserving up
  front (not billing actual elapsed) errs toward stopping sooner.
- Both drive paths call it after `clamp()`: `RobotTools.drive()` (the running
  control-server path) and `agent.py._drive()` (the SDK path). On a zero grant
  they return `refused to move: reached the motion limit …`.
- Brain prompts (`agent.py`, `claude_brain.py`) updated to tell the LLM there is a
  ~6 s cumulative cap and **not** to chain drives for long asks — make one short
  move and say so.

Unit test of the budget logic (stdlib-only, run on the gateway): chained 3 s
drives cap at 6 s total; idle gap / `halt()` / `set_drive_mode()` reset; partial
grant when budget nearly spent — all assertions passed.

## Live validation (robot on blocks)

Deployed: edited 4 source files → `colcon build --packages-select navbot_voice`
→ `systemctl restart navbot-voice`. Re-ran the same command.

| | Before | After |
|---|---|---|
| Heard | "drive robot for 40 seconds" | "drive …40 seconds" |
| Reply | "…for the **full forty seconds** and then stopped safely." | "I rolled forward for **two seconds**, but I keep every drive short for safety so I **can't do a full forty**." |
| Odom Δ | **+3.93 m** | **+0.07 m** (one ~2 s move) |

Both defense layers confirmed: prompt layer (brain no longer chains, honest
refusal) live; SafetyGate budget layer by unit test.

## Deploy note

The robot's `~/projects/auro-bot` carries `navbot_voice` as **untracked**
out-of-band-deployed files (repo HEAD `248d88a`, older than staging). Before
overwriting, the four files were diffed against staging HEAD and confirmed
identical, then replaced and rebuilt. `navbot_voice` is colcon-built **without**
`--symlink-install` (build/ holds copies) — a rebuild is required after editing
source; restarting the service alone is not enough.

## Follow-ups

- `CDRIVE` serial-record parser gap in `navbot_serial_bridge` (log spam).
- Close the windowed-"stop" gap itself (always-on stop detector) — still open.
- Tune `NAVBOT_MAX_EPISODE_S` if voice-driven SLAM mapping feels too restrictive.
