#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source /opt/ros/jazzy/setup.bash
source "${ROOT_DIR}/ros2_ws/install/setup.bash"
ros2 launch navbot_teleop teleop.launch.py "$@"
