#!/usr/bin/env bash
set -euo pipefail

# Quick health checkpoint during soak test.
# Run this via SSH every 30 minutes to verify system liveness.
#
# Usage:
#   ./scripts/soak_checkpoint.sh [web_console_port]
#   Default port: 8081

PORT="${1:-8081}"

echo "=== Navbot Checkpoint $(date -Iseconds) ==="
echo ""

# --- Web Console Status ---
echo "--- Web Console (port $PORT) ---"
STATUS=$(curl -sf "http://127.0.0.1:${PORT}/api/status" 2>/dev/null) || {
  echo "  *** FAIL: web console unreachable ***"
  STATUS=""
}

if [[ -n "$STATUS" ]]; then
  echo "$STATUS" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(f'  ROS alive:     {d[\"ros_bridge_alive\"]}')
    print(f'  Base alive:    {d[\"base_bridge_alive\"]}')
    print(f'  Scan alive:    {d[\"scan\"][\"alive\"]}')
    print(f'  IMU alive:     {d[\"imu\"][\"alive\"]}')
    print(f'  Power alive:   {d[\"power\"][\"alive\"]}')
    print(f'  Controller:    {d[\"controller\"][\"state\"]}')
    print(f'  Uptime:        {d[\"ros_uptime_sec\"]/3600:.2f}h')
    odom_age = d['odom'].get('age_sec')
    scan_age = d['scan'].get('age_sec')
    if odom_age is not None and odom_age > 1.0:
        print(f'  *** WARNING: odom age {odom_age:.1f}s (stale) ***')
    if scan_age is not None and scan_age > 1.0:
        print(f'  *** WARNING: scan age {scan_age:.1f}s (stale) ***')
except Exception as e:
    print(f'  Parse error: {e}')
"
fi
echo ""

# --- Bridge Health ---
echo "--- Bridge Health ---"
source /opt/ros/jazzy/setup.bash 2>/dev/null || true
HEALTH=$(timeout 3 ros2 topic echo /base/bridge_health --once 2>/dev/null) || {
  echo "  *** FAIL: bridge health topic unreachable ***"
  HEALTH=""
}

if [[ -n "$HEALTH" ]]; then
  echo "$HEALTH" | python3 -c "
import json, sys, re
for line in sys.stdin:
    line = line.strip()
    if line.startswith('data:'):
        raw = line[5:].strip().strip(\"'\").strip('\"')
        try:
            d = json.loads(raw)
            print(f'  Connected:     {d.get(\"serial_connected\")}')
            print(f'  FW version:    {d.get(\"firmware_version\")}')
            print(f'  Uptime:        {d.get(\"uptime_sec\", 0)/3600:.2f}h')
            print(f'  Reconnects:    {d.get(\"reconnect_count\")}')
            print(f'  Checksum fail: {d.get(\"checksum_failures\")}')
            print(f'  Latency:       {d.get(\"last_latency_ms\")}ms')
            odom_age = d.get('last_odom_age_sec')
            if odom_age is not None:
                print(f'  Odom age:      {odom_age:.3f}s')
        except (json.JSONDecodeError, TypeError) as e:
            print(f'  Parse error: {e}')
        break
"
fi
echo ""

# --- System Resources ---
echo "--- System ---"
echo "  Memory:"
free -m | head -2 | sed 's/^/    /'
echo "  Load:"
cat /proc/loadavg | sed 's/^/    /'
if [[ -f /sys/class/thermal/thermal_zone0/temp ]]; then
  TEMP=$(cat /sys/class/thermal/thermal_zone0/temp)
  echo "  Temperature: $((TEMP / 1000))°C"
fi
echo ""

# --- Kernel Warnings (last 30 min) ---
echo "--- Kernel Warnings (last 30 min) ---"
WARNINGS=$(journalctl -k --since "30 min ago" --no-pager 2>/dev/null \
  | grep -Ei "voltage|throttl|oom" | head -5)
if [[ -n "$WARNINGS" ]]; then
  echo "  *** WARNING: kernel issues detected ***"
  echo "$WARNINGS" | sed 's/^/    /'
else
  echo "  None"
fi
echo ""
echo "=== Checkpoint Complete ==="
