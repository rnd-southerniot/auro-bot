# Pi 5 Rebuild — Ubuntu Jazzy

Procedure for rebuilding the Pi 5 from scratch on Ubuntu 24.04 arm64 +
ROS 2 Jazzy, plus the five silent bugs that were fixed during the most
recent rebuild (pre-wipe snapshot at
[../validation/records/2026-04-19-pre-wipe-calibration.md](../validation/records/2026-04-19-pre-wipe-calibration.md)).

Always pair this file with [../RUNBOOK.md](../RUNBOOK.md) pre-flight
checklist before first boot on the rebuilt image.

## Why rebuild

The most recent rebuild was triggered by a `fastcdr` ABI mismatch after
an upstream Ubuntu/ROS update. The symptom was ROS 2 nodes segfaulting
during `rclcpp::init()` on the stock Pi image. A rebuild off a fresh
Ubuntu 24.04 arm64 image restored a coherent set of matching binaries.

## High-level procedure

1. Flash a fresh Ubuntu 24.04 arm64 server image to SD card.
2. Boot, create the `arif` user, change hostname, attach keyboard for
   first SSH setup.
3. From the host laptop, SSH in and run:

   ```bash
   git clone -b navbot-experimental https://github.com/rnd-southerniot/claude-navbot.git \
     ~/projects/claude-navbot
   cd ~/projects/claude-navbot
   bash scripts/setup-pi.sh
   ```

4. `setup-pi.sh` is idempotent and installs ROS 2 Jazzy, Nav2,
   slam_toolbox, Foxglove bridge, Pico SDK, udev rules, CycloneDDS,
   kernel socket buffer tuning.
5. Optional: re-run with `NAVBOT_CONFIGURE_STATIC_IP=1` to set the
   static IP (default `192.168.68.101/24`).
6. After reboot: `colcon build --symlink-install` in `ros2_ws/`.
7. Flash firmware UF2 to the RP2040 (see
   [../../firmware/makerpi_rp2040_base/FLASHING.md](../../firmware/makerpi_rp2040_base/FLASHING.md)).
8. Run the smoke checks from [../RUNBOOK.md](../RUNBOOK.md) Smoke Checks
   section before any motion command.

## The five silent bugs fixed during the most recent rebuild

Each of these was a latent-but-dormant problem in the previous image
that only surfaced when a symptom pulled on its thread. They are listed
chronologically by commit hash on the `navbot-experimental` branch.

### 1. Kernel socket buffers 208 kB → 16 MB

- **Commit:** `9178451`
- **Symptom:** every ROS 2 node aborted at `rmw_create_node()` with
  `failed to increase socket receive buffer size to at least 10485760`.
- **Root cause:** Ubuntu 24.04's default `net.core.rmem_max=208KB` is
  below the 10 MB that CycloneDDS requires per `~/.ros/cyclonedds.xml`.
- **Fix:** `/etc/sysctl.d/10-cyclonedds.conf` sets `rmem_max`,
  `rmem_default`, `wmem_max`, `wmem_default` to 16 MB. Baked into
  `setup-pi.sh` as `configure_kernel_tuning`.

### 2. `docking_server` `SimpleChargingDock` stub

- **Commit:** `cbd6088`
- **Symptom:** `docking_server` lifecycle node refused to activate.
- **Root cause:** upstream Nav2 bringup references `docking_server` but
  the codebase had no minimal dock plugin configured.
- **Fix:** minimal `docking_server` config wired to a
  `SimpleChargingDock` stub plugin so the lifecycle node activates in
  bring-up even when docking isn't used.

### 3. `base_link` → `base_footprint` in six configs

- **Commit:** `d7aa26c`
- **Symptom:** SLAM map had a persistent ~33 mm offset and Nav2
  planners behaved oddly around the robot origin.
- **Root cause:** the 2D nav stack expects `base_footprint` as the
  planning frame (on-ground projection of the robot). Six configs still
  named `base_link` as the primary frame, which sits above the ground
  plane at the wheel axis height.
- **Fix:** swap `base_link` → `base_footprint` in Nav2 costmap configs,
  AMCL, velocity_smoother, robot_localization, SLAM, and the URDF TF
  tree so there is a proper `odom → base_footprint → base_link` chain.
- **Lesson:** SLAM map offset that exactly matches wheel-axis height is
  a strong hint that `base_link` vs `base_footprint` is mis-wired.

### 4. URDF laser X offset 70 mm → 35 mm

- **Commit:** `1952f6a`
- **Symptom:** LiDAR scans rendered visually offset from the robot body
  in Foxglove.
- **Root cause:** URDF declared the laser mount X offset from
  `base_link` as 70 mm; physical measurement of the actual LiDAR
  position was 35 mm.
- **Fix:** update URDF. Physical measurements are the source of truth
  for all mount offsets.

### 5. Firmware wheel_radius 0.033 → 0.0325 in URDF

- **Commit:** `1952f6a` (same commit as #4)
- **Symptom:** odometry consistently over-reported distance by ~1.5%.
- **Root cause:** firmware used the nominal `0.033` m wheel radius; the
  correctly-calibrated value is `0.0325` m.
- **Fix:** URDF wheel radius updated to `0.0325` m to match reality.
- **Remaining gap:** the firmware still hard-codes `0.033f` —
  the URDF-firmware mismatch is tracked in the Phase C backlog (see
  [../project-status.md](../project-status.md)).

## Lessons from this rebuild

- **Upstream launch files hard-code lifecycle-node lists.** If a node
  listed in `nav2_bringup` isn't running, the whole lifecycle stays in
  `INACTIVE`. Always check the lifecycle manager's configured nodes
  list before assuming a bringup is broken.
- **A 33 mm SLAM offset is a `base_link`/`base_footprint` smell.** Any
  map offset that exactly matches a known vertical dimension on the
  robot (wheel axis height, sensor height) is worth checking against
  frame-naming before deeper SLAM debugging.
- **`fastcdr` ABI mismatch warrants a full rebuild**, not a partial
  re-install. Matching binaries across the full DDS + ROS stack matter
  more than individual patches.
- **Pre-wipe artifacts are worth capturing.** See
  [../validation/records/2026-04-19-pre-wipe-calibration.md](../validation/records/2026-04-19-pre-wipe-calibration.md)
  and
  [../validation/records/2026-04-19-pre-wipe-packages.txt](../validation/records/2026-04-19-pre-wipe-packages.txt)
  for what was validated on the last image.
