#!/usr/bin/env bash
set -eo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ROS 2 Jazzy setup.bash references unbound variables (AMENT_TRACE_SETUP_FILES
# and friends), so we cannot run the sourcing step under `set -u`. Source with
# -u off, then re-enable for the rest of the script. Same pattern used in
# setup-pi.sh configure_kernel_tuning() step.
set +u
source /opt/ros/jazzy/setup.bash
source "${ROOT_DIR}/ros2_ws/install/setup.bash"
set -u

ros2 launch navbot_bringup navigation.launch.py "$@"
