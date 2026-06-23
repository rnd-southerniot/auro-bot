#!/usr/bin/env bash
set -euo pipefail

# Navbot soak test monitor — runs alongside the full ROS stack.
# Records bridge health, topic rates, system metrics, and DIAG telemetry.
#
# Usage:
#   ./scripts/soak_test.sh [duration_hours]
#   Default: 8 hours
#
# Prerequisites:
#   - ROS 2 stack running (imu_localization.launch.py)
#   - Web console running
#   - RP2040 connected and bridge active

DURATION_HOURS="${1:-8}"
DURATION_SEC=$((DURATION_HOURS * 3600))
LOG_DIR="$HOME/navbot_soak_$(date +%Y%m%d_%H%M%S)"
RP2040_PORT="/dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00"

mkdir -p "$LOG_DIR"
echo "Soak test: ${DURATION_HOURS}h, logging to ${LOG_DIR}"
echo "Start: $(date -Iseconds)" > "$LOG_DIR/soak_meta.txt"
echo "Duration target: ${DURATION_HOURS}h" >> "$LOG_DIR/soak_meta.txt"

source /opt/ros/jazzy/setup.bash 2>/dev/null || true

# Bridge health every 10s
(while true; do
  ros2 topic echo /base/bridge_health --once 2>/dev/null \
    >> "$LOG_DIR/bridge_health.jsonl" || true
  sleep 10
done) &
PIDS=$!

# Topic rates every 60s
(while true; do
  echo "--- $(date -Iseconds) ---" >> "$LOG_DIR/topic_rates.log"
  timeout 5 ros2 topic hz /odom --window 20 2>&1 | head -1 \
    >> "$LOG_DIR/topic_rates.log" || true
  timeout 5 ros2 topic hz /scan --window 20 2>&1 | head -1 \
    >> "$LOG_DIR/topic_rates.log" || true
  timeout 5 ros2 topic hz /imu/l3gd20_lsm303d/raw --window 20 2>&1 | head -1 \
    >> "$LOG_DIR/topic_rates.log" || true
  sleep 60
done) &
PIDS="$PIDS $!"

# System metrics every 30s
(while true; do
  echo "--- $(date -Iseconds) ---" >> "$LOG_DIR/system.log"
  free -m | head -2 >> "$LOG_DIR/system.log"
  cat /proc/loadavg >> "$LOG_DIR/system.log"
  cat /sys/class/thermal/thermal_zone0/temp >> "$LOG_DIR/system.log" 2>/dev/null || true
  journalctl -k --since "1 min ago" --no-pager 2>/dev/null \
    | grep -Ei "voltage|throttl|oom" >> "$LOG_DIR/kernel_warnings.log" || true
  sleep 30
done) &
PIDS="$PIDS $!"

# DIAG command every 5 minutes (only if serial port not exclusively held by bridge)
(while true; do
  echo "--- $(date -Iseconds) ---" >> "$LOG_DIR/diag.log"
  python3 -c "
import serial, time
try:
    s = serial.Serial('${RP2040_PORT}', 115200, timeout=1)
    s.write(b'DIAG\n')
    time.sleep(0.3)
    while s.in_waiting:
        print(s.readline().decode('utf-8', errors='replace').strip())
    s.close()
except Exception as e:
    print(f'DIAG probe skipped: {e}')
" >> "$LOG_DIR/diag.log" 2>&1
  sleep 300
done) &
PIDS="$PIDS $!"

cleanup() {
  for pid in $PIDS; do
    kill "$pid" 2>/dev/null || true
  done
  echo "End: $(date -Iseconds)" >> "$LOG_DIR/soak_meta.txt"
  echo ""
  echo "Soak test complete. Logs in: $LOG_DIR"
  echo "Run post-soak analysis:"
  echo "  cd $LOG_DIR"
  echo "  # Check disconnections:"
  echo "  grep -c '\"serial_connected\": false' bridge_health.jsonl"
  echo "  # Check kernel warnings:"
  echo "  cat kernel_warnings.log"
}
trap cleanup EXIT INT TERM

echo "Monitoring active. Will run for ${DURATION_HOURS}h."
echo "Press Ctrl+C to stop early."
echo "Logs: $LOG_DIR"
sleep "$DURATION_SEC"
