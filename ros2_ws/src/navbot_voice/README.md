# navbot_voice

The on-robot **voice brain**. It listens (via the ESP32-S3 buddy front-end),
transcribes (faster-whisper), reasons (Claude — Haiku for fast intent, Sonnet
for reasoning/vision), speaks (Piper TTS, played on the buddy), and commands the
robot **only** through the sanctioned `navbot_web` HTTP control surface
(`/api/cmd_vel`, `/api/stop`, `/api/status`) — never the Pico serial port.

See the full design + phased roadmap in the project plan and
[docs/operations/claude-operator.md](../../../docs/operations/claude-operator.md).

## Status: P0 skeleton

Currently this package only stands up the node and the control-surface link:

- `robot_client.py` — thin HTTP client for the navbot_web API (bearer-token aware).
- `voice_agent.py` — connects and logs a periodic `/api/status` summary.

No audio, LLM, or motion yet — those land in P1–P6 (buddy firmware, wake/STT,
safety, gated teleop, perception, autostart).

## P6 — perception (camera/vision)

The robot's eyes are a **XIAO ESP32-S3 Sense** Wi-Fi camera
([`firmware/xiao_esp32s3_sense_cam`](../../../firmware/xiao_esp32s3_sense_cam)),
serving JPEG over HTTP — not a CSI Pi-camera. The brain reaches it with
[`camera_client.py`](navbot_voice/camera_client.py) (`NAVBOT_CAMERA_URL`, default
`http://192.168.68.110`):

- **Headless brain** (`claude_brain.py`, subscription auth): `navbotctl look`
  grabs a frame and prints the JPEG path; the `Read` tool (now allowed) lets
  multimodal Claude Code see it — no API key, no metered vision call.
- **SDK brain** (`agent.py`): the `look` tool sends the JPEG to a vision model
  (`NAVBOT_VISION_MODEL`, default `claude-sonnet-4-6`) and relays the description.

The `navbot_camera` package exposes the same camera to ROS
(`/camera/grab_frame`, `/camera/status`).

## Run (P0 gate)

With the web console up on the robot (`./scripts/launch_web_console.sh`):

```bash
ros2 launch navbot_voice voice_agent.launch.py
# expect: "controller=IDLE OK estop=off odom=(...) motor_v=... scan_alive=..."
```

## Safety

Motion (later phases) reuses the existing three-layer watchdog (web 0.35 s →
serial_bridge 0.5 s → RP2040 0.5 s); the buddy's on-device offline "stop" maps to
`POST /api/stop`. No unbounded "run until told" motion. See the plan's Safety
section.
