# Operating the Navbot as Claude Code

This is the entry point for an agent (or operator driving via Claude Code)
that needs to work with the physical robot. It does not replace any existing
doc — it ties them together and states the **tool boundary**. Read it
alongside the startup rule in [../../AGENTS.md](../../AGENTS.md).

## Identity

You are operating a **real** Raspberry Pi 5 + Maker Pi RP2040 differential-
drive robot (ROS 2 Jazzy, RPLIDAR C1, IMU, INA238). Motion moves real
hardware. There is no simulator in this path. Ground every claim in
[../project-status.md](../project-status.md) and
[../validation/README.md](../validation/README.md); never overclaim autonomy
(Nav2 is partially validated — AMCL drift and a fresh home SLAM map are open
items, and the `office_lab*` maps are stale after the 2026-06 home move).

## Tool boundary — what Claude drives, and how

Claude does **not** touch motors directly. The safety-critical loop lives in
two places that already exist and are validated:

- **RP2040 firmware** owns closed-loop wheel control, estop, stall detection,
  and a 0.5 s command-timeout — if `CMD_VEL` streaming pauses, the base stops
  on its own. See
  [firmware/.../navbot_protocol.h](../../firmware/makerpi_rp2040_base/include/navbot_protocol.h).
- **`navbot_base/serial_bridge`** (ROS 2) owns the serial port and
  odometry/TF when the stack is running.

Claude reaches the robot through exactly two sanctioned surfaces:

| Surface | When | How |
|---|---|---|
| `/navbot:*` slash commands | Bench / direct serial, stack **down** | SSH `navbot-pi` → line protocol on `/dev/serial/by-id/...Pico...` |
| `navbot_web` HTTP API | Stack **up** | `GET /api/status`, `POST /api/stop`, `POST /api/cmd_vel` (see [web-console.md](web-console.md)) |

**Hard rule — one owner of the Pico serial port at a time.** The `/navbot:*`
commands open `/dev/serial/by-id/...Pico...` directly. **Do not run them while
a ROS bringup / `serial_bridge` is holding that port** — the two will contend
and corrupt control. When the stack is up, use the `navbot_web` API instead.
`/navbot:preflight` reports which state you are in.

## Safety model — firmware-enforced, not advisory

This robot's safety is enforced in **firmware**, not by prompt instructions:

- A **0.5 s command-timeout** halts the base if command streaming stops.
- **Estop, stall detection, and run-timeout** are latched faults the firmware
  raises on its own; `RESET` clears them.
- `TEST_PWM` (used by the single-wheel bench commands) is **PID-bypassed and
  auto-stops after 1 s**.
- The motion commands stream `CMD_VEL` at 10 Hz specifically to beat the
  firmware timeout, and send an explicit `STOP` at the end.

Preserve this model. Do **not** introduce an advisory/trust-the-model control
path (e.g. a Python driver with an unbounded "run until told to stop" mode):
that would remove the firmware watchdog and preemption guarantees the current
design provides.

## What Claude MUST do

- Run [/navbot:preflight](../../.claude/commands/navbot/preflight.md) at the
  start of a hands-on session.
- For any command that moves the robot, confirm clear space (or wheels on
  blocks) and wait for an explicit "yes" before driving — the motion commands
  already enforce this.
- Keep [/navbot:stop](../../.claude/commands/navbot/stop.md) ready as the
  software emergency stop; physical estop / motor-rail power-off is the
  backstop (see [../RUNBOOK.md](../RUNBOOK.md#incident-response)).
- Make one minimal hardware change at a time; verify before the next. Never
  stack conflicting fixes (e.g. polarity + channel swaps together).

## What Claude MUST NOT do

- Re-implement motor or serial control in Python "for convenience" — the
  firmware and `serial_bridge` are the validated path. Do not add a parallel
  driver or a new control stack.
- Command `CMD_VEL` motion with the ROS stack up **and** a raw `/navbot:*`
  serial command at the same time (serial-port contention).
- Claim autonomy / Nav2 readiness beyond what
  [../project-status.md](../project-status.md) records.

## Control surface — slash command index

Full catalog, PASS criteria, and troubleshooting:
[bench-test-commands.md](bench-test-commands.md). Quick map:

- **Read-only:** `/navbot:status`, `/navbot:preflight`, `/navbot:motor-voltage`,
  `/navbot:lidar-voltage`, `/navbot:lidar-health`, `/navbot:gyro-test`
- **Safety:** `/navbot:stop`
- **Moves a single wheel (on blocks):**
  `/navbot:motor-{left,right}-{fwd,rev}`
- **Drives the robot (closed-loop):** `/navbot:move-forward`,
  `/navbot:move-backward`, `/navbot:soft-turn-left`, `/navbot:soft-turn-right`,
  `/navbot:turn-reverse`

> Note: `/navbot:status`, `/navbot:preflight`, and `/navbot:stop` are proposed
> additions and may not exist yet — check `.claude/commands/navbot/` for what
> is actually present in this checkout.

## Startup flow

1. `/navbot:preflight` — confirm reachability, devices, and stack state.
2. If the ROS stack is needed, follow
   [RUNBOOK.md → Startup Procedure](../RUNBOOK.md#startup-procedure).
3. Bench checks with wheels free: `/navbot:motor-*`, `/navbot:gyro-test`.
4. Floor motion only after confirming clear space: `/navbot:move-*`.
5. `/navbot:stop` (or web-console STOP when the stack owns the port) to halt at
   any time.
