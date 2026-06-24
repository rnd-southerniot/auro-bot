# Next-session handoff — 2026-06-24

Pick-up note after the voice-perception + autostart + docs session. Start here.

## Where we are

The voice subsystem is complete through **P7**. All on `main`, pushed to
`github.com/rnd-southerniot/auro-bot` (remote `origin` configured; PAT in the
gateway's `~/.git-credentials`, so `git push`/`pull` just work).

| Phase | What | State |
|---|---|---|
| P0–P3 | brain skeleton, buddy fw, wake/STT/TTS loop | ✅ on hardware |
| P5 | Claude gated voice teleop (headless, subscription) | ✅ on blocks 2026-06-24 (odom +0.18 m) |
| P6 | XIAO ESP32-S3 Sense Wi-Fi camera + `look()` | ✅ live grab + status validated |
| P7 | systemd autostart stack | ✅ **boot-validated on the robot 2026-06-24** (deployed + rebooted) |

Key recent commits: `75cfe37` P6, `9f68405` P7, `30c2a9b` docs; deploy fixes
`0760be7` (overlay path) + `6c4f9fe` (navbotctl exec bit). Record:
[validation/records/2026-06-24-autostart-validation.md](../validation/records/2026-06-24-autostart-validation.md).

## Open follow-ups (priority order)

1. **LiDAR `/scan` absent at boot — known: LiDAR battery down.** `sllidar_node`
   dies with `SL_RESULT_OPERATION_TIMEOUT` (exit 255). Confirmed a flat LiDAR pack
   — a common, expected blocker, **not** a P7 bug and not being chased. Charge the
   LiDAR pack, then restart `navbot-bringup` (or reboot). Voice + camera + base +
   IMU/EKF are unaffected; Nav2 is disabled anyway.
2. **Capture a fresh home SLAM map** → unblocks `navbot-nav` (Nav2/AMCL is
   installed but disabled; `office_lab` maps are stale after the home move). Then
   `sudo systemctl enable --now navbot-nav.service`.
3. **Close the windowed-"stop" gap** (known safety gap). On-device "stop" only
   fires in the ~5 s post-wake MultiNet window, so a "stop" shouted *during* a
   Claude-initiated drive isn't heard. Fix = continuous "stop"/"halt" detector
   (always-on MultiNet, or "stop" as a 2nd WakeNet word). Motion stays bounded by
   clamps + cmd-vel timeout meanwhile; the hardware e-stop always works.
4. **Base carryovers** (lower priority, from TODO.md): reconnect GP27 `motor_v`
   divider; recompute INA238 calibration for the motor rail.

## Facts / gotchas to carry forward

- **This host is staging** (gateway Pi), not the robot. Robot = `ssh navbot-pi`
  (`arif@192.168.68.126`, Ubuntu Jazzy). Don't assume robot paths exist here.
- **Camera** is a Wi-Fi board at **`192.168.68.110`** (DHCP-reserved, MAC
  `8C:BF:EA:8E:65:04`), reachable from this host. `/navbot:camera-test` to check.
  Not wired to the Pi — only needs power. See [[xiao-camera]].
- **Backgrounding ROS launches on navbot-pi via nohup/setsid is flaky**; reliable
  pattern is a foreground `ssh navbot-pi 'exec bash <script>'` from the gateway
  (run_in_background). See [[buddy-voice-loop]].
- Engines (faster-whisper, Piper) are installed on the robot, **not** in the repo.

## Orientation for the next agent

- Read: [README.md](../../README.md), [CLAUDE.md](../../CLAUDE.md),
  [operations/voice-appliance.md](../operations/voice-appliance.md),
  [operations/autostart.md](../operations/autostart.md).
- Memory: [[buddy-voice-loop]], [[xiao-camera]], [[voice-autostart]],
  [[auro-bot-staging-repo]], [[buddy-firmware-build-flash]].
- Safe first commands: `/navbot:status`, `/navbot:camera-test`,
  `/navbot:voice-status` (all read-only), `/navbot:stop` (halt).
