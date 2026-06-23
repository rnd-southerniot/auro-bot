# claude-navbot — Project Instructions

Differential-drive robot: **Raspberry Pi 5 + Maker Pi RP2040**, ROS 2 Jazzy,
RPLIDAR C1, `slam_toolbox` + Nav2, Pi-side IMU + INA238. Active development on
branch **`navbot-experimental`** (the `main` branch is the older v1.2.0
validation freeze).

## Hardware quick reference

- **RP2040 base** (fw v1.3.0): motors LEFT=M2 (GP10/11, enc GP2/3, swap_dir
  false) / RIGHT=M1 (GP8/9, enc GP4/5, swap_dir true); ESTOP GP20; buzzer
  GP22; ADC motor_v GP27 / lidar_v GP28. Serial protocol is line-based at
  115200 (`PING`, `CMD_VEL <lin> <ang>`, `TEST_PWM <l> <r>`, `STOP`, `RESET`,
  `DIAG`; telemetry `ODOM/STATE/VBAT/CDRIVE`). Port:
  `/dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00`.
- **IMU** (Pi I²C-1): L3G4200D gyro `0x69`, LSM303DLHC accel `0x19` / mag
  `0x1E`. Driver mode `x_forward_flipped` (board mounted flipped 180° about
  X). INA238 power monitor at `0x40` (on the **motor rail** since the
  2026-06 home reassembly).
- **Power (home, 2026-06):** 3S LiPo + 5V converter feeds the Pi only;
  INA238/motor rail is separate (~6–7 V, likely 2S); LiDAR separately
  powered. Old undervoltage blocker retired.

## Access

- Pi: `ssh navbot-pi` (→ `arif@192.168.68.126`, key
  `id_ed25519_siot_lab_arif`); repo at `~/projects/claude-navbot`, ROS 2
  Jazzy workspace built at `ros2_ws/install`.
- Single source of truth for status: [docs/project-status.md](docs/project-status.md).

## Working rules (this project)

- **Hardware debugging: one minimal change at a time, verify before the
  next.** Never stack conflicting fixes (e.g. polarity + channel swaps).
- Motors: never command motion without confirming wheels are free; prefer
  `TEST_PWM` (PID-bypassed, auto-stops) for bench checks.
- Default to minimal, scoped changes; don't refactor beyond the request.
- Bench self-tests: the `/navbot:*` slash commands
  ([docs/operations/bench-test-commands.md](docs/operations/bench-test-commands.md)).
- Operating this robot as Claude Code: start at
  [docs/operations/claude-operator.md](docs/operations/claude-operator.md)
  (identity, tool boundary, control surface, safety). Quick safe commands:
  `/navbot:preflight`, `/navbot:status` (read-only), `/navbot:stop` (halt).
  Only one owner of the Pico serial port at a time — raw `/navbot:*` serial
  commands conflict with a running ROS bringup; use the `navbot_web` API then.

## MCP knowledge store (SIoT gateway)

This project's **skills, memory, and key docs are mirrored to the SIoT MCP
gateway** (`10.10.8.113:8000`) as the `navbot-knowledge` upstream server
(prefix `nav`), reading from `/home/mcp/knowledge/claude-navbot/` on the VM.
Future agents can query it via the gateway meta-tools
(`discover_upstream_tools(server_name="navbot-knowledge")`,
`call_upstream_tool(...)`) without local files. The mirror is refreshed by
[scripts/sync_knowledge_to_mcp.sh](scripts/sync_knowledge_to_mcp.sh) (run
automatically by a Claude Code Stop hook).
