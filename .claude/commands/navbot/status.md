---
description: Read-only health snapshot — prefers the ROS /api/status when the stack is up, serial PING/DIAG when it is down
allowed-tools: Bash(ssh navbot-pi:*)
---

Report navbot health **without moving it**. Picks the non-conflicting path:
web console if running, otherwise direct serial. No motion is ever commanded.

1. Confirm the Pi is reachable (`ssh navbot-pi 'echo ok'`); if not, say so and stop.

```bash
ssh navbot-pi 'bash -s' <<'EOF'
# 1) Preferred: web console snapshot (does NOT touch the serial port).
for p in 8081 8080; do
  if curl -fsS "http://127.0.0.1:$p/api/status" 2>/dev/null \
       | python3 -m json.tool 2>/dev/null; then
    echo "[status via navbot_web :$p]"; exit 0
  fi
done
# 2) Stack down? Read serial directly (safe: PING + DIAG only).
echo "[no web console — reading RP2040 serial directly]"
python3 - <<'PY'
import serial, time
PORT='/dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00'
try:
    s=serial.Serial(PORT,115200,timeout=0.4)
except Exception as e:
    print("SERIAL UNAVAILABLE (a ROS node may own the port):", e); raise SystemExit(0)
time.sleep(0.2); s.reset_input_buffer()
s.write(b'PING\n'); s.write(b'DIAG\n'); time.sleep(0.6)
for l in s.readlines():
    t=l.decode('utf-8','replace').strip()
    if t.split(' ',1)[0] in ('ACK','STATE','VBAT','ODOM','ERR'): print(t)
s.close()
PY
EOF
```

Interpret: healthy bench state is `ACK PING 1.3.0` + `STATE IDLE OK`. Via the
web console, check `controller.state == "IDLE OK"` and that `odom`/`scan`/`imu`
report `alive: true`.
