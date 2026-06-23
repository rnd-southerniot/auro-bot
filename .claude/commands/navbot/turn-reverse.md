---
description: Turn in place ~180° to reverse heading (CMD_VEL 0.0 m/s, +0.6 rad/s)
allowed-tools: Bash(ssh navbot-pi:*)
---

Rotate the navbot **in place ~180°** (spin left/CCW at 0.6 rad/s for ~5.2 s) to face the reverse direction, closed-loop. The angle is open-loop / time-based, so treat ~180° as approximate.

SAFETY — do this first, every time:
1. Confirm the Pi is reachable (`ssh navbot-pi 'echo ok'`); if not, tell the user and stop.
2. **This ROTATES the robot in place.** Ask the user to confirm clear space around the robot (it sweeps its own footprint) OR the wheels are on blocks. WAIT for explicit "yes" before driving.

Then run:

```bash
ssh navbot-pi 'bash -s' <<'EOF'
python3 - <<'PY'
import serial, time
PORT='/dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00'
LIN, ANG, SECS = 0.0, 0.6, 5.2   # in-place CCW; ~pi rad at 0.6 rad/s
s=serial.Serial(PORT,115200,timeout=0.05); time.sleep(0.3); s.reset_input_buffer()
def odom():
    L=R=None; t=time.time()
    while time.time()-t<0.15:
        l=s.readline().decode('utf-8','replace').strip()
        if l.startswith('ODOM'):
            p=l.split()
            if len(p)>=4: L,R=int(p[2]),int(p[3])
    return L,R
s.write(b'RESET\n'); time.sleep(0.4)
b=odom(); bL,bR=b[0] or 0,b[1] or 0
t0=time.time(); ls=0; states=set()
while time.time()-t0<SECS:
    if time.time()-ls>=0.1:
        s.write(f'CMD_VEL {LIN} {ANG}\n'.encode()); ls=time.time()
    l=s.readline().decode('utf-8','replace').strip()
    if l.startswith('STATE'): states.add(' '.join(l.split()[1:3]))
s.write(b'STOP\n'); s.write(b'CMD_VEL 0.0 0.0\n'); time.sleep(0.5)
e=odom(); dL,dR=(e[0] or bL)-bL,(e[1] or bR)-bR
print(f"LEFT delta={dL:+}  RIGHT delta={dR:+}")
print("states:", sorted(states))
print("RESULT:", "IN-PLACE CCW OK (left back, right fwd)" if dL<0 and dR>0 and 'FAULT STALL' not in states else "review")
s.close()
PY
EOF
```

Interpret: PASS = in-place rotation pattern — **left wheel counts down, right wheel counts up** (CCW), roughly equal magnitude, no `FAULT STALL`. If 180° lands short/long, adjust `SECS` (rotation rate varies with battery/load).
