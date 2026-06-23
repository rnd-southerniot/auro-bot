import math
import time
from typing import Optional

import json

import rclpy
from geometry_msgs.msg import Quaternion, TransformStamped, Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool, Float32, String
from tf2_ros import TransformBroadcaster

from .checksum import append_checksum, validate_and_strip_checksum
from .odometry import DifferentialDriveOdometry

try:
    import serial
    from serial import SerialException
except ImportError:  # pragma: no cover - depends on target environment
    serial = None

    class SerialException(Exception):
        pass


SERIAL_ERRORS = (SerialException, OSError)


class SerialBridgeNode(Node):
    """ROS 2 bridge between /cmd_vel and the RP2040 line-based serial protocol."""

    def __init__(self) -> None:
        super().__init__("navbot_serial_bridge")

        self.declare_parameter("serial_port", "/dev/ttyACM0")
        self.declare_parameter("baud_rate", 115200)
        self.declare_parameter("wheel_radius", 0.033)
        self.declare_parameter("wheel_separation", 0.160)
        self.declare_parameter("counts_per_revolution", 3945)
        self.declare_parameter("left_counts_per_revolution", 3943)
        self.declare_parameter("right_counts_per_revolution", 3946)
        self.declare_parameter("command_timeout", 0.5)
        self.declare_parameter("odom_frame", "odom")
        self.declare_parameter("base_frame", "base_footprint")
        self.declare_parameter("base_link_frame", "base_link")
        self.declare_parameter("laser_frame", "laser_link")
        self.declare_parameter("publish_tf", True)
        self.declare_parameter("zero_command_deadband", 1.0e-4)

        self.serial_port = self.get_parameter("serial_port").value
        self.baud_rate = int(self.get_parameter("baud_rate").value)
        self.wheel_radius = float(self.get_parameter("wheel_radius").value)
        self.wheel_separation = float(self.get_parameter("wheel_separation").value)
        self.counts_per_revolution = int(self.get_parameter("counts_per_revolution").value)
        self.left_counts_per_revolution = int(self.get_parameter("left_counts_per_revolution").value)
        self.right_counts_per_revolution = int(self.get_parameter("right_counts_per_revolution").value)
        self.command_timeout = float(self.get_parameter("command_timeout").value)
        self.odom_frame = self.get_parameter("odom_frame").value
        self.base_frame = self.get_parameter("base_frame").value
        self.base_link_frame = self.get_parameter("base_link_frame").value
        self.laser_frame = self.get_parameter("laser_frame").value
        self.publish_tf = bool(self.get_parameter("publish_tf").value)
        self.zero_command_deadband = float(self.get_parameter("zero_command_deadband").value)

        self._serial = None
        self._last_connect_attempt = 0.0
        self._last_connect_log = 0.0
        self._latest_twist = Twist()
        self._latest_twist_time: Optional[float] = None
        self._stop_sent = False
        self._firmware_version: Optional[str] = None
        self._checksum_failures = 0
        self._reconnect_count = 0
        self._start_time = time.monotonic()
        self._ping_sent_time: Optional[float] = None
        self._last_latency_ms: Optional[float] = None
        self._last_odom_time: Optional[float] = None

        self._odometry = DifferentialDriveOdometry(
            wheel_radius=self.wheel_radius,
            wheel_separation=self.wheel_separation,
            counts_per_revolution=self.counts_per_revolution,
            left_counts_per_revolution=self.left_counts_per_revolution,
            right_counts_per_revolution=self.right_counts_per_revolution,
        )

        self.odom_pub = self.create_publisher(Odometry, "/odom", 20)
        self.joint_state_pub = self.create_publisher(JointState, "/joint_states", 20)
        self.controller_state_pub = self.create_publisher(String, "/base/controller_state", 10)
        self.estop_pub = self.create_publisher(Bool, "/base/estop", 10)
        self.latency_pub = self.create_publisher(Float32, "/base/serial_latency_ms", 10)
        self.health_pub = self.create_publisher(String, "/base/bridge_health", 10)
        self.motor_voltage_pub = self.create_publisher(Float32, "/base/motor_voltage", 10)
        self.lidar_voltage_pub = self.create_publisher(Float32, "/base/lidar_voltage", 10)
        self.tf_broadcaster = TransformBroadcaster(self) if self.publish_tf else None

        self.create_subscription(Twist, "/cmd_vel", self._cmd_vel_callback, 20)
        self.create_timer(0.05, self._write_timer_callback)
        self.create_timer(0.02, self._read_timer_callback)
        self.create_timer(5.0, self._ping_timer_callback)
        self.create_timer(1.0, self._health_timer_callback)

        self.get_logger().info("navbot serial bridge started")

    def _cmd_vel_callback(self, msg: Twist) -> None:
        self._latest_twist = msg
        self._latest_twist_time = time.monotonic()
        self._stop_sent = False

    def _connect_serial(self) -> None:
        if self._serial is not None:
            return

        now = time.monotonic()
        if now - self._last_connect_attempt < 1.0:
            return
        self._last_connect_attempt = now

        if serial is None:
            if now - self._last_connect_log > 5.0:
                self.get_logger().error("pyserial is not installed; serial bridge is inactive")
                self._last_connect_log = now
            return

        try:
            port = serial.Serial(self.serial_port, self.baud_rate, timeout=0.5)
            port.reset_input_buffer()

            # Reconnect handshake: STOP to ensure known state, PING to verify.
            port.write(append_checksum("STOP").encode("utf-8") + b"\n")
            port.write(append_checksum("PING").encode("utf-8") + b"\n")

            # Wait for ACK PING (with firmware version).
            handshake_ok = False
            deadline = time.monotonic() + 1.5
            while time.monotonic() < deadline:
                raw = port.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="ignore").strip()
                payload, _ = validate_and_strip_checksum(line)
                if payload.startswith("ACK PING"):
                    handshake_ok = True
                    tokens = payload.split()
                    if len(tokens) >= 3:
                        self._firmware_version = tokens[2]
                    break

            if not handshake_ok:
                self.get_logger().warn("handshake failed: no ACK PING received, retrying")
                port.close()
                return

            # Switch to non-blocking for normal operation.
            port.timeout = 0.0
            self._serial = port
            self._reconnect_count += 1
            version_str = f" (firmware {self._firmware_version})" if self._firmware_version else ""
            self.get_logger().info(
                f"connected to {self.serial_port} @ {self.baud_rate}{version_str}"
                f" (connect #{self._reconnect_count})"
            )
            self._stop_sent = False
        except SERIAL_ERRORS as exc:
            if now - self._last_connect_log > 5.0:
                self.get_logger().warn(f"waiting for serial device {self.serial_port}: {exc}")
                self._last_connect_log = now

    def _close_serial(self) -> None:
        if self._serial is None:
            return
        try:
            self._serial.close()
        except SERIAL_ERRORS:
            pass
        self._serial = None

    def _write_line(self, line: str) -> None:
        self._connect_serial()
        if self._serial is None:
            return

        try:
            self._serial.write((append_checksum(line) + "\n").encode("utf-8"))
        except SERIAL_ERRORS as exc:
            self.get_logger().error(f"serial write failed: {exc}")
            self._close_serial()

    def _write_timer_callback(self) -> None:
        self._connect_serial()
        if self._serial is None:
            return

        now = time.monotonic()
        command_is_fresh = (
            self._latest_twist_time is not None
            and (now - self._latest_twist_time) <= self.command_timeout
        )

        if not command_is_fresh:
            if not self._stop_sent:
                self._write_line("STOP")
                self._publish_controller_state("STOP timeout_or_idle")
                self._stop_sent = True
            return

        linear = self._latest_twist.linear.x
        angular = self._latest_twist.angular.z
        if abs(linear) <= self.zero_command_deadband and abs(angular) <= self.zero_command_deadband:
            if not self._stop_sent:
                self._write_line("STOP")
                self._publish_controller_state("STOP zero_cmd")
                self._stop_sent = True
            return

        self._write_line(f"CMD_VEL {linear:.4f} {angular:.4f}")
        self._stop_sent = False

    def _read_timer_callback(self) -> None:
        self._connect_serial()
        if self._serial is None:
            return

        for _ in range(20):
            try:
                waiting = self._serial.in_waiting
            except SERIAL_ERRORS as exc:
                self.get_logger().error(f"serial read readiness failed: {exc}")
                self._close_serial()
                return

            if waiting <= 0:
                return

            try:
                raw_line = self._serial.readline()
            except SERIAL_ERRORS as exc:
                self.get_logger().error(f"serial read failed: {exc}")
                self._close_serial()
                return

            if not raw_line:
                return

            line = raw_line.decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            payload, checksum_valid = validate_and_strip_checksum(line)
            if not checksum_valid:
                self._checksum_failures += 1
                self.get_logger().warn(
                    f"checksum mismatch on received line (total failures: {self._checksum_failures}): {line}"
                )
                continue

            self._handle_line(payload)

    def _handle_line(self, line: str) -> None:
        tokens = line.split()
        if not tokens:
            return

        record_type = tokens[0]
        if record_type == "ACK":
            ack_command = tokens[1] if len(tokens) > 1 else "UNKNOWN"
            if ack_command == "PING":
                if len(tokens) >= 3:
                    self._firmware_version = tokens[2]
                if self._ping_sent_time is not None:
                    latency_ms = (time.monotonic() - self._ping_sent_time) * 1000.0
                    self._last_latency_ms = latency_ms
                    self._ping_sent_time = None
                    msg = Float32()
                    msg.data = float(latency_ms)
                    self.latency_pub.publish(msg)
            self._publish_controller_state(f"ACK {' '.join(tokens[1:])}")
        elif record_type == "ERR":
            if len(tokens) < 3:
                self.get_logger().warn(f"malformed ERR line: {line}")
                return
            code = tokens[1]
            message = " ".join(tokens[2:])
            self._publish_controller_state(f"ERR {code} {message}")
            self.estop_pub.publish(Bool(data=("ESTOP" in code) or ("ESTOP" in message.upper())))
            self.get_logger().error(f"controller error {code}: {message}")
        elif record_type == "STATE":
            if len(tokens) < 3:
                self.get_logger().warn(f"malformed STATE line: {line}")
                return
            mode = tokens[1]
            fault = " ".join(tokens[2:])
            self._publish_controller_state(f"{mode} {fault}")
            self.estop_pub.publish(Bool(data=("ESTOP" in mode) or ("ESTOP" in fault)))
        elif record_type == "VBAT":
            if len(tokens) != 4:
                self.get_logger().warn(f"malformed VBAT line: {line}")
                return
            try:
                motor_v = float(tokens[2])
                lidar_v = float(tokens[3])
            except ValueError:
                self.get_logger().warn(f"unable to parse VBAT line: {line}")
                return
            msg = Float32()
            msg.data = float(motor_v)
            self.motor_voltage_pub.publish(msg)
            msg = Float32()
            msg.data = float(lidar_v)
            self.lidar_voltage_pub.publish(msg)
        elif record_type == "ODOM":
            if len(tokens) != 6:
                self.get_logger().warn(f"malformed ODOM line: {line}")
                return
            try:
                stamp_ms = int(tokens[1])
                left_count = int(tokens[2])
                right_count = int(tokens[3])
                left_velocity = float(tokens[4])
                right_velocity = float(tokens[5])
            except ValueError:
                self.get_logger().warn(f"unable to parse ODOM line: {line}")
                return
            self._publish_motion(stamp_ms, left_count, right_count, left_velocity, right_velocity)
        else:
            self.get_logger().warn(f"unknown serial record: {line}")

    def _publish_motion(
        self,
        stamp_ms: int,
        left_count: int,
        right_count: int,
        left_velocity: float,
        right_velocity: float,
    ) -> None:
        self._last_odom_time = time.monotonic()
        stamp_sec = stamp_ms / 1000.0
        state = self._odometry.update(
            stamp_sec=stamp_sec,
            left_count=left_count,
            right_count=right_count,
            left_velocity_mps=left_velocity,
            right_velocity_mps=right_velocity,
        )
        stamp = self.get_clock().now().to_msg()

        odom_msg = Odometry()
        odom_msg.header.stamp = stamp
        odom_msg.header.frame_id = self.odom_frame
        odom_msg.child_frame_id = self.base_frame
        odom_msg.pose.pose.position.x = state.x
        odom_msg.pose.pose.position.y = state.y
        odom_msg.pose.pose.orientation = self._quaternion_from_yaw(state.yaw)
        odom_msg.twist.twist.linear.x = state.linear_velocity
        odom_msg.twist.twist.angular.z = state.angular_velocity
        self.odom_pub.publish(odom_msg)

        joint_state = JointState()
        joint_state.header.stamp = stamp
        joint_state.name = ["left_wheel_joint", "right_wheel_joint"]
        joint_state.position = [state.left_joint_position, state.right_joint_position]
        joint_state.velocity = [
            left_velocity / self.wheel_radius if self.wheel_radius > 0.0 else 0.0,
            right_velocity / self.wheel_radius if self.wheel_radius > 0.0 else 0.0,
        ]
        self.joint_state_pub.publish(joint_state)

        if self.tf_broadcaster is not None:
            transform = TransformStamped()
            transform.header.stamp = stamp
            transform.header.frame_id = self.odom_frame
            transform.child_frame_id = self.base_frame
            transform.transform.translation.x = state.x
            transform.transform.translation.y = state.y
            transform.transform.rotation = self._quaternion_from_yaw(state.yaw)
            self.tf_broadcaster.sendTransform(transform)

    def _publish_controller_state(self, text: str) -> None:
        self.controller_state_pub.publish(String(data=text))

    def _ping_timer_callback(self) -> None:
        if self._serial is None:
            return
        self._ping_sent_time = time.monotonic()
        self._write_line("PING")

    def _health_timer_callback(self) -> None:
        odom_age = None
        if self._last_odom_time is not None:
            odom_age = round(time.monotonic() - self._last_odom_time, 3)

        payload = {
            "serial_connected": self._serial is not None,
            "firmware_version": self._firmware_version,
            "uptime_sec": round(time.monotonic() - self._start_time, 1),
            "reconnect_count": self._reconnect_count,
            "checksum_failures": self._checksum_failures,
            "last_odom_age_sec": odom_age,
            "last_latency_ms": round(self._last_latency_ms, 2) if self._last_latency_ms is not None else None,
        }
        msg = String()
        msg.data = json.dumps(payload, sort_keys=True)
        self.health_pub.publish(msg)

    @staticmethod
    def _quaternion_from_yaw(yaw: float) -> Quaternion:
        quaternion = Quaternion()
        quaternion.z = math.sin(yaw * 0.5)
        quaternion.w = math.cos(yaw * 0.5)
        return quaternion


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SerialBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
