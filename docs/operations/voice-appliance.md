# Operating the voice + camera robot

This is the **essential user guide** for talking to auro-bot. For boot-on-power
setup see [autostart.md](autostart.md); for base safety see
[../RUNBOOK.md](../RUNBOOK.md).

## Before you start

1. **Clear space + free wheels.** If you'll let it drive, put it on blocks or give
   it open floor. Never command motion with wheels jammed.
2. **Power on** the robot (Pi + base + buddy) and the **XIAO camera** (its own USB
   power; it joins Wi-Fi `Auro` and self-serves — nothing to plug into the Pi).
3. **Bring the stack up** — either it autostarts (P7), or manually:
   ```bash
   ssh navbot-pi
   ros2 launch navbot_bringup imu_localization.launch.py   # base + LiDAR + IMU/EKF
   ./scripts/launch_web_console.sh                          # /api/* on :8080
   python3 -m navbot_voice_io.buddy_brain                   # the voice loop
   ```
   The voice loop prints `buddy brain running — say 'Jarvis' then your phrase.`

## Talking to it

Say the wake word **"Jarvis,"** wait for the **listening** face, then speak one
request. The buddy streams your speech; Whisper transcribes; Claude decides; Piper
speaks the reply.

| You say | It does |
|---|---|
| "Jarvis, **what do you see**?" | grabs a camera frame and describes the scene |
| "Jarvis, **drive forward two seconds**" | enables drive mode, drives ~0.10 m/s, auto-stops |
| "Jarvis, **turn left a little**" | a short, clamped in-place-ish turn |
| "Jarvis, **what's your status**?" | controller / e-stop / odometry / battery / LiDAR |
| "Jarvis, **stop**" | halts now (also works as an offline word — see Safety) |

Tips:
- **Say "Jarvis" clearly.** Wake is reliable when enunciated, marginal at low
  volume (single mic, no array). One request per wake.
- Replies are **one short spoken sentence** by design.
- It will tell you honestly when it can't do something (e.g. navigate to a named
  place — that needs a map).

## What it can and can't do (today)

**Can:** converse, describe what the camera sees, report status, and drive short
clamped distances/turns on command.

**Can't yet:** autonomous navigation to named places (Nav2/AMCL needs a fresh home
map — `navbot-nav` is installed but disabled), and it won't hear a "stop" shouted
*in the middle* of a Claude-initiated drive (see Safety). It has no arm/manipulator.

## Camera

The camera is a Wi-Fi board at **`http://192.168.68.110`** (DHCP-reserved). Quick
checks, no ROS needed:

```bash
curl -s http://192.168.68.110/status            # fps, motion, rssi, uptime
curl -s http://192.168.68.110/snapshot -o f.jpg # a still JPEG
```

The brain reads `NAVBOT_CAMERA_URL` (default that address). If the camera moves to
a new network or address, update that env / `voice_agent.yaml` and
`navbot_camera/config/camera.yaml`. In ROS, the same camera is exposed as
`/camera/grab_frame` + `/camera/status` by `navbot_camera`.

## Safety (read this)

- **Drive mode is OFF by default.** The robot will not move until you ask it to and
  the brain enables drive mode. Speeds/durations are hard-clamped
  (`≤0.12 m/s`, `≤0.6 rad/s`, `≤3 s`).
- **"Stop" word:** the buddy detects "stop"/"halt" on-device and halts instantly,
  independent of Claude — **but only in the ~5 s window after a wake.** A "stop"
  shouted during a later drive may not be heard. Until that's fixed (continuous
  detector), rely on the bounded motion (≤3 s) and the controls below.
- **Always-available stops:** the **hardware e-stop**, and
  `./scripts/launch_web_console.sh` UI / `curl -X POST http://127.0.0.1:8080/api/stop`,
  and `/navbot:stop`.
- The brain drives **only** through `/api/*`; it never owns the Pico serial port,
  so it can't conflict with the base bringup.

## Troubleshooting

| Symptom | Check |
|---|---|
| No wake / no response | buddy on `ttyACM1`? voice loop running? mic gain (see [[buddy-voice-loop]] memory) |
| "camera unavailable" on look | `curl http://192.168.68.110/status`; is the XIAO powered + on Wi-Fi? |
| "refused to move" | drive mode off, e-stop active, or low motor voltage — the reply says which |
| Replies but won't drive | base bringup up? `/navbot:status`; web console reachable on :8080? |
| Brain falls back to echo | no `claude` on PATH and no `ANTHROPIC_API_KEY` — install/auth the Claude CLI |

Logs (with autostart): `journalctl -u navbot-voice.service -f`. Manual: the
`buddy_brain` stdout (`[wake]`, `heard: …`, `reply: …`, `[STOP]`).
