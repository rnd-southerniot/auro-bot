from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import rclpy
from geometry_msgs.msg import Twist, Vector3Stamped
from nav_msgs.msg import Odometry
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import Imu, JointState, LaserScan, MagneticField
from std_msgs.msg import Bool, Float32, String


def _monotonic_age(stamp: float | None) -> float | None:
    if stamp is None:
        return None
    return max(0.0, time.monotonic() - stamp)


def _yaw_from_quaternion(x: float, y: float, z: float, w: float) -> float:
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return math.atan2(siny_cosp, cosy_cosp)


def _safe_label(label: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in label.strip())
    return cleaned or "ground_test"


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


@dataclass
class OdomState:
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0
    linear_x: float = 0.0
    angular_z: float = 0.0
    stamp: float | None = None


@dataclass
class ScanState:
    frame_id: str = ""
    beam_count: int = 0
    stamp: float | None = None


@dataclass
class JointStateView:
    names: list[str] = field(default_factory=list)
    positions: list[float] = field(default_factory=list)
    velocities: list[float] = field(default_factory=list)
    stamp: float | None = None


@dataclass
class PowerState:
    available: bool = False
    message: str = "No INA238 data yet"
    bus_voltage_v: float = math.nan
    current_a: float = math.nan
    power_w: float = math.nan
    temperature_c: float = math.nan
    shunt_voltage_v: float = math.nan
    stamp: float | None = None


@dataclass
class BatteryVoltages:
    motor_voltage: float = math.nan
    lidar_voltage: float = math.nan
    stamp: float | None = None


@dataclass
class ImuState:
    available: bool = False
    message: str = "No IMU data yet"
    variant: str = ""
    frame_id: str = ""
    gyro_address: int = 0
    accel_address: int = 0
    mag_address: int = 0
    angular_velocity_x: float = math.nan
    angular_velocity_y: float = math.nan
    angular_velocity_z: float = math.nan
    linear_acceleration_x: float = math.nan
    linear_acceleration_y: float = math.nan
    linear_acceleration_z: float = math.nan
    magnetic_field_x: float = math.nan
    magnetic_field_y: float = math.nan
    magnetic_field_z: float = math.nan
    yaw_rad: float = math.nan
    pitch_rad: float = math.nan
    roll_rad: float = math.nan
    heading_deg: float = math.nan
    stamp: float | None = None


class CaptureManager:
    def __init__(self, capture_root: Path, topics: list[str]) -> None:
        self.capture_root = capture_root
        self.capture_root.mkdir(parents=True, exist_ok=True)
        self.topics = topics
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._log_handle = None
        self._folder: Path | None = None
        self._label = ""
        self._started_wall_time: float | None = None
        self._last_error = ""

    def start(self, label: str) -> dict[str, Any]:
        safe_label = _safe_label(label)
        timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        run_dir = self.capture_root / f"{timestamp}_{safe_label}"
        bag_dir = run_dir / "bag"

        with self._lock:
            if self._process is not None:
                raise RuntimeError("capture already active")

            run_dir.mkdir(parents=True, exist_ok=False)
            log_path = run_dir / "record.log"
            meta_path = run_dir / "capture_meta.json"
            cmd = ["ros2", "bag", "record", "-o", str(bag_dir), *self.topics]
            env = os.environ.copy()

            self._log_handle = log_path.open("w", encoding="utf-8")
            try:
                self._process = subprocess.Popen(
                    cmd,
                    cwd=str(self.capture_root),
                    env=env,
                    stdout=self._log_handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                    start_new_session=True,
                )
            except Exception:
                self._log_handle.close()
                self._log_handle = None
                raise

            self._folder = run_dir
            self._label = safe_label
            self._started_wall_time = time.time()
            self._last_error = ""
            meta_path.write_text(
                json.dumps(
                    {
                        "label": safe_label,
                        "run_folder": str(run_dir),
                        "bag_folder": str(bag_dir),
                        "started_at": self._started_wall_time,
                        "topics": self.topics,
                        "command": cmd,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

        time.sleep(0.4)
        with self._lock:
            if self._process is not None and self._process.poll() is not None:
                self._last_error = f"ros2 bag exited immediately with code {self._process.returncode}"
                self._cleanup_locked()
                raise RuntimeError(self._last_error)
            return self.snapshot()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if self._process is None:
                return self.snapshot()

            proc = self._process
            folder = self._folder
            label = self._label
            started_wall_time = self._started_wall_time
            last_error = self._last_error
            meta_path = folder / "capture_meta.json" if folder is not None else None

            try:
                os.killpg(proc.pid, signal.SIGINT)
            except ProcessLookupError:
                pass

        try:
            proc.wait(timeout=15.0)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=5.0)

        with self._lock:
            if meta_path is not None and meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    meta = {}
                meta.update(
                    {
                        "stopped_at": time.time(),
                        "return_code": proc.returncode,
                    }
                )
                meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
            self._cleanup_locked()
            return {
                "active": False,
                "label": label,
                "folder": str(folder) if folder is not None else "",
                "started_wall_time": started_wall_time,
                "last_error": last_error,
            }

    def snapshot(self) -> dict[str, Any]:
        return {
            "active": self._process is not None,
            "label": self._label,
            "folder": str(self._folder) if self._folder is not None else "",
            "started_wall_time": self._started_wall_time,
            "last_error": self._last_error,
        }

    def recent_runs(self, limit: int = 10) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        for meta_path in sorted(self.capture_root.glob("*/capture_meta.json"), reverse=True):
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            data["folder"] = str(meta_path.parent)
            runs.append(data)
            if len(runs) >= limit:
                break
        return runs

    def shutdown(self) -> None:
        if self._process is not None:
            self.stop()

    def _cleanup_locked(self) -> None:
        if self._log_handle is not None:
            self._log_handle.close()
        self._process = None
        self._log_handle = None
        self._folder = None
        self._label = ""
        self._started_wall_time = None


class WebConsoleNode(Node):
    def __init__(self) -> None:
        super().__init__("navbot_web_console")

        self.declare_parameter("host", "127.0.0.1")
        self.declare_parameter("port", 8080)
        self.declare_parameter("capture_root", str(Path.home() / "navbot_captures"))
        self.declare_parameter("cmd_vel_topic", "/cmd_vel")
        self.declare_parameter("odom_topic", "/odom")
        self.declare_parameter("scan_topic", "/scan")
        self.declare_parameter("joint_states_topic", "/joint_states")
        self.declare_parameter("controller_state_topic", "/base/controller_state")
        self.declare_parameter("estop_topic", "/base/estop")
        self.declare_parameter("power_status_topic", "/power/ina238/status")
        self.declare_parameter("imu_status_topic", "/imu/l3gd20_lsm303d/status")
        self.declare_parameter("imu_raw_topic", "/imu/l3gd20_lsm303d/raw")
        self.declare_parameter("imu_mag_topic", "/imu/l3gd20_lsm303d/mag")
        self.declare_parameter("imu_ypr_topic", "/imu/l3gd20_lsm303d/ypr")
        self.declare_parameter(
            "capture_topics",
            [
                "/scan",
                "/odom",
                "/odometry/filtered",
                "/tf",
                "/tf_static",
                "/joint_states",
                "/base/controller_state",
                "/base/estop",
                "/cmd_vel",
                "/imu/l3gd20_lsm303d/raw",
                "/imu/l3gd20_lsm303d/mag",
                "/imu/l3gd20_lsm303d/ypr",
                "/heading_controller/status",
            ],
        )
        self.declare_parameter("command_hold_timeout", 0.35)
        self.declare_parameter("topic_stale_timeout", 1.0)

        self.host = str(self.get_parameter("host").value)
        self.port = int(self.get_parameter("port").value)
        self.capture_root = Path(str(self.get_parameter("capture_root").value)).expanduser()
        self.capture_topics = [str(topic) for topic in self.get_parameter("capture_topics").value]
        self.command_hold_timeout = float(self.get_parameter("command_hold_timeout").value)
        self.topic_stale_timeout = float(self.get_parameter("topic_stale_timeout").value)

        self._api_token = self._load_api_token()
        self._require_token = self.host != "127.0.0.1" and self._api_token is not None

        self._state_lock = threading.Lock()
        self._odom = OdomState()
        self._scan = ScanState()
        self._joints = JointStateView()
        self._power = PowerState()
        self._batteries = BatteryVoltages()
        self._imu = ImuState()
        self._controller_state = "UNKNOWN"
        self._controller_stamp: float | None = None
        self._estop = False
        self._estop_stamp: float | None = None
        self._ros_started = time.monotonic()
        self._last_cmd_linear = 0.0
        self._last_cmd_angular = 0.0
        self._last_cmd_time: float | None = None
        self._zero_sent = False

        self.capture_manager = CaptureManager(self.capture_root, self.capture_topics)

        cmd_vel_topic = str(self.get_parameter("cmd_vel_topic").value)
        odom_topic = str(self.get_parameter("odom_topic").value)
        scan_topic = str(self.get_parameter("scan_topic").value)
        joint_states_topic = str(self.get_parameter("joint_states_topic").value)
        controller_state_topic = str(self.get_parameter("controller_state_topic").value)
        estop_topic = str(self.get_parameter("estop_topic").value)
        power_status_topic = str(self.get_parameter("power_status_topic").value)
        imu_status_topic = str(self.get_parameter("imu_status_topic").value)
        imu_raw_topic = str(self.get_parameter("imu_raw_topic").value)
        imu_mag_topic = str(self.get_parameter("imu_mag_topic").value)
        imu_ypr_topic = str(self.get_parameter("imu_ypr_topic").value)

        self._cmd_pub = self.create_publisher(Twist, cmd_vel_topic, 20)
        self.create_subscription(Odometry, odom_topic, self._odom_cb, 20)
        self.create_subscription(LaserScan, scan_topic, self._scan_cb, 10)
        self.create_subscription(JointState, joint_states_topic, self._joint_cb, 20)
        self.create_subscription(String, controller_state_topic, self._controller_cb, 10)
        self.create_subscription(Bool, estop_topic, self._estop_cb, 10)
        self.create_subscription(String, power_status_topic, self._power_cb, 10)
        self.create_subscription(Float32, "/base/motor_voltage", self._motor_voltage_cb, 10)
        self.create_subscription(Float32, "/base/lidar_voltage", self._lidar_voltage_cb, 10)
        self.create_subscription(String, imu_status_topic, self._imu_status_cb, 10)
        self.create_subscription(Imu, imu_raw_topic, self._imu_raw_cb, 20)
        self.create_subscription(MagneticField, imu_mag_topic, self._imu_mag_cb, 20)
        self.create_subscription(Vector3Stamped, imu_ypr_topic, self._imu_ypr_cb, 20)
        self.create_timer(0.1, self._command_timer_cb)

    def set_cmd_vel(self, linear: float, angular: float) -> None:
        with self._state_lock:
            self._last_cmd_linear = float(linear)
            self._last_cmd_angular = float(angular)
            self._last_cmd_time = time.monotonic()
            self._zero_sent = False

    def stop_motion(self) -> None:
        with self._state_lock:
            self._last_cmd_linear = 0.0
            self._last_cmd_angular = 0.0
            self._last_cmd_time = None
            self._zero_sent = False
        self._publish_twist(0.0, 0.0)

    def snapshot(self) -> dict[str, Any]:
        with self._state_lock:
            odom_age = _monotonic_age(self._odom.stamp)
            scan_age = _monotonic_age(self._scan.stamp)
            joint_age = _monotonic_age(self._joints.stamp)
            power_age = _monotonic_age(self._power.stamp)
            battery_age = _monotonic_age(self._batteries.stamp)
            imu_age = _monotonic_age(self._imu.stamp)
            controller_age = _monotonic_age(self._controller_stamp)
            estop_age = _monotonic_age(self._estop_stamp)
            capture = self.capture_manager.snapshot()
            return {
                "server": {"host": self.host, "port": self.port},
                "ros_bridge_alive": True,
                "ros_uptime_sec": max(0.0, time.monotonic() - self._ros_started),
                "base_bridge_alive": (
                    (controller_age is not None and controller_age < self.topic_stale_timeout)
                    or (odom_age is not None and odom_age < self.topic_stale_timeout)
                ),
                "odom": {
                    **asdict(self._odom),
                    "age_sec": odom_age,
                    "alive": odom_age is not None and odom_age < self.topic_stale_timeout,
                },
                "scan": {
                    **asdict(self._scan),
                    "age_sec": scan_age,
                    "alive": scan_age is not None and scan_age < self.topic_stale_timeout,
                },
                "joint_states": {
                    **asdict(self._joints),
                    "age_sec": joint_age,
                    "alive": joint_age is not None and joint_age < self.topic_stale_timeout,
                },
                "power": {
                    **asdict(self._power),
                    "age_sec": power_age,
                    "alive": power_age is not None and power_age < self.topic_stale_timeout,
                },
                "batteries": {
                    **asdict(self._batteries),
                    "age_sec": battery_age,
                    "alive": battery_age is not None and battery_age < self.topic_stale_timeout,
                },
                "imu": {
                    **asdict(self._imu),
                    "age_sec": imu_age,
                    "alive": imu_age is not None and imu_age < self.topic_stale_timeout,
                },
                "controller": {
                    "state": self._controller_state,
                    "age_sec": controller_age,
                    "alive": controller_age is not None and controller_age < self.topic_stale_timeout,
                },
                "estop": {
                    "active": self._estop,
                    "age_sec": estop_age,
                },
                "capture": {
                    **capture,
                    "recent": self.capture_manager.recent_runs(),
                },
                "command": {
                    "linear": self._last_cmd_linear,
                    "angular": self._last_cmd_angular,
                    "age_sec": _monotonic_age(self._last_cmd_time),
                },
                "updated_at": time.time(),
            }

    def shutdown(self) -> None:
        self.stop_motion()
        self.capture_manager.shutdown()

    @staticmethod
    def _load_api_token() -> str | None:
        token = os.environ.get("NAVBOT_WEB_TOKEN")
        if token:
            return token.strip()
        token_path = Path.home() / ".navbot_web_token"
        if token_path.exists():
            content = token_path.read_text(encoding="utf-8").strip()
            if content:
                return content
        return None

    def _publish_twist(self, linear: float, angular: float) -> None:
        msg = Twist()
        msg.linear.x = float(linear)
        msg.angular.z = float(angular)
        self._cmd_pub.publish(msg)

    def _command_timer_cb(self) -> None:
        with self._state_lock:
            linear = self._last_cmd_linear
            angular = self._last_cmd_angular
            cmd_time = self._last_cmd_time
            zero_sent = self._zero_sent

        fresh = cmd_time is not None and (time.monotonic() - cmd_time) <= self.command_hold_timeout
        if fresh:
            self._publish_twist(linear, angular)
            with self._state_lock:
                self._zero_sent = False
            return

        if not zero_sent:
            self._publish_twist(0.0, 0.0)
            with self._state_lock:
                self._zero_sent = True

    def _odom_cb(self, msg: Odometry) -> None:
        yaw = _yaw_from_quaternion(
            msg.pose.pose.orientation.x,
            msg.pose.pose.orientation.y,
            msg.pose.pose.orientation.z,
            msg.pose.pose.orientation.w,
        )
        with self._state_lock:
            self._odom = OdomState(
                x=float(msg.pose.pose.position.x),
                y=float(msg.pose.pose.position.y),
                yaw=float(yaw),
                linear_x=float(msg.twist.twist.linear.x),
                angular_z=float(msg.twist.twist.angular.z),
                stamp=time.monotonic(),
            )

    def _scan_cb(self, msg: LaserScan) -> None:
        with self._state_lock:
            self._scan = ScanState(
                frame_id=msg.header.frame_id,
                beam_count=len(msg.ranges),
                stamp=time.monotonic(),
            )

    def _joint_cb(self, msg: JointState) -> None:
        with self._state_lock:
            self._joints = JointStateView(
                names=list(msg.name),
                positions=[float(v) for v in msg.position],
                velocities=[float(v) for v in msg.velocity],
                stamp=time.monotonic(),
            )

    def _controller_cb(self, msg: String) -> None:
        with self._state_lock:
            self._controller_state = msg.data
            self._controller_stamp = time.monotonic()

    def _estop_cb(self, msg: Bool) -> None:
        with self._state_lock:
            self._estop = bool(msg.data)
            self._estop_stamp = time.monotonic()

    def _power_cb(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            with self._state_lock:
                self._power = PowerState(
                    available=False,
                    message="INA238 status payload is not valid JSON",
                    stamp=time.monotonic(),
                )
            return

        def _num(name: str) -> float:
            value = payload.get(name, math.nan)
            try:
                return float(value)
            except (TypeError, ValueError):
                return math.nan

        with self._state_lock:
            self._power = PowerState(
                available=bool(payload.get("available", False)),
                message=str(payload.get("message", "INA238 status unavailable")),
                bus_voltage_v=_num("bus_voltage_v"),
                current_a=_num("current_a"),
                power_w=_num("power_w"),
                temperature_c=_num("temperature_c"),
                shunt_voltage_v=_num("shunt_voltage_v"),
                stamp=time.monotonic(),
            )

    def _motor_voltage_cb(self, msg: Float32) -> None:
        with self._state_lock:
            self._batteries.motor_voltage = float(msg.data)
            self._batteries.stamp = time.monotonic()

    def _lidar_voltage_cb(self, msg: Float32) -> None:
        with self._state_lock:
            self._batteries.lidar_voltage = float(msg.data)
            self._batteries.stamp = time.monotonic()

    def _imu_status_cb(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            with self._state_lock:
                self._imu = ImuState(
                    available=False,
                    message="IMU status payload is not valid JSON",
                    stamp=time.monotonic(),
                )
            return

        with self._state_lock:
            self._imu.available = bool(payload.get("available", False))
            self._imu.message = str(payload.get("message", "IMU status unavailable"))
            self._imu.variant = str(payload.get("variant", ""))
            self._imu.frame_id = str(payload.get("frame_id", self._imu.frame_id))
            self._imu.gyro_address = int(payload.get("gyro_address", self._imu.gyro_address or 0))
            self._imu.accel_address = int(payload.get("accel_address", self._imu.accel_address or 0))
            self._imu.mag_address = int(payload.get("mag_address", self._imu.mag_address or 0))
            self._imu.yaw_rad = self._num_from_payload(payload, "yaw_rad", self._imu.yaw_rad)
            self._imu.pitch_rad = self._num_from_payload(payload, "pitch_rad", self._imu.pitch_rad)
            self._imu.roll_rad = self._num_from_payload(payload, "roll_rad", self._imu.roll_rad)
            self._imu.heading_deg = self._num_from_payload(payload, "heading_deg", self._imu.heading_deg)
            self._imu.stamp = time.monotonic()

    def _imu_raw_cb(self, msg: Imu) -> None:
        with self._state_lock:
            self._imu.frame_id = msg.header.frame_id
            self._imu.angular_velocity_x = float(msg.angular_velocity.x)
            self._imu.angular_velocity_y = float(msg.angular_velocity.y)
            self._imu.angular_velocity_z = float(msg.angular_velocity.z)
            self._imu.linear_acceleration_x = float(msg.linear_acceleration.x)
            self._imu.linear_acceleration_y = float(msg.linear_acceleration.y)
            self._imu.linear_acceleration_z = float(msg.linear_acceleration.z)
            self._imu.stamp = time.monotonic()

    def _imu_mag_cb(self, msg: MagneticField) -> None:
        with self._state_lock:
            self._imu.frame_id = msg.header.frame_id
            self._imu.magnetic_field_x = float(msg.magnetic_field.x)
            self._imu.magnetic_field_y = float(msg.magnetic_field.y)
            self._imu.magnetic_field_z = float(msg.magnetic_field.z)
            self._imu.stamp = time.monotonic()

    def _imu_ypr_cb(self, msg: Vector3Stamped) -> None:
        yaw = float(msg.vector.x)
        with self._state_lock:
            self._imu.frame_id = msg.header.frame_id
            self._imu.yaw_rad = yaw
            self._imu.pitch_rad = float(msg.vector.y)
            self._imu.roll_rad = float(msg.vector.z)
            self._imu.heading_deg = (math.degrees(yaw) + 360.0) % 360.0
            self._imu.stamp = time.monotonic()

    @staticmethod
    def _num_from_payload(payload: dict[str, Any], name: str, default: float) -> float:
        try:
            return float(payload.get(name, default))
        except (TypeError, ValueError):
            return math.nan


class WebAppContext:
    def __init__(self, node: WebConsoleNode) -> None:
        self.node = node
        self.static_dir = Path(__file__).resolve().parent / "static"


class RequestHandler(BaseHTTPRequestHandler):
    server: "RobotWebServer"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._serve_static("index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/static/app.js":
            self._serve_static("app.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/static/styles.css":
            self._serve_static("styles.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/api/status":
            self._send_json(HTTPStatus.OK, self.server.context.node.snapshot())
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._check_token():
            return

        parsed = urlparse(self.path)
        body = self._read_json()

        try:
            if parsed.path == "/api/cmd_vel":
                self.server.context.node.set_cmd_vel(
                    float(body.get("linear", 0.0)),
                    float(body.get("angular", 0.0)),
                )
                self._send_json(HTTPStatus.OK, {"ok": True})
                return

            if parsed.path == "/api/stop":
                self.server.context.node.stop_motion()
                self._send_json(HTTPStatus.OK, {"ok": True})
                return

            if parsed.path == "/api/capture/start":
                label = str(body.get("label", "ground_test"))
                capture = self.server.context.node.capture_manager.start(label)
                self._send_json(HTTPStatus.OK, {"ok": True, "capture": capture})
                return

            if parsed.path == "/api/capture/stop":
                capture = self.server.context.node.capture_manager.stop()
                self._send_json(HTTPStatus.OK, {"ok": True, "capture": capture})
                return
        except Exception as exc:  # pragma: no cover - runtime path
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def _check_token(self) -> bool:
        node = self.server.context.node
        if not node._require_token:
            return True
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and auth[7:].strip() == node._api_token:
            return True
        self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "missing or invalid bearer token"})
        return False

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        payload = self.rfile.read(length)
        if not payload:
            return {}
        try:
            return json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError:
            raise RuntimeError("invalid json body")

    def _serve_static(self, file_name: str, content_type: str) -> None:
        file_path = self.server.context.static_dir / file_name
        if not file_path.exists():
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "missing static asset"})
            return
        data = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        data = json.dumps(_json_safe(payload), allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class RobotWebServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], context: WebAppContext) -> None:
        super().__init__(server_address, RequestHandler)
        self.context = context


def _spin_ros(node: WebConsoleNode, ready: threading.Event) -> None:
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    ready.set()
    try:
        executor.spin()
    finally:
        executor.remove_node(node)


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = WebConsoleNode()
    ready = threading.Event()
    ros_thread = threading.Thread(target=_spin_ros, args=(node, ready), daemon=True)
    ros_thread.start()
    ready.wait(timeout=2.0)

    context = WebAppContext(node)
    server = RobotWebServer((node.host, node.port), context)
    node.get_logger().info(f"ground-test web console on http://{node.host}:{node.port}")
    if node.host != "127.0.0.1":
        if node._require_token:
            node.get_logger().warn(
                "web console is LAN-accessible — POST endpoints require Bearer token"
            )
        else:
            node.get_logger().warn(
                "WARNING: web console is LAN-accessible WITHOUT authentication. "
                "Set NAVBOT_WEB_TOKEN or create ~/.navbot_web_token to enable token auth."
            )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        node.shutdown()
        node.destroy_node()
        rclpy.shutdown()
        ros_thread.join(timeout=2.0)


if __name__ == "__main__":
    main()
