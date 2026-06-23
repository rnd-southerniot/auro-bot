---
description: Check LiDAR-rail voltage via RP2040 lidar_v telemetry (GP28)
allowed-tools: Bash(ssh navbot-pi:*)
---

Check the **LiDAR power rail voltage** on the navbot. No motion — read-only.

Confirm the Pi is reachable first (`ssh navbot-pi 'echo ok'`), then run:

```bash
ssh navbot-pi 'bash -s' <<'EOF'
python3 - <<'PY'
import serial, time
s=serial.Serial('/dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00',115200,timeout=1)
time.sleep(0.3); s.reset_input_buffer()
vals=[]; t=time.time()
while time.time()-t<4 and len(vals)<4:
    l=s.readline().decode('utf-8','replace').strip()
    if l.startswith('VBAT'):
        p=l.split(); lv=p[3].split('*')[0]; vals.append(float(lv)); print(f"lidar_v={lv} V  (motor_v={p[2]} V)")
if vals:
    print(f"avg lidar_v = {sum(vals)/len(vals):.3f} V")
s.close()
PY
EOF
```

Interpret: the RP2040 `lidar_v` ADC (GP28) sense line is intact (unlike motor_v); expect ~4.9 V. PASS = stable reading in the expected band. A reading near 0 would mean the LiDAR rail is off or the GP28 sense line dropped.
