#!/usr/bin/env bash
set -euo pipefail

# Launch base + LiDAR first, wait for the C1 scan motor to warm up,
# then start slam_toolbox. The RPLIDAR C1 vendor manual recommends
# at least 2 minutes of warm-up with the motor spinning before
# precision SLAM work.

WARMUP_SECONDS="${LIDAR_WARMUP_SECONDS:-120}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

source /opt/ros/jazzy/setup.bash
if [[ -f "${EXTERNAL_WORKSPACE_SETUP:-/home/arif/ros2_ws/install/setup.bash}" ]]; then
  set +u
  # shellcheck disable=SC1090
  source "${EXTERNAL_WORKSPACE_SETUP:-/home/arif/ros2_ws/install/setup.bash}"
  set -u
fi
source "${ROOT_DIR}/ros2_ws/install/setup.bash"

echo "Starting base + LiDAR..."
ros2 launch navbot_bringup base_lidar.launch.py "$@" &
BASE_PID=$!

echo "Waiting ${WARMUP_SECONDS}s for LiDAR warm-up..."
sleep "${WARMUP_SECONDS}"

echo "Verifying /scan is alive..."
if ! ros2 topic hz /scan --window 5 2>/dev/null | head -1 | grep -q 'average rate'; then
  echo "WARNING: /scan does not appear to be publishing. Proceeding anyway."
fi

echo "Starting slam_toolbox..."
ros2 launch navbot_slam slam_toolbox.launch.py &
SLAM_PID=$!

cleanup() {
  echo "Shutting down..."
  kill "${SLAM_PID}" 2>/dev/null || true
  kill "${BASE_PID}" 2>/dev/null || true
  wait
}
trap cleanup INT TERM

wait
