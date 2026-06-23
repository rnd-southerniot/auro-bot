---
description: Gyro test — verify IMU gyro at rest (~0) and correct +CCW yaw sign on rotation
allowed-tools: Bash(ssh navbot-pi:*)
---

Run a **gyro test** on the navbot IMU (L3G4200D on Pi I²C-1, driver mode `x_forward_flipped`).

Confirm the Pi is reachable first (`ssh navbot-pi 'echo ok'`). NOTE: command output is not streamed live, so there is no usable real-time "GO" cue. Instead:
1. Tell the user: when they reply to start, **immediately begin rotating the whole robot in place counter-clockwise (turn LEFT, viewed from above) and keep rotating continuously and briskly for ~12 s** until you report back. (No need to lift wheels — rotate the chassis by hand.) Wait for their "go".
2. Then run (10 s continuous capture of all 3 gyro axes + accel Z):

```bash
ssh navbot-pi 'bash -l -s' <<'EOF'
set +u
source /opt/ros/jazzy/setup.bash
source ~/projects/claude-navbot/ros2_ws/install/setup.bash
pkill -f l3gd20 2>/dev/null; pkill -f complementary_filter 2>/dev/null; pkill -f imu_fusion 2>/dev/null; sleep 1
ros2 launch navbot_imu imu_fusion.launch.py > /tmp/gyro_test.log 2>&1 &
LPID=$!
sleep 8
python3 - <<'PY'
import rclpy, time
from sensor_msgs.msg import Imu
rclpy.init(); n=rclpy.create_node('gyroaxes')
gx=[];gy=[];gz=[];az=[]
def cb(m):
    gx.append(m.angular_velocity.x);gy.append(m.angular_velocity.y);gz.append(m.angular_velocity.z)
    az.append(m.linear_acceleration.z)
n.create_subscription(Imu,'/imu/data_raw',cb,50)
t=time.time()
while time.time()-t<10: rclpy.spin_once(n,timeout_sec=0.05)
def pk(v): return max(v,key=abs) if v else 0.0
print(f"samples={len(gz)}")
print(f"gyro peak  x={pk(gx):+.3f}  y={pk(gy):+.3f}  z={pk(gz):+.3f}  rad/s")
print(f"accel mean z={(sum(az)/len(az) if az else 0):+.2f}  (Z-up should be ~+9.8 to +11)")
axis=max([('x',pk(gx)),('y',pk(gy)),('z',pk(gz))],key=lambda kv:abs(kv[1]))
print(f"strongest rotation axis: gyro_{axis[0]} = {axis[1]:+.3f} rad/s")
if pk(gz)>0.3 and axis[0]=='z': print("VERDICT: CCW -> gyro_z POSITIVE (CORRECT, Z-up RH)")
elif pk(gz)<-0.3 and axis[0]=='z': print("VERDICT: CCW -> gyro_z NEGATIVE (yaw sign WRONG)")
elif axis[0]!='z': print(f"VERDICT: rotation appeared on gyro_{axis[0]} not gyro_z — orientation/remap wrong")
else: print("VERDICT: no clear rotation captured — re-run and rotate continuously")
n.destroy_node(); rclpy.shutdown()
PY
kill $LPID 2>/dev/null; sleep 2; pkill -f l3gd20 2>/dev/null; pkill -f complementary_filter 2>/dev/null; pkill -f imu_fusion 2>/dev/null
grep -iE "read failed|Remote I/O" /tmp/gyro_test.log | tail -2 || true
true
EOF
```

Interpret: PASS = strongest rotation on **gyro_z, positive** for CCW, and accel mean Z ≈ +10 (Z-up after the `x_forward_flipped` remap); confirms the IMU node is alive at ~50 Hz. If rotation lands on gyro_x/y, the orientation/remap is wrong; if gyro_z is negative, the yaw sign is wrong. If a `Remote I/O` line appears, the IMU dropped off I²C (reseat the connector).
