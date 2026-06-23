---
description: Emergency STOP — halt the robot now (serial STOP + zero CMD_VEL, then RESET clears faults)
allowed-tools: Bash(ssh navbot-pi:*)
---

Immediately **halt** the navbot. Safe to run any time; sends a stop, never motion.

1. Confirm the Pi is reachable (`ssh navbot-pi 'echo ok'`); if not, tell the user
   to use the **physical** estop / motor-rail power-off and stop here.
2. Note: this opens the Pico serial port directly. If a ROS bringup is running,
   prefer the web console red STOP / `POST /api/stop` (it owns the port). This
   command is the fallback for the stack-down / bench case.

```bash
ssh navbot-pi 'bash -s' <<'EOF'
python3 - <<'PY'
import serial, time
PORT='/dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00'
try:
    s=serial.Serial(PORT,115200,timeout=0.3)
except Exception as e:
    print("SERIAL BUSY/UNAVAILABLE:", e)
    print("If the ROS stack is up, use the web console STOP / POST /api/stop.")
    raise SystemExit(1)
time.sleep(0.2); s.reset_input_buffer()
for _ in range(3):
    s.write(b'STOP\n'); s.write(b'CMD_VEL 0.0 0.0\n'); time.sleep(0.1)
s.write(b'RESET\n'); time.sleep(0.3)   # clears latched ESTOP/STALL/RUN_TIMEOUT + CD fault
s.reset_input_buffer(); s.write(b'DIAG\n'); time.sleep(0.3)
state=[l.decode('utf-8','replace').strip() for l in s.readlines()
       if l.startswith(b'STATE')]
print("post-stop:", state[-1] if state else "(no STATE line — re-run DIAG)")
s.close()
PY
EOF
```

Interpret: expect `STATE IDLE OK` after the RESET. If it still shows a fault,
escalate to physical motor-rail power-off (see RUNBOOK → Incident Response).
