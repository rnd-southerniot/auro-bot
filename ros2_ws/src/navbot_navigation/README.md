# navbot_navigation

Wrapper around the upstream Nav2 stack. Does not vendor Nav2; provides
launch + parameter tuning for Navbot.

## Launch files

- `launch/` — starts the Nav2 bringup with Navbot-specific parameters
  (costmap tuning, planner, controller, BT).

## Config

- `config/` — Navbot tuning of DWB, costmap inflation, BT XML.

## Dependencies

- ROS 2 Jazzy: `nav2_bringup`, `nav2_msgs`, `docking_server`
  (apt install `ros-jazzy-navigation2 ros-jazzy-nav2-bringup`).
- Requires a live map frame (SLAM or a saved map) and a running base +
  localization stack.

## Known Jazzy gotchas

- `drive_on_heading` decel-envelope parameters are **Kilted / Rolling
  only** — they are not supported on Jazzy. An attempt to use them
  was reverted (commit `8cf3319`). See
  [../../../docs/testing/motion-tests.md](../../../docs/testing/motion-tests.md).

## Related docs

- Current backlog state: [../../../docs/project-status.md](../../../docs/project-status.md)
- Pi-rebuild `base_footprint` fix: [../../../docs/hardware/pi-rebuild.md](../../../docs/hardware/pi-rebuild.md)
