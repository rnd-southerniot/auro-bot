# auro-bot — Project Instructions

**auro-bot** is a **talk-to-it, sees-you mobile robot**: a differential-drive
base you command by voice, that answers out loud and can look at the room. It is
the navbot base (Raspberry Pi 5 + Maker Pi RP2040, ROS 2 Jazzy, RPLIDAR C1, IMU)
plus three things layered on top:

- a hands-free **voice front-end** (ESP32-S3 "buddy": wake word, mic, speaker, face),
- a **Claude brain** that turns speech into safe, gated robot actions, and
- a **XIAO ESP32-S3 Sense Wi-Fi camera** that gives the brain eyes.

Active development is on **`main`** (linear phase commits `P0…P7`). This repo on
*this host* is a **staging copy** — see "Access" below.

## Subsystem map

| Subsystem | Where | What |
|---|---|---|
| Drive base (RP2040 fw 1.3.0) | `firmware/makerpi_rp2040_base/` | motors, encoders, PID, e-stop, serial protocol |
| ROS 2 base + sensors | `ros2_ws/src/navbot_*` | serial bridge, odom, LiDAR, IMU/EKF, SLAM/Nav2, web API |
| Voice buddy (ESP32-S3) | `firmware/esp32s3_voice_buddy/` | WakeNet "Jarvis" + offline "stop", mic/speaker, face; USB-serial to Pi |
| Voice brain | `ros2_ws/src/navbot_voice{,_io}/` | Whisper STT → Claude → Piper TTS; gated teleop via `/api/*` |
| Camera (XIAO Sense) | `firmware/xiao_esp32s3_sense_cam/` | Wi-Fi JPEG camera; the brain's `look()` |
| Autostart | `ops/systemd/`, `scripts/install_autostart.sh` | boot the whole appliance via systemd |

## Phase status (voice subsystem)

P0–P3 and P5 teleop are **hardware-validated**; P6 camera validated this June;
**P7 autostart is boot-validated on the robot (2026-06-24)** — it powers on into
the appliance (base+web+voice+camera). As of **2026-06-25** the LiDAR `/scan` is
**healthy again** (720 beams; the earlier timeout was a flat LiDAR pack, now
charged), and two voice changes landed: a cumulative **≤6 s/episode motion
budget** (fixes drive-command chaining) and **visual search** (`look_around` +
`turn` — spin 360°, find a named object, face it). Both bench-validated on
blocks; on-floor voice validation pending.

- **P0–P1** brain skeleton + buddy firmware (link validated)
- **P2** on-device wake word + AFE + offline "stop" (esp-sr)
- **P3** Pi STT + TTS conversational loop (faster-whisper + Piper)
- **P5** LLM tool-use + gated voice teleop (headless Claude Code, subscription auth);
  validated on blocks 2026-06-24 ("Jarvis, drive forward 2 s" → odom +0.18 m, auto-stop)
- **P6** perception — XIAO Sense Wi-Fi camera + `look()`/`describe_scene()` in both
  brains; **visual search** (`look_around` 360° photo sweep + `turn`-to-face,
  2026-06-25) in the Claude Code brain
- **P7** autostart — systemd stack (base+LiDAR+IMU/EKF → web → voice); **boots
  hands-free on the robot, validated 2026-06-24** ([record](docs/validation/records/2026-06-24-autostart-validation.md))

> ⚠️ **Known safety gap (P5→fix):** the on-device "stop" word only fires inside
> the firmware's ~5 s post-wake MultiNet window — a "stop" shouted *during* a
> later Claude-initiated drive isn't heard. Motion stays bounded by the clamps
> (≤3 s, ≤0.12 m/s per call) + a cumulative **≤6 s/episode** motion budget
> + the 0.5 s cmd-vel timeout. The hardware **e-stop** always works.
>
> The per-episode budget was added 2026-06-25 after a live test showed the brain
> would satisfy "drive for 40 seconds" by *chaining* ~11 clamped 3 s drives
> (~3.9 m) — the per-call clamp alone did **not** bound total motion. `SafetyGate`
> now caps cumulative commanded drive-time per wake-episode
> ([record](docs/validation/records/2026-06-25-voice-motion-budget.md)).

## Hardware quick reference

- **RP2040 base** (fw 1.3.0): LEFT=M2 (GP10/11, enc GP2/3, swap_dir false) /
  RIGHT=M1 (GP8/9, enc GP4/5, swap_dir true); ESTOP GP20; line protocol @115200
  (`PING`, `CMD_VEL`, `TEST_PWM`, `STOP`, `RESET`, `DIAG`). Port:
  `/dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00`.
- **Buddy** (ESP32-S3-WROOM): USB-serial (CH343→UART0) to the Pi on `ttyACM1`,
  framed audio protocol (`firmware/esp32s3_voice_buddy/PROTOCOL.md`). "Jarvis" wake.
- **Camera** (XIAO ESP32-S3 Sense): **Wi-Fi only**, not wired to the Pi. Serves
  `:80/snapshot` (JPEG), `:81/stream` (MJPEG), `:80/status`. DHCP-reserved at
  `192.168.68.110` on AP "Auro" (MAC `8C:BF:EA:8E:65:04`).
- **IMU** (Pi I²C-1): L3G4200D `0x69`, LSM303DLHC accel `0x19`/mag `0x1E`, mode
  `x_forward_flipped`. INA238 power monitor `0x40` on the motor rail.

## Access

- **This host** = the **gateway/staging Pi** (`~/projects/auro-bot`). Edit, build
  firmware, and commit here. It is **not** the robot.
- **The robot** = `ssh navbot-pi` (→ `arif@192.168.68.126`, Ubuntu 24.04 / ROS 2
  Jazzy). The voice/camera stack runs here. Don't assume robot paths exist on this
  host (the external sllidar overlay is `/home/arif/ros2_ws/install`).
- The camera (`192.168.68.110`) is reachable from this host over Wi-Fi.

## Working rules (this project)

- **Hardware debugging: one minimal change at a time, verify before the next.**
  Never command motion without confirming wheels are free; prefer `TEST_PWM`.
- **Distinguish validated-now from pending** in everything you write; don't
  overclaim. Preserve confirmed runtime facts in repo docs, not just chat.
- The brain reaches the base **only** through `navbot_web` `/api/*` — never the
  Pico serial port (single-owner). Only one owner of the Pico serial at a time.
- Default to minimal, scoped changes; don't refactor beyond the request.
- Single source of truth for base state: [docs/project-status.md](docs/project-status.md).
  Voice/camera/autostart ops: [docs/operations/voice-appliance.md](docs/operations/voice-appliance.md),
  [docs/operations/autostart.md](docs/operations/autostart.md). End-user
  voice/camera guide: [docs/guides/talking-to-auro.md](docs/guides/talking-to-auro.md).
- Operator bench self-tests: the `/navbot:*` slash commands
  ([docs/operations/bench-test-commands.md](docs/operations/bench-test-commands.md)).
  Quick safe ones: `/navbot:preflight`, `/navbot:status`, `/navbot:stop`,
  `/navbot:camera-test`, `/navbot:voice-status`.

## MCP knowledge store (SIoT gateway)

This project's skills, memory, and key docs are mirrored to the SIoT MCP gateway
(`10.10.8.113:8000`) as the `navbot-knowledge` upstream (prefix `nav`), from
`/home/mcp/knowledge/claude-navbot/` on the VM. Future agents can query it via the
gateway meta-tools (`discover_upstream_tools`, `call_upstream_tool`). Refreshed by
[scripts/sync_knowledge_to_mcp.sh](scripts/sync_knowledge_to_mcp.sh) (a Stop hook).
