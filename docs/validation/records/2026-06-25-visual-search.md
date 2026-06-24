# Visual search — `look_around` + `turn` (camera search)

**Date:** 2026-06-25
**Scope:** New voice-brain capability — "search / find / look for X" makes the
robot spin a full 360° in place, photographing each heading, then identify the
target in the frames and turn to face it.
**Stack:** robot `navbot-pi`, autostart appliance; brain = headless Claude Code
(`claude_brain.py`) over the `navbotctl` → control-server (`:8077`) path.
**Verdict:** BENCH-VALIDATED on blocks; on-floor find-the-object pending.

## Design

The "finding" is the brain's vision (it `Read`s JPEGs); the new tools provide a
reliable motion + capture primitive:

- **`look_around [steps=8] [target]`** (`RobotTools.look_around`) — rotates in
  place through 360° in N steps (default 8 × 45°), grabbing one **stationary**
  frame per heading (sharper than shooting mid-rotation), and returns the
  `heading → JPEG path` list. Does not judge content. Ends ~back at the start
  heading (N × step == 360°).
- **`turn <degrees>`** (`RobotTools.turn`) — rotate in place by a relative angle
  (+ = left/CCW), clamped ±360°. Used to face a found target.
- Both share `_spin()` (angular-only, ~0.5 rad/s). They are **drive-mode gated**
  and **e-stop checked** like `drive`, and **abortable by the "stop" word**
  (checked each step), but are **exempt from the 6 s linear motion budget** —
  in-place rotation is low-risk and a 360° sweep needs ~12 s. Bounded instead by
  the requested angle (≤ one turn).
- Camera frames get a unique `tag` suffix (`scanNN`) so rapid grabs within one
  second don't collide on the second-resolution filename.

Brain orchestration (prompt in `claude_brain.py`): on "find/look for/where is X"
→ `drive-mode on` → `look-around --target "X"` → `Read` every frame → if found,
`turn --degrees <that heading>` to face it and announce; else say it looked all
around and couldn't find it.

## Tests

- **Mock smoke test** (gateway, no hardware): drive-mode gating, 8-frame sweep
  with correct headings/tags, budget left untouched, mid-sweep abort stops
  cleanly, `turn` gating/clamp/budget-exemption, dispatch wiring — all passed.
- **Bench (robot on blocks):** `navbotctl look-around --target "chair"` returned
  all 8 headings `0…315°` with valid 320×240 JPEGs; `turn 90` succeeded. Frames
  look identical because the robot doesn't physically rotate on blocks.
- **CLI timeout fix:** `navbotctl call()` had a hardcoded 10 s timeout < the ~12 s
  sweep, so the first run reported "control server unreachable" though the sweep
  completed. `call()` now takes a `timeout`; `look-around` uses 90 s, `turn` 30 s.

## Follow-ups

- **On-floor voice validation:** "Jarvis, look for my <object>" with the robot on
  the floor, to confirm distinct per-heading views + correct turn-to-face.
- **SDK-path parity:** `agent.py` (the in-process Anthropic-SDK brain, not the
  running path) does not yet expose `look_around`/`turn`.
- Open-loop rotation: headings are approximate (no odom closed-loop). Fine for
  "face the object" but not precise; revisit if accuracy matters.
