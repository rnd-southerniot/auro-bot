---
description: Soft LEFT arc — drive forward while turning left (CMD_VEL 0.10 m/s, +0.4 rad/s)
allowed-tools: Bash(ssh navbot-pi:*)
---

Drive the navbot in a **gentle left arc** (forward 0.10 m/s + turn left 0.4 rad/s, radius ~0.25 m) for ~2.5 s, closed-loop.

SAFETY — do this first, every time:
1. Confirm the Pi is reachable (`ssh navbot-pi 'echo ok'`); if not, tell the user and stop.
2. **This MOVES the robot (forward + left curve).** Ask the user to confirm clear space ahead and to the left OR the robot is on blocks. WAIT for explicit "yes" before driving.

Then run:

```bash
ssh navbot-pi 'bash -s' <<'EOF'
python3 - <<'PY'
import serial, time
PORT='/dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00'
LIN, ANG, SECS = 0.10, 0.4, 2.5   # +ANG = left / CCW
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
print("RESULT:", "LEFT ARC OK (outer/right wheel travels more)" if dR>dL>0 and 'FAULT STALL' not in states else "review")
s.close()
PY
EOF
```

Interpret: PASS = both wheels forward but the **right (outer) wheel travels more than the left** (R delta > L delta), no `FAULT STALL`.
