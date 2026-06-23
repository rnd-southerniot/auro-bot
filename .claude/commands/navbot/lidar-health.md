---
description: LiDAR health test — bring up sllidar, check health status + /scan_raw rate
allowed-tools: Bash(ssh navbot-pi:*)
---

Run a **LiDAR health test** on the navbot (RPLIDAR C1 on the CP2102 `/dev/ttyUSB0`). No motion.

Confirm the Pi is reachable first (`ssh navbot-pi 'echo ok'`), then run (launches sllidar, reads health + scan rate, then shuts it down):

```bash
ssh navbot-pi 'bash -l -s' <<'EOF'
set +u
source /opt/ros/jazzy/setup.bash
source ~/projects/claude-navbot/ros2_ws/install/setup.bash
pkill -f sllidar 2>/dev/null; pkill -f lidar.launch 2>/dev/null; sleep 1
ros2 launch navbot_lidar lidar.launch.py > /tmp/lidar_health.log 2>&1 &
LPID=$!
sleep 12
echo "=== health / model / mode ==="
grep -iE "health|firmware|hardware|S/N|scan mode|scan frequency" /tmp/lidar_health.log | tail -8
echo "=== /scan_raw rate ==="
timeout 8 ros2 topic hz /scan_raw --window 20 2>&1 | grep -E "average rate" | head -1 || echo "no /scan_raw data"
kill $LPID 2>/dev/null; sleep 2; pkill -f sllidar 2>/dev/null; pkill -f lidar.launch 2>/dev/null
echo "=== errors, if any ==="
grep -iE "error|fail|exception|denied" /tmp/lidar_health.log | head -5 || echo "(no errors)"
EOF
```

Interpret: PASS = `health status: OK` and `/scan_raw` at ~10 Hz (8–12 Hz). Note: bare `lidar.launch.py` publishes `/scan_raw`; `/scan` only exists when the scan_filter node runs (SLAM/nav bringup). Report PASS/FAIL plainly.
