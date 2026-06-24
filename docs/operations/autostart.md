# Autostart — boot the robot into the voice appliance (P7)

The robot can come up hands-free on power-on: full sensing stack → web control
surface → voice brain. Say "Jarvis", talk, and it listens, sees (camera),
answers, and drives — all gated by the existing safety layer.

This is implemented as a small systemd stack. Units live in
[`ops/systemd/`](../../ops/systemd/); install with
[`scripts/install_autostart.sh`](../../scripts/install_autostart.sh).

> Run the installer **on the robot Pi** (`navbot-pi`, Ubuntu 24.04 / ROS 2 Jazzy),
> not the staging host.

## What comes up

| Unit | Component | Brings up |
|---|---|---|
| `navbot-bringup.service` | `imu_localization.launch.py` | base serial bridge (Pico) + LiDAR + IMU + EKF (`/odometry/filtered`) |
| `navbot-web.service` | `navbot_web` | `/api/cmd_vel`, `/api/stop`, `/api/status` on `:8080` |
| `navbot-voice.service` | `navbot_voice_io.buddy_brain` | buddy serial link + Whisper STT + Claude brain + Piper TTS |
| `navbot.target` | — | groups the three; enabled into `multi-user.target` |
| `navbot-nav.service` | `navigation.launch.py` | map-based Nav2 — **installed but disabled** (needs a home map) |

Ordering: `bringup` → (`Requires`) `web` → (`Requires`) `voice`. If bringup
fails, web and voice don't start; each restarts on failure.

The **XIAO camera** is a separate Wi-Fi board (P6) and powers up on its own —
nothing to autostart on the Pi for it. The voice brain reaches it over HTTP
(`NAVBOT_CAMERA_URL`).

## Install

```bash
# on the robot, from the repo root
sudo ./scripts/install_autostart.sh         # install + enable for boot
sudo ./scripts/install_autostart.sh --now    # ...and start immediately
```

The installer:
1. writes `/etc/navbot/navbot.env` from
   [`navbot.env.example`](../../ops/systemd/navbot.env.example) (kept if it
   already exists — edit it for paths/creds), and
2. installs the units into `/etc/systemd/system` (substituting the repo path),
   then enables the three core services + `navbot.target`.

**Edit `/etc/navbot/navbot.env` before first boot** — it sets ROS sourcing, the
external sllidar overlay, the camera URL, the `claude` binary path, and the
Whisper/Piper locations.

## Operate

```bash
systemctl status navbot-voice.service
journalctl -u navbot-voice.service -f         # follow the voice loop
journalctl -u navbot-bringup.service -b       # this boot's sensor bringup
sudo systemctl restart navbot-voice.service   # restart just the brain
sudo systemctl stop navbot.target             # halt the whole appliance
sudo systemctl start navbot.target            # bring it back
```

Uninstall: `sudo ./scripts/install_autostart.sh --uninstall` (leaves
`/etc/navbot/navbot.env`).

## Safety

- **Drive mode is OFF at boot** (`SafetyGate` default). The robot will not move
  until someone asks it to and the brain enables drive mode; speeds/durations are
  hard-clamped.
- The on-device **"stop"** word and the hardware **e-stop** override everything,
  independent of the brain.
- One owner of the Pico serial port at a time: the voice brain drives **only**
  through `navbot_web` `/api/*`, never the serial port — so it never fights
  `navbot-bringup`.

## Enabling Nav2 later

`navbot-nav.service` is installed but **not enabled** — Nav2/AMCL needs a fresh
home SLAM map (the `office_lab` maps are stale after the home move; see
[project-status.md](../project-status.md)). Once a home map exists and
`navigation.launch.py` points at it:

```bash
sudo systemctl enable --now navbot-nav.service
```
