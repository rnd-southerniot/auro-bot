# Navbot Foxglove Layouts

Default layout for live Navbot visualization via `foxglove_bridge`. Replaces
the old `navbot_web` package.

## Load the default layout

1. Start the stack on the Pi (four separate terminals):

   ```bash
   # Terminal 1 — base + LiDAR
   ssh arif@192.168.68.101 \
     "bash -ic 'source ~/projects/claude-navbot/ros2_ws/install/setup.bash && \
      ros2 launch navbot_bringup base_lidar.launch.py'"

   # Terminal 2 — SLAM
   ssh arif@192.168.68.101 \
     "bash -ic 'source ~/projects/claude-navbot/ros2_ws/install/setup.bash && \
      ros2 launch navbot_slam slam_toolbox.launch.py'"

   # Terminal 3 — Nav2
   ssh arif@192.168.68.101 \
     "bash -ic 'source ~/projects/claude-navbot/ros2_ws/install/setup.bash && \
      ros2 launch navbot_navigation nav2.launch.py'"

   # Terminal 4 — Foxglove bridge
   ssh arif@192.168.68.101 \
     "bash -ic 'source /opt/ros/jazzy/setup.bash && \
      ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765 address:=0.0.0.0'"
   ```

2. Open <https://studio.foxglove.dev> (or the Foxglove Studio desktop app).

3. **Open connection** → **Foxglove WebSocket** → `ws://192.168.68.101:8765` → **Open**.

4. **Layouts** menu → **Import from file…** → select `navbot-default.json`.

## Panels in this layout

Left half: 3D scene.

- **3D scene** (`3D!1r53yko`) — `follow-pose` camera, grid, `/scan` (Turbo colormap on intensity), URDF loaded from the `/robot_state_publisher.robot_description` parameter.

Right half: four-panel tabbed overview.

- **`/base/motor_voltage`** plot — single-trace, colour `#f5774d`.
- **`/base/lidar_voltage`** plot — single-trace, colour `#4e98e2`.
- **`/base/serial_latency_ms`** plot — single-trace, colour `#f7df71`. Spikes here flag the RP2040↔Pi serial link stalling.
- **`/cmd_vel`** plot — 3 traces for `linear.x/y/z`. Flat at idle (no motion commands); populates during drive tests.
- **Diagnostic summary** — consumes `/diagnostics`; quiet until a node publishes `diagnostic_msgs/DiagnosticArray`.
- **`/dock_pose` raw messages** — placeholder for future docking work; empty when no dock is registered.

## Troubleshooting

### URDF fails to load via "Topic" source

**Symptom:** 3D panel shows `invalid topic: /robot_description` error on the URDF custom layer.

**Cause:** Foxglove Studio's URDF custom layer rejects plain `std_msgs/String` topics (which is what `robot_state_publisher` uses for `/robot_description`) when `Source` is set to `Topic`.

**Fix:** In the 3D panel Custom layers → URDF settings, switch **Source** from `Topic` to `Parameter`, and set the parameter to `/robot_state_publisher.robot_description` (dot syntax, not slash). The committed layout already uses this.

### LiDAR scan shows a black/magenta checker pattern

**Symptom:** Some `/scan` points render with an alternating black/magenta pattern instead of normal colour.

**Cause:** RPLIDAR C1 emits `+Inf` in `ranges[i]` for beams with no return (pointing beyond 16 m or at absorbent surfaces). Foxglove flags those as invalid and replaces the colour.

**Fix (committed):** The bringup now includes a `laser_filters::LaserScanRangeFilter` node (`ros2_ws/src/navbot_lidar/launch/scan_filter.launch.py`) that replaces out-of-range values with `NaN`. Foxglove handles `NaN` by not rendering that beam, so the warning pattern is gone on the current build. The raw sllidar output is still available on `/scan_raw` for debugging.

**Ad-hoc (if running without the filter):** Set a manual max range on the `/scan` topic in the 3D panel (Value max: 16), or change Color mode to Flat.

### Foxglove Studio reports "Connection failed" or the WebSocket times out

Check in order:

1. Is `foxglove_bridge` running on the Pi?

   ```bash
   ssh arif@192.168.68.101 "pgrep -af foxglove_bridge"
   ```

2. Is port 8765 listening?

   ```bash
   ssh arif@192.168.68.101 "ss -tlnp | grep 8765"
   ```

3. Is UFW blocking?

   ```bash
   ssh arif@192.168.68.101 "sudo ufw status"   # should be inactive
   ```

4. Is the Mac on the same subnet (`192.168.68.x`)?

   ```bash
   ifconfig en0 | grep inet
   ```

5. Is the Pi reachable from the Mac?

   ```bash
   ping -c 2 192.168.68.101
   ```

## When to update this layout

- New topic added that should be default-visible.
- Panel arrangement no longer matches workflow.
- Foxglove Studio major release with layout schema changes.

Re-export via Foxglove Studio → **Layouts** → **Export** (or copy JSON),
overwrite `navbot-default.json`, and commit.
