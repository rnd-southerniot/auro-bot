#!/usr/bin/env bash
# navbot_service.sh — single entry point the systemd units exec (P7 autostart).
#
# Sources ROS 2 + the external (sllidar) overlay + this repo's workspace, then
# execs one component of the voice-appliance stack. Keeping the source chain in
# one place keeps the unit files trivial and DRY.
#
# Usage: navbot_service.sh <bringup|web|voice|nav>
#
# Config comes from the EnvironmentFile the units load (ops/systemd/navbot.env,
# installed to /etc/navbot/navbot.env). All paths have robot defaults.
#
# NOTE: deliberately NO `set -u` — Jazzy's setup.bash references
# AMENT_TRACE_SETUP_FILES before testing if it's set (same gotcha as setup-pi.sh).
set -eo pipefail

component="${1:-}"
if [[ -z "${component}" ]]; then
  echo "usage: navbot_service.sh <bringup|web|voice|nav>" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# --- config (overridable via the EnvironmentFile / env) ---
ROS_SETUP="${ROS_SETUP:-/opt/ros/jazzy/setup.bash}"
EXTERNAL_WORKSPACE_SETUP="${EXTERNAL_WORKSPACE_SETUP:-/home/arif/ros2_ws/install/setup.bash}"
WORKSPACE_SETUP="${WORKSPACE_SETUP:-${ROOT_DIR}/ros2_ws/install/setup.bash}"
WEB_PORT="${NAVBOT_WEB_PORT:-8080}"
CAPTURE_ROOT="${NAVBOT_CAPTURE_ROOT:-${ROOT_DIR}/captures}"

# --- source the ROS environment ---
# shellcheck disable=SC1090
source "${ROS_SETUP}"
if [[ -f "${EXTERNAL_WORKSPACE_SETUP}" ]]; then
  # shellcheck disable=SC1090
  source "${EXTERNAL_WORKSPACE_SETUP}"
fi
if [[ -f "${WORKSPACE_SETUP}" ]]; then
  # shellcheck disable=SC1090
  source "${WORKSPACE_SETUP}"
else
  echo "workspace not built: ${WORKSPACE_SETUP} (run scripts/build_ros2_ws.sh)" >&2
  exit 1
fi

# Word-split user-supplied extra launch args (e.g. serial_port:=... log_level:=debug).
read -r -a BRINGUP_ARGS <<< "${NAVBOT_BRINGUP_ARGS:-}"
read -r -a NAV_ARGS <<< "${NAVBOT_NAV_ARGS:-}"

case "${component}" in
  bringup)
    # Full sensing stack: base serial bridge + LiDAR + IMU + EKF (/odometry/filtered).
    exec ros2 launch navbot_bringup imu_localization.launch.py "${BRINGUP_ARGS[@]}"
    ;;
  web)
    # Control surface (/api/cmd_vel, /api/stop, /api/status) the voice brain wraps.
    exec ros2 launch navbot_web web_console.launch.py \
      port:="${WEB_PORT}" capture_root:="${CAPTURE_ROOT}"
    ;;
  voice)
    # Conversational loop: buddy serial link + Whisper STT + Claude brain + Piper TTS.
    exec python3 -m navbot_voice_io.buddy_brain
    ;;
  nav)
    # Map-based Nav2 stack — needs a saved home map (see project-status.md). Off by
    # default; enable navbot-nav.service once maps/<home>.{pgm,yaml} exists.
    exec ros2 launch navbot_bringup navigation.launch.py "${NAV_ARGS[@]}"
    ;;
  *)
    echo "unknown component: ${component}" >&2
    exit 2
    ;;
esac
