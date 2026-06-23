---
description: Check motor-rail voltage — RP2040 motor_v telemetry vs INA238 VBUS
allowed-tools: Bash(ssh navbot-pi:*)
---

Check the **motor power rail voltage** on the navbot. No motion — read-only.

Confirm the Pi is reachable first (`ssh navbot-pi 'echo ok'`), then run:

```bash
ssh navbot-pi 'bash -s' <<'EOF'
echo "=== INA238 VBUS (motor rail @ sensor, 0x40) ==="
python3 - <<'PY'
try:
    from smbus2 import SMBus
except Exception:
    from smbus import SMBus
def rd16(b,r):
    w=b.read_word_data(0x40,r); return ((w&0xFF)<<8)|(w>>8)
with SMBus(1) as b:
    print(f"INA238 VBUS = {rd16(b,0x05)*3.125e-3:.3f} V")
PY
echo "=== RP2040 VBAT telemetry (motor_v lidar_v), 3 samples ==="
python3 - <<'PY'
import serial, time
s=serial.Serial('/dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00',115200,timeout=1)
time.sleep(0.3); s.reset_input_buffer(); n=0; t=time.time()
while time.time()-t<3.5 and n<3:
    l=s.readline().decode('utf-8','replace').strip()
    if l.startswith('VBAT'):
        p=l.split(); print(f"motor_v={p[2]} V   lidar_v={p[3]} V"); n+=1
s.close()
PY
EOF
```

Interpret:
- INA238 VBUS is the trustworthy motor-rail reading (expect ~6.27 V; confirm vs nominal).
- The RP2040 `motor_v` is currently expected to read **false ~0.085 V** — the GP27 sense divider is disconnected (known open item). Note this discrepancy; it does NOT affect driving (`motor_v` is telemetry-only). If `motor_v` ever reads ~6 V, the GP27 sense wire has been reconnected.
