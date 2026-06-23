---
description: Test RIGHT motor FORWARD (TEST_PWM, PID-bypassed) and verify encoder counts up
allowed-tools: Bash(ssh navbot-pi:*)
---

Test the **RIGHT motor driving FORWARD** on the navbot (RP2040 fw 1.3.0, motor M1).

SAFETY — do this first, every time:
1. Confirm the Pi is reachable (`ssh navbot-pi 'echo ok'`); if not, tell the user and stop.
2. **Ask the user to confirm the wheels are lifted/free**, and WAIT for an explicit "yes" before driving.

Then run (RIGHT at +30% duty for 3 s, TEST_PWM auto-stops):

```bash
ssh navbot-pi 'bash -s' <<'EOF'
python3 - <<'PY'
import serial, time
PORT='/dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00'
DUTY_L, DUTY_R, SECS = 0, 300, 3
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
    if time.time()-ls>=0.8:
        s.write(f'TEST_PWM {DUTY_L} {DUTY_R}\n'.encode()); ls=time.time()
    l=s.readline().decode('utf-8','replace').strip()
    if l.startswith('STATE'): states.add(' '.join(l.split()[1:3]))
s.write(b'STOP\n'); time.sleep(0.4)
e=odom(); dL,dR=(e[0] or bL)-bL,(e[1] or bR)-bR
print(f"LEFT delta={dL:+}  RIGHT delta={dR:+}")
print("DIRECTION:", "FORWARD(+)" if dR>0 else "REVERSE(-)" if dR<0 else "NO MOVEMENT")
print("states:", sorted(states))
s.close()
PY
EOF
```

Interpret: PASS = RIGHT delta clearly positive (> ~+50), LEFT ~0, no `FAULT STALL`. If NO MOVEMENT, suspect the M1 motor leads / loose terminal. Report plainly; leave motors stopped.
