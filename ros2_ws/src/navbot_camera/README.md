# navbot_camera

The robot's **eyes**: the Pi Camera Module 3 (CSI) feed plus a frame-grab helper
the voice brain (`navbot_voice`) uses for `look()` / `describe_scene()`.

- **Driver:** the upstream `camera_ros` node (libcamera-native — correct for the
  Pi 5; `v4l2_camera` is fragile there). Install on the robot Pi with
  `sudo apt install ros-jazzy-camera-ros`.
- **`frame_grabber.py`** (this package): subscribes to `/camera/image_raw`, tracks
  fps/liveness, publishes JSON `/camera/status`, and serves
  `/camera/grab_frame` (`std_srvs/Trigger`) — saves the latest frame to a JPEG and
  returns its path (cv_bridge/OpenCV lazy-imported).

## Status: scaffolded; live camera-test deferred

Per the project decisions, the Pi Camera Module 3 isn't connected yet, so the
`/navbot:camera-test` live validation is deferred. The package builds and
`frame_grabber` runs status-only without a camera.

## Run

```bash
# Full (needs camera_ros + a connected CSI module):
ros2 launch navbot_camera camera.launch.py
# Grabber only (no driver/hardware):
ros2 launch navbot_camera camera.launch.py use_camera_driver:=false
```
