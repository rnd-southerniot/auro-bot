"""navbot_camera networked-frame grabber (P6 perception).

The robot's **eyes** are a Seeed **XIAO ESP32-S3 Sense** on Wi-Fi serving JPEG
over HTTP (``firmware/xiao_esp32s3_sense_cam``) — not a CSI Pi-camera. This node
is the ROS-side face of that camera: it polls the XIAO's ``/status`` for liveness
and republishes a JSON ``/camera/status`` (same idiom as ``navbot_power``'s INA238
status), and offers a ``/camera/grab_frame`` (``std_srvs/Trigger``) service that
fetches a fresh ``/snapshot`` JPEG, saves it, and returns the path — used by the
voice brain's ``look()`` / ``describe_scene()`` tool.

Because the XIAO already serves compressed JPEG, there is **no decode step** here:
no ``camera_ros``, ``cv_bridge``, or OpenCV. We just relay bytes. Stdlib ``urllib``
only.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger


class FrameGrabber(Node):
    def __init__(self) -> None:
        super().__init__("navbot_camera_frame_grabber")

        # XIAO ESP32-S3 Sense base URL (control plane, :80). The MJPEG stream
        # lives on :81/stream but look() only needs a still, so we use /snapshot.
        self.declare_parameter("camera_url", "http://192.168.68.107")
        self.declare_parameter("snapshot_path", "/snapshot")
        self.declare_parameter("status_path", "/status")
        self.declare_parameter("http_timeout", 4.0)
        self.declare_parameter("status_period", 2.0)
        self.declare_parameter("save_dir", str(Path.home() / "navbot_captures" / "frames"))

        self.base_url = str(self.get_parameter("camera_url").value).rstrip("/")
        self.snapshot_path = str(self.get_parameter("snapshot_path").value)
        self.status_path = str(self.get_parameter("status_path").value)
        self.timeout = float(self.get_parameter("http_timeout").value)
        self.save_dir = Path(str(self.get_parameter("save_dir").value)).expanduser()
        period = float(self.get_parameter("status_period").value)

        self._last_ok: float | None = None
        self._last_cam_status: dict = {}
        self._last_error = ""

        self._status_pub = self.create_publisher(String, "/camera/status", 10)
        self.create_service(Trigger, "/camera/grab_frame", self._grab_cb)
        self.create_timer(period, self._publish_status)

        self.get_logger().info(
            f"navbot_camera frame_grabber -> XIAO camera at {self.base_url} "
            f"(snapshot {self.snapshot_path}, grab service /camera/grab_frame, "
            f"save_dir {self.save_dir})"
        )

    # ---- HTTP helpers (stdlib only) ----
    def _get(self, path: str) -> bytes:
        url = f"{self.base_url}{path}"
        with urllib.request.urlopen(url, timeout=self.timeout) as resp:
            return resp.read()

    def _poll_camera_status(self) -> None:
        try:
            raw = self._get(self.status_path)
            self._last_cam_status = json.loads(raw.decode("utf-8")) if raw else {}
            self._last_ok = time.monotonic()
            self._last_error = ""
        except (urllib.error.URLError, OSError, ValueError) as exc:
            self._last_error = str(exc)

    def _alive(self) -> bool:
        return self._last_ok is not None and (time.monotonic() - self._last_ok) < 5.0

    def _publish_status(self) -> None:
        self._poll_camera_status()
        cam = self._last_cam_status
        payload = {
            "available": self._alive(),
            "url": self.base_url,
            "fps": cam.get("fps"),
            "framesize": cam.get("framesize"),
            "motion": cam.get("motion"),
            "rssi_dbm": cam.get("rssi_dbm"),
            "uptime_s": cam.get("uptime_s"),
            "message": "online" if self._alive() else (self._last_error or "unreachable"),
        }
        self._status_pub.publish(String(data=json.dumps(payload)))

    def _grab_cb(self, request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        try:
            jpeg = self._get(self.snapshot_path)
        except (urllib.error.URLError, OSError) as exc:
            response.success = False
            response.message = f"snapshot fetch failed ({self.base_url}{self.snapshot_path}): {exc}"
            return response
        if not (jpeg[:3] == b"\xff\xd8\xff"):  # JFIF SOI marker
            response.success = False
            response.message = f"snapshot was not a JPEG (got {len(jpeg)} bytes)"
            return response
        try:
            self.save_dir.mkdir(parents=True, exist_ok=True)
            path = self.save_dir / f"frame_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
            path.write_bytes(jpeg)
            response.success = True
            response.message = str(path)
        except OSError as exc:
            response.success = False
            response.message = f"save failed: {exc}"
        return response


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = FrameGrabber()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
