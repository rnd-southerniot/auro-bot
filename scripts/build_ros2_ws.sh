#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WS_DIR="${ROOT_DIR}/ros2_ws"
EXTERNAL_WORKSPACE_SETUP="${EXTERNAL_WORKSPACE_SETUP:-/home/arif/ros2_ws/install/setup.bash}"

source_setup() {
  local setup_path="$1"
  set +u
  # shellcheck disable=SC1090
  source "${setup_path}"
  set -u
}

if [[ "${NAVBOT_AUTO_SYNC:-0}" == "1" ]]; then
  "${ROOT_DIR}/scripts/sync_pi_repo.sh"
elif [[ "${NAVBOT_AUTO_SYNC:-0}" == "hard" ]]; then
  "${ROOT_DIR}/scripts/sync_pi_repo.sh" --hard
fi

source_setup /opt/ros/jazzy/setup.bash
if [[ -f "${EXTERNAL_WORKSPACE_SETUP}" ]]; then
  source_setup "${EXTERNAL_WORKSPACE_SETUP}"
fi
cd "${WS_DIR}"
colcon build "$@"
echo
echo "Build complete. Source the workspace with:"
echo "source ${WS_DIR}/install/setup.bash"
