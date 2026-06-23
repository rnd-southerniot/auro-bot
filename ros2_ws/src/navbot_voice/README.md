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
