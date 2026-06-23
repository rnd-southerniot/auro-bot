---
description: Automatable pre-flight checks (reachability, serial by-id, i2c, ROS nodes, scan rate) — read-only, no motion
allowed-tools: Bash(ssh navbot-pi:*)
---

Run the **automatable** subset of the RUNBOOK pre-flight checklist and report.
This does NOT replace the human checklist in
[../../docs/RUNBOOK.md](../../docs/RUNBOOK.md#pre-flight-safety-checklist) —
battery-switch state, wheels-free, and estop reachability are physical checks
the operator must still confirm.

```bash
ssh navbot-pi 'bash -s' <<'EOF'
echo "== reachability =="; echo ok
echo "== serial by-id (expect Pico + CP2102) =="; ls /dev/serial/by-id/ 2>/dev/null || echo "none"
echo "== i2c-1 (expect 40 = INA238; 19/1e/69 = IMU if planned) =="; i2cdetect -y 1 2>/dev/null || echo "i2c-tools missing"
echo "== ROS nodes (should be EMPTY before a fresh bringup) =="; ros2 node list 2>/dev/null | sort || echo "ROS not sourced / not running"
echo "== serial port owner (raw /navbot:* commands conflict with a running bringup) =="
pgrep -af serial_bridge >/dev/null 2>&1 && echo "serial_bridge RUNNING -> use navbot_web API, not raw /navbot:* serial cmds" || echo "no serial_bridge -> raw /navbot:* serial commands are safe to use"
echo "== /scan rate (only if a lidar/bringup launch is up) =="; timeout 4 ros2 topic hz /scan 2>/dev/null | tail -2 || echo "/scan not active"
EOF
```

Interpret: PASS = both by-id devices present, INA238 at `0x40`, and the serial-
owner line matches your intended control path. A non-empty `ros2 node list`
before a fresh bringup means stale nodes — clear them first (RUNBOOK).
