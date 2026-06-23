import json
import math
import time

import rclpy
from geometry_msgs.msg import Twist, Vector3Stamped
from rclpy.node import Node
from std_msgs.msg import Bool, Float32, String


def _wrap_pi(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class HeadingControllerNode(Node):
    """Closed-loop compass heading target controller.

    Targets are radians in the same yaw frame as /imu/l3gd20_lsm303d/ypr
    where vector.x is yaw. The node is passive until it receives either an
    absolute target or a relative target.
    """

    def __init__(self) -> None:
        super().__init__("navbot_heading_controller")

        self.declare_parameter("heading_topic", "/imu/l3gd20_lsm303d/ypr")
        self.declare_parameter("absolute_target_topic", "/heading_controller/target")
        self.declare_parameter("relative_target_topic", "/heading_controller/relative")
        self.declare_parameter("cancel_topic", "/heading_controller/cancel")
        self.declare_parameter("cmd_vel_topic", "/cmd_vel")
        self.declare_parameter("status_topic", "/heading_controller/status")
        self.declare_parameter("control_hz", 20.0)
        self.declare_parameter("kp", 0.8)
        self.declare_parameter("max_angular_z", 0.35)
        self.declare_parameter("min_angular_z", 0.14)
        self.declare_parameter("heading_tolerance_rad", 0.06)
        self.declare_parameter("settle_samples", 4)
        self.declare_parameter("target_timeout_sec", 25.0)
        self.declare_parameter("heading_stale_timeout_sec", 0.5)
        self.declare_parameter("command_sign", 1.0)
        self.declare_parameter("status_hz", 4.0)

        self.heading_topic = str(self.get_parameter("heading_topic").value)
        absolute_target_topic = str(self.get_parameter("absolute_target_topic").value)
        relative_target_topic = str(self.get_parameter("relative_target_topic").value)
        cancel_topic = str(self.get_parameter("cancel_topic").value)
        cmd_vel_topic = str(self.get_parameter("cmd_vel_topic").value)
        status_topic = str(self.get_parameter("status_topic").value)

        self.kp = float(self.get_parameter("kp").value)
        self.max_angular_z = abs(float(self.get_parameter("max_angular_z").value))
        self.min_angular_z = abs(float(self.get_parameter("min_angular_z").value))
        self.heading_tolerance_rad = abs(float(self.get_parameter("heading_tolerance_rad").value))
        self.settle_samples = max(1, int(self.get_parameter("settle_samples").value))
        self.target_timeout_sec = max(0.1, float(self.get_parameter("target_timeout_sec").value))
        self.heading_stale_timeout_sec = max(
            0.1, float(self.get_parameter("heading_stale_timeout_sec").value)
        )
        self.command_sign = 1.0 if float(self.get_parameter("command_sign").value) >= 0.0 else -1.0
        status_hz = max(0.1, float(self.get_parameter("status_hz").value))
        self.status_period_sec = 1.0 / status_hz

        self._yaw: float | None = None
        self._yaw_stamp: float | None = None
        self._target_yaw: float | None = None
        self._target_started: float | None = None
        self._settle_count = 0
        self._last_status_time = 0.0
        self._last_error: float | None = None
        self._active_mode = "idle"

        self._cmd_pub = self.create_publisher(Twist, cmd_vel_topic, 10)
        self._status_pub = self.create_publisher(String, status_topic, 10)
        self.create_subscription(Vector3Stamped, self.heading_topic, self._heading_cb, 20)
        self.create_subscription(Float32, absolute_target_topic, self._absolute_target_cb, 10)
        self.create_subscription(Float32, relative_target_topic, self._relative_target_cb, 10)
        self.create_subscription(Bool, cancel_topic, self._cancel_cb, 10)

        control_hz = max(1.0, float(self.get_parameter("control_hz").value))
        self.create_timer(1.0 / control_hz, self._control_cb)
        self.get_logger().info("navbot heading controller ready")

    def _heading_cb(self, msg: Vector3Stamped) -> None:
        self._yaw = _wrap_pi(float(msg.vector.x))
        self._yaw_stamp = time.monotonic()

    def _absolute_target_cb(self, msg: Float32) -> None:
        self._start_target(_wrap_pi(float(msg.data)), "absolute")

    def _relative_target_cb(self, msg: Float32) -> None:
        if self._yaw is None or self._heading_stale():
            self._publish_status("ERROR", message="heading unavailable for relative target")
            return
        self._start_target(_wrap_pi(self._yaw + float(msg.data)), "relative")

    def _cancel_cb(self, msg: Bool) -> None:
        if bool(msg.data) and self._target_yaw is not None:
            self._stop("CANCELLED", "cancel requested")

    def _start_target(self, target_yaw: float, mode: str) -> None:
        self._target_yaw = target_yaw
        self._target_started = time.monotonic()
        self._settle_count = 0
        self._last_error = None
        self._active_mode = mode
        self._publish_status("ACTIVE", force=True)

    def _control_cb(self) -> None:
        if self._target_yaw is None:
            message = "heading stale" if self._heading_stale() else ""
            self._publish_status("IDLE", message=message)
            return

        if self._heading_stale():
            self._stop("ERROR", "heading stale")
            return

        assert self._yaw is not None
        assert self._target_started is not None
        now = time.monotonic()
        if now - self._target_started > self.target_timeout_sec:
            self._stop("TIMEOUT", "target timeout")
            return

        error = _wrap_pi(self._target_yaw - self._yaw)
        self._last_error = error
        if abs(error) <= self.heading_tolerance_rad:
            self._publish_twist(0.0)
            self._settle_count += 1
            if self._settle_count >= self.settle_samples:
                self._stop("REACHED", "target reached")
            else:
                self._publish_status("SETTLING")
            return

        self._settle_count = 0
        angular = self.kp * error
        angular = _clamp(angular, -self.max_angular_z, self.max_angular_z)
        if 0.0 < abs(angular) < self.min_angular_z:
            angular = math.copysign(self.min_angular_z, angular)
        self._publish_twist(self.command_sign * angular)
        self._publish_status("ACTIVE")

    def _heading_stale(self) -> bool:
        return self._yaw_stamp is None or (time.monotonic() - self._yaw_stamp) > self.heading_stale_timeout_sec

    def _publish_twist(self, angular_z: float) -> None:
        msg = Twist()
        msg.angular.z = float(angular_z)
        self._cmd_pub.publish(msg)

    def _stop(self, state: str, message: str) -> None:
        self._publish_twist(0.0)
        self._publish_status(state, message=message, force=True)
        self._target_yaw = None
        self._target_started = None
        self._settle_count = 0
        self._active_mode = "idle"

    def _publish_status(self, state: str, message: str = "", force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_status_time < self.status_period_sec:
            return
        self._last_status_time = now
        payload = {
            "state": state,
            "message": message,
            "mode": self._active_mode,
            "yaw_rad": self._yaw,
            "target_yaw_rad": self._target_yaw,
            "error_rad": self._last_error,
            "heading_topic": self.heading_topic,
        }
        msg = String()
        msg.data = json.dumps(payload, sort_keys=True)
        self._status_pub.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = HeadingControllerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
