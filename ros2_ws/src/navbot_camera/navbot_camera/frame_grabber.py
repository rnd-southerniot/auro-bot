"""navbot_camera frame grabber.

Subscribes to the camera stream (published by the upstream ``camera_ros`` node),
tracks liveness/fps, publishes a JSON ``/camera/status`` (same idiom as
``navbot_power``'s INA238 status), and offers a ``/camera/grab_frame``
(``std_srvs/Trigger``) service that saves the latest frame to a JPEG and returns
its path — used by the voice brain's ``look()`` / ``describe_scene()`` tool.

cv_bridge/OpenCV are imported lazily so the node builds and runs (status-only)
even on a machine without them; grab_frame degrades gracefully if absent.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String
from std_srvs.srv import Trigger


class FrameGrabber(Node):
    def __init__(self) -> None:
        super().__init__("navbot_camera_frame_grabber")

        self.declare_parameter("image_topic", "/camera/image_raw")
        self.declare_parameter("status_period", 1.0)
        self.declare_parameter("save_dir", str(Path.home() / "navbot_captures" / "frames"))

        self.image_topic = str(self.get_parameter("image_topic").value)
        self.save_dir = Path(str(self.get_parameter("save_dir").value)).expanduser()
        period = float(self.get_parameter("status_period").value)

        self._last_msg: Image | None = None
        self._last_stamp: float | None = None
        self._frame_count = 0
        self._fps_window_start = time.monotonic()
        self._fps = 0.0
        self._width = 0
        self._height = 0
        self._encoding = ""

        self.create_subscription(Image, self.image_topic, self._image_cb, 10)
        self._status_pub = self.create_publisher(String, "/camera/status", 10)
        self.create_service(Trigger, "/camera/grab_frame", self._grab_cb)
        self.create_timer(period, self._publish_status)

        self.get_logger().info(
            f"navbot_camera frame_grabber on {self.image_topic} "
            f"(grab service /camera/grab_frame, save_dir {self.save_dir})"
        )

    def _image_cb(self, msg: Image) -> None:
        self._last_msg = msg
        self._last_stamp = time.monotonic()
        self._frame_count += 1
        self._width, self._height, self._encoding = msg.width, msg.height, msg.encoding
        now = time.monotonic()
        elapsed = now - self._fps_window_start
        if elapsed >= 1.0:
            self._fps = self._frame_count / elapsed
            self._frame_count = 0
            self._fps_window_start = now

    def _alive(self) -> bool:
        return self._last_stamp is not None and (time.monotonic() - self._last_stamp) < 2.0

    def _publish_status(self) -> None:
        payload = {
            "available": self._alive(),
            "topic": self.image_topic,
            "fps": round(self._fps, 2),
            "width": self._width,
            "height": self._height,
            "encoding": self._encoding,
            "message": "streaming" if self._alive() else "no frames",
        }
        self._status_pub.publish(String(data=json.dumps(payload)))

    def _grab_cb(self, request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        if self._last_msg is None:
            response.success = False
            response.message = "no frame received yet"
            return response
        try:
            from cv_bridge import CvBridge  # lazy
            import cv2  # lazy
        except Exception as exc:  # pragma: no cover - env dependent
            response.success = False
            response.message = f"cv_bridge/opencv unavailable: {exc}"
            return response
        try:
            self.save_dir.mkdir(parents=True, exist_ok=True)
            frame = CvBridge().imgmsg_to_cv2(self._last_msg, desired_encoding="bgr8")
            path = self.save_dir / f"frame_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
            cv2.imwrite(str(path), frame)
            response.success = True
            response.message = str(path)
        except Exception as exc:  # pragma: no cover - runtime path
            response.success = False
            response.message = f"grab failed: {exc}"
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
