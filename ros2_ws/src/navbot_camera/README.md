# navbot_camera

The robot's **eyes**: a Seeed **XIAO ESP32-S3 Sense** Wi-Fi camera board plus a
frame-grab helper the voice brain (`navbot_voice`) uses for `look()` /
`describe_scene()`.

The camera is **not** a CSI Pi-camera — it's the ESP32-S3 Sense firmware in
[`firmware/xiao_esp32s3_sense_cam`](../../../firmware/xiao_esp32s3_sense_cam),
which joins the robot's Wi-Fi (AP `Auro_IoT`) and serves JPEG over HTTP:

- `GET <camera_url>/snapshot` — single JPEG (control plane, `:80`)
- `GET <camera_url>:81/stream` — live MJPEG (not used by `look()`)
- `GET <camera_url>/status` — JSON health (`fps`, `motion`, `rssi_dbm`, `uptime_s`, …)

Because the board already emits compressed JPEG, the Pi side does **no** image
decode: there is no `camera_ros`, `cv_bridge`, or OpenCV dependency — just an HTTP
relay.

- **`frame_grabber.py`** (this package): polls the XIAO `/status` for liveness,
  publishes JSON `/camera/status` (same idiom as `navbot_power`'s INA238 status),
  and serves `/camera/grab_frame` (`std_srvs/Trigger`) — fetches a fresh
  `/snapshot`, saves the JPEG, and returns its path.

## Configure the board address

The XIAO takes a DHCP lease on the robot's AP. Set `camera_url` in
[`config/camera.yaml`](config/camera.yaml) (confirmed `192.168.68.107` on
2026-06-26), or override at launch.

## Run

```bash
ros2 launch navbot_camera camera.launch.py
# or point at a different board address:
ros2 launch navbot_camera camera.launch.py camera_url:=http://192.168.68.107
```

Quick check the board directly (no ROS):

```bash
curl -s http://192.168.68.107/status
curl -s http://192.168.68.107/snapshot -o frame.jpg   # valid JFIF JPEG
```
