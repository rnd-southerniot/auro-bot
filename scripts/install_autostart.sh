#!/usr/bin/env bash
# install_autostart.sh — install the navbot voice-appliance systemd stack (P7).
#
# Run this ON THE ROBOT Pi (Ubuntu 24.04 / ROS 2 Jazzy), not the staging host.
# It installs the units from ops/systemd/, an EnvironmentFile at
# /etc/navbot/navbot.env (kept if it already exists), and enables the appliance
# so the robot boots hands-free: base + LiDAR + IMU/EKF -> web -> voice brain.
#
# Usage:
#   sudo ./scripts/install_autostart.sh            # install + enable (start at boot)
#   sudo ./scripts/install_autostart.sh --now      # also start the stack immediately
#   sudo NAVBOT_USER=arif ./scripts/install_autostart.sh
#   sudo ./scripts/install_autostart.sh --uninstall
#
# Idempotent: re-running updates the unit files (your /etc/navbot/navbot.env is
# never overwritten).
set -eo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${ROOT_DIR}/ops/systemd"
DEST="/etc/systemd/system"
ENV_DIR="/etc/navbot"
ENV_FILE="${ENV_DIR}/navbot.env"
SVC_USER="${NAVBOT_USER:-arif}"
UNITS=(navbot-bringup.service navbot-web.service navbot-voice.service navbot-nav.service navbot.target)
START_NOW=0
UNINSTALL=0

for arg in "$@"; do
  case "${arg}" in
    --now) START_NOW=1 ;;
    --uninstall) UNINSTALL=1 ;;
    *) echo "unknown arg: ${arg}" >&2; exit 2 ;;
  esac
done

if [[ "${EUID}" -ne 0 ]]; then
  echo "must run as root (use sudo)" >&2
  exit 1
fi

if [[ "${UNINSTALL}" -eq 1 ]]; then
  systemctl disable --now navbot.target navbot-voice.service navbot-web.service \
    navbot-bringup.service navbot-nav.service 2>/dev/null || true
  for u in "${UNITS[@]}"; do rm -f "${DEST}/${u}"; done
  systemctl daemon-reload
  echo "uninstalled navbot units (left ${ENV_FILE} in place)."
  exit 0
fi

# 1) EnvironmentFile — install the example once; never clobber a real one.
install -d -m 0755 "${ENV_DIR}"
if [[ -f "${ENV_FILE}" ]]; then
  echo "keeping existing ${ENV_FILE}"
else
  install -m 0644 "${SRC}/navbot.env.example" "${ENV_FILE}"
  echo "installed ${ENV_FILE} (review and edit paths/creds before first boot)"
fi

# 2) Units — substitute __REPO_DIR__ (and User=, if overridden) into /etc/systemd/system.
for u in "${UNITS[@]}"; do
  sed -e "s#__REPO_DIR__#${ROOT_DIR}#g" \
      -e "s#^User=arif#User=${SVC_USER}#" \
      -e "s#^Group=arif#Group=${SVC_USER}#" \
      "${SRC}/${u}" > "${DEST}/${u}"
  echo "installed ${DEST}/${u}"
done

systemctl daemon-reload

# 3) Enable for boot (the three core services + the target). navbot-nav stays
#    disabled — enable it yourself once a home map exists.
systemctl enable navbot-bringup.service navbot-web.service navbot-voice.service navbot.target
echo "enabled navbot appliance for boot (navbot-nav left disabled)."

if [[ "${START_NOW}" -eq 1 ]]; then
  systemctl start navbot.target
  echo "started navbot.target."
  systemctl --no-pager --output=short status navbot-bringup.service navbot-web.service navbot-voice.service | sed -n '1,40p' || true
else
  echo "not started now. Reboot, or: sudo systemctl start navbot.target"
fi

cat <<EOF

Done. Useful commands:
  systemctl status navbot-voice.service
  journalctl -u navbot-voice.service -f      # follow the voice brain
  journalctl -u navbot-bringup.service -b    # this boot's bringup log
  sudo systemctl stop navbot.target          # halt the whole appliance
  sudo systemctl restart navbot-voice.service
Safety: drive mode is OFF on boot (SafetyGate); the robot won't move until asked,
and the on-device "stop" word + e-stop always override.
EOF
