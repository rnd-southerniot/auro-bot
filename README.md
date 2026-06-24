# auro-bot

A **voice-controlled, camera-equipped mobile robot**. Say "Jarvis," talk to it,
and it listens, thinks (Claude), answers out loud, looks at the room, and drives —
all under a hard safety layer. Built on a Raspberry Pi 5 + Maker Pi RP2040
differential-drive base running ROS 2 Jazzy, with RPLIDAR C1, an IMU, an ESP32-S3
voice "buddy," and a XIAO ESP32-S3 Sense Wi-Fi camera.

> **Not a tutorial scaffold and not a fake-finished product.** Real firmware, a
> real ROS 2 stack, a working voice loop validated on hardware, and an honest
> record of what is and isn't validated yet (see [Status](#status)).

## What it does

- **Hears you** — an ESP32-S3 buddy runs an on-device "Jarvis" wake word and an
  offline "stop"/"halt" word (esp-sr), streams your speech to the Pi.
- **Understands** — faster-whisper transcribes; a **Claude brain** decides what to
  do with a small, safety-gated tool set.
- **Acts** — drives the base (gated, clamped, abortable), reports status, sets the
  buddy's animated face.
- **Speaks** — Piper TTS, played back on the buddy's speaker.
- **Sees** — a XIAO ESP32-S3 Sense Wi-Fi camera; the brain's `look()` grabs a
  frame and describes the scene.
- **Boots hands-free** — a systemd stack brings the whole appliance up on power-on.

## Architecture at a glance

```
        speech                       /api/* (gated)            USB-serial
  you ──────────▶ ESP32-S3 buddy ───────────────▶  Pi 5 brain ──────────▶ RP2040 base
        TTS  ◀────  (wake/STT/TTS,   ◀───────────   (Whisper +              (motors,
              face)   mic/speaker)      face/audio    Claude + Piper)        encoders, PID)
                                                          │
                                              HTTP /snapshot │ (Wi-Fi)
                                                          ▼
                                              XIAO ESP32-S3 Sense camera
```

Two control planes, deliberately separated:
- **Motion** flows brain → `navbot_web` HTTP `/api/*` → ROS → the Pico. The brain
  **never** touches the Pico serial port directly (single-owner rule).
- **Camera** is a Wi-Fi appliance: the Pi just `GET`s a JPEG. No CSI ribbon.

## Repo layout

```text
firmware/
  makerpi_rp2040_base/      RP2040 drive firmware (Pico SDK)
  esp32s3_voice_buddy/      voice front-end firmware (ESP-IDF)
  xiao_esp32s3_sense_cam/   Wi-Fi camera firmware (ESP-IDF, vendored)
ros2_ws/src/
  navbot_base/ _bringup/ _lidar/ _imu/ _localization/ _slam/ _navigation/  base + nav
  navbot_web/               HTTP control surface (/api/cmd_vel,/stop,/status)
  navbot_voice/             the brain: Claude tool-use, SafetyGate, vision
  navbot_voice_io/          buddy serial link + conversational loop (buddy_brain)
  navbot_camera/            XIAO camera → ROS (/camera/grab_frame, /camera/status)
ops/systemd/                autostart units + env template (P7)
scripts/                    build/launch/install helpers, navbotctl, navbot_service.sh
docs/                       architecture, runbook, operations, validation, status
```

## Quickstart (on the robot, `ssh navbot-pi`)

```bash
# 1. Build the workspace
./scripts/build_ros2_ws.sh

# 2a. Manual bring-up (base + LiDAR + IMU, then the web API, then the voice loop)
ros2 launch navbot_bringup imu_localization.launch.py
./scripts/launch_web_console.sh
python3 -m navbot_voice_io.buddy_brain     # owns the buddy on ttyACM1

# 2b. ...or install hands-free autostart (does all of the above on every boot)
sudo ./scripts/install_autostart.sh --now
```

Then say **"Jarvis, what do you see?"** or **"Jarvis, drive forward two seconds."**
Drive mode is **off** until you ask to move. See
[docs/operations/voice-appliance.md](docs/operations/voice-appliance.md) for the
full operating guide.

## Status

| Phase | Subsystem | State |
|---|---|---|
| P0–P1 | brain skeleton + buddy firmware | ✅ link validated |
| P2 | wake word + AFE + offline "stop" | ✅ on hardware |
| P3 | STT + TTS conversational loop | ✅ on hardware |
| P5 | LLM tool-use + gated voice teleop | ✅ on blocks 2026-06-24 (odom +0.18 m, auto-stop) |
| P6 | XIAO Sense camera + vision | ✅ live grab + status validated 2026-06-24 |
| P7 | systemd autostart | ⏳ authored + syntax-checked; **robot enable/boot test pending** |

**Base** (drive/odom/LiDAR/IMU/SLAM): validated through the v1.2.0 freeze and the
2026-06 home re-assembly bring-up — details in
[docs/project-status.md](docs/project-status.md).

**Honest gaps:** Nav2/AMCL needs a fresh home SLAM map (the `office_lab` maps are
stale after the home move), so `navbot-nav` ships **disabled**. The on-device
"stop" word only listens in the ~5 s window after a wake (see the safety note in
[CLAUDE.md](CLAUDE.md)). The hardware e-stop always works.

## Safety model

Three layers, none of which the brain can bypass:
1. **SafetyGate** (in the brain) — drive mode OFF by default; clamps
   `|linear|≤0.12 m/s`, `|angular|≤0.6 rad/s`, `duration≤3 s`; abortable; refuses
   on e-stop / low motor voltage.
2. **Command-timeout watchdog** — web 0.35 s → serial_bridge 0.5 s → RP2040 0.5 s.
   A drive must be actively re-posted or the wheels stop.
3. **Hardware e-stop + offline "stop" word** — both halt the robot independent of
   Claude.

## Documentation

- **[docs/index.md](docs/index.md)** — documentation hub.
- **[docs/operations/voice-appliance.md](docs/operations/voice-appliance.md)** —
  how to operate the voice + camera robot (essential user guide).
- **[docs/operations/autostart.md](docs/operations/autostart.md)** — boot-on-power
  systemd stack.
- **[docs/RUNBOOK.md](docs/RUNBOOK.md)** — pre-flight safety, startup/shutdown,
  incident response.
- **[docs/project-status.md](docs/project-status.md)** — base/nav state + backlog.
- **[CLAUDE.md](CLAUDE.md)** / **[AGENTS.md](AGENTS.md)** — instructions for agents.
- Firmware: [base](firmware/makerpi_rp2040_base/README.md) ·
  [buddy](firmware/esp32s3_voice_buddy/README.md) ·
  [camera](firmware/xiao_esp32s3_sense_cam/README.md).
