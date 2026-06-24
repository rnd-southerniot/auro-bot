# auro-bot Documentation

Navigation hub for the auro-bot project docs (the voice + camera robot on the
navbot drive base). Operators land here first — pick the entry point that matches
what you're doing.

## First stop

- **Operating the voice robot?** Read
  [operations/voice-appliance.md](operations/voice-appliance.md).
- **Starting a base/hardware session?** Begin with the pre-flight safety checklist
  in [RUNBOOK.md](RUNBOOK.md).
- **Trying to understand the robot?** Read
  [architecture/system.md](architecture/system.md).
- **Checking project state?** See
  [project-status.md](project-status.md).

## Top-level docs

- [RUNBOOK.md](RUNBOOK.md) — pre-flight safety, startup/shutdown,
  launch, smoke checks, incident response, troubleshooting.
- [power-architecture.md](power-architecture.md) — three-battery system,
  Mermaid diagrams, the Pi USB-C non-isolation finding.
- [project-status.md](project-status.md) — current state, active work,
  Phase C backlog, decisions log.

## Architecture

- [architecture/system.md](architecture/system.md) — hardware split,
  ROS graph, serial protocol, TF tree, current risks.

## Voice + camera (auro-bot)

- [operations/voice-appliance.md](operations/voice-appliance.md) — **essential
  user guide**: talking to the robot, what it can/can't do, the camera, safety,
  troubleshooting.
- [operations/autostart.md](operations/autostart.md) — boot the whole appliance
  on power-on via the systemd stack (`ops/systemd/`, `install_autostart.sh`).
- The voice/camera subsystems themselves: `ros2_ws/src/navbot_voice/README.md`,
  `navbot_voice_io`, `navbot_camera`, and the firmware READMEs under
  `firmware/{esp32s3_voice_buddy,xiao_esp32s3_sense_cam}/`.

## Operations

- [operations/claude-operator.md](operations/claude-operator.md) — how an
  agent / Claude Code operates the robot: identity, tool boundary, control
  surface, safety gates, startup flow.
- [operations/web-console.md](operations/web-console.md) — `navbot_web`
  browser console (being replaced by Foxglove; see note in-doc).
- [operations/foxglove/README.md](operations/foxglove/README.md) —
  Foxglove bridge setup and default layout.
- [operations/bench-test-commands.md](operations/bench-test-commands.md) —
  the `/navbot:*` operator bench-test slash commands (motors, voltages,
  LiDAR health, gyro) with PASS criteria and troubleshooting.

## Hardware

- [hardware/pi-rebuild.md](hardware/pi-rebuild.md) — Ubuntu Jazzy Pi 5
  rebuild procedure and the five silent bugs fixed during the rebuild.
- [hardware/ina238.md](hardware/ina238.md) — INA238 chip details,
  driver troubleshooting, register notes.
- [hardware/lidar-mount.md](hardware/lidar-mount.md) — RPLIDAR C1
  physical mount conventions and filter pipeline.

## Testing

- [testing/motion-tests.md](testing/motion-tests.md) — 120 mm drive
  result, coast-on analysis, odom accuracy, current speed envelope.

## Validation

- [validation/README.md](validation/README.md) — validated checkpoints
  and remaining validation limits.
- [validation/records/](validation/records/) — historical session
  records, including the v1.2.0 freeze soak and pre-wipe calibration.

## Notes

- [notes/brake-attempt-forensic.md](notes/brake-attempt-forensic.md) —
  forensic writeup of the regen-brake experiment that was reverted as
  ineffective at creep speeds.

## Documentation rules

- Put operator commands in [RUNBOOK.md](RUNBOOK.md).
- Put verified runtime facts in [validation/README.md](validation/README.md).
- Put system design and interfaces in [architecture/](architecture/).
- Put ops procedures and UI/API details in [operations/](operations/).
- Put hardware-specific gotchas in [hardware/](hardware/).
- Put test results in [testing/](testing/).
- Put session-specific forensics in [notes/](notes/).
- Archive one-off session records under [validation/records/](validation/records/)
  with an ISO date prefix (e.g. `2026-04-19-topic.md`).
- Do not create a new docs file unless it has a distinct long-term
  purpose.
