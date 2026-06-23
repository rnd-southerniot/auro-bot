#!/usr/bin/env bash
set -eo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT=8080
ROS_SETUP_DEFAULT="/opt/ros/jazzy/setup.bash"
EXTERNAL_WORKSPACE_SETUP_DEFAULT="/home/arif/ros2_ws/install/setup.bash"
ROS_SETUP_PATH="${ROS_SETUP:-${ROS_SETUP_DEFAULT}}"
EXTERNAL_WORKSPACE_SETUP_PATH="${EXTERNAL_WORKSPACE_SETUP:-${EXTERNAL_WORKSPACE_SETUP_DEFAULT}}"
WORKSPACE_SETUP_PATH="${WORKSPACE_SETUP:-${ROOT_DIR}/ros2_ws/install/setup.bash}"
FORWARD_ARGS=()

for arg in "$@"; do
  case "$arg" in
    port:=*)
      PORT="${arg#port:=}"
      ;;
    *)
      FORWARD_ARGS+=("${arg}")
      ;;
  esac
done

require_file() {
  local path="$1"
  local label="$2"
  if [[ ! -f "${path}" ]]; then
    echo "${label} not found: ${path}" >&2
    return 1
  fi
}

find_listener_pids() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -t -n -P -iTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null | sort -u
    return
  fi

  if command -v ss >/dev/null 2>&1; then
    ss -ltnp "( sport = :${PORT} )" 2>/dev/null \
      | awk 'match($0, /pid=([0-9]+)/, m) { print m[1] }' \
      | sort -u
  fi
}

read_listener_pids() {
  REPLY_PIDS=()
  while IFS= read -r pid; do
    [[ -n "${pid}" ]] && REPLY_PIDS+=("${pid}")
  done < <(find_listener_pids)
}

read_listener_pids
LISTENER_PIDS=("${REPLY_PIDS[@]}")
if ((${#LISTENER_PIDS[@]} > 0)); then
  echo "Port ${PORT} is already in use by PID(s): ${LISTENER_PIDS[*]}"
  echo "Stopping existing listener(s) on port ${PORT}..."
  kill "${LISTENER_PIDS[@]}" 2>/dev/null || true
  sleep 1

  read_listener_pids
  STILL_RUNNING=("${REPLY_PIDS[@]}")
  if ((${#STILL_RUNNING[@]} > 0)); then
    echo "Listener(s) still active on port ${PORT}, forcing stop: ${STILL_RUNNING[*]}"
    kill -9 "${STILL_RUNNING[@]}" 2>/dev/null || true
    sleep 1
  fi

  read_listener_pids
  REMAINING=("${REPLY_PIDS[@]}")
  if ((${#REMAINING[@]} > 0)); then
    echo "Failed to free port ${PORT}; still held by PID(s): ${REMAINING[*]}" >&2
    exit 1
  fi
fi

if ! require_file "${ROS_SETUP_PATH}" "ROS setup"; then
  cat >&2 <<EOF
This script expects ROS 2 Jazzy on the machine where it is run.

If you are on the Pi, confirm Jazzy is installed at:
  ${ROS_SETUP_DEFAULT}

If ROS is installed elsewhere, rerun with:
  ROS_SETUP=/path/to/setup.bash ./scripts/launch_web_console.sh
EOF
  exit 1
fi

if ! require_file "${WORKSPACE_SETUP_PATH}" "Workspace setup"; then
  cat >&2 <<EOF
Build the workspace first or point WORKSPACE_SETUP at an existing install setup:
  WORKSPACE_SETUP=/path/to/ros2_ws/install/setup.bash ./scripts/launch_web_console.sh
EOF
  exit 1
fi

source "${ROS_SETUP_PATH}"
if [[ -f "${EXTERNAL_WORKSPACE_SETUP_PATH}" ]]; then
  source "${EXTERNAL_WORKSPACE_SETUP_PATH}"
elif [[ -n "${EXTERNAL_WORKSPACE_SETUP:-}" ]]; then
  echo "External workspace setup not found: ${EXTERNAL_WORKSPACE_SETUP_PATH}" >&2
  exit 1
fi
source "${WORKSPACE_SETUP_PATH}"

echo "Launching navbot_web on port ${PORT}"
ros2 launch navbot_web web_console.launch.py \
  port:="${PORT}" \
  capture_root:="${ROOT_DIR}/captures" \
  "${FORWARD_ARGS[@]}"
