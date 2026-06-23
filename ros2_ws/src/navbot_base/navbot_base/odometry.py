import math
from dataclasses import dataclass


@dataclass
class OdometryState:
    stamp_sec: float
    x: float
    y: float
    yaw: float
    linear_velocity: float
    angular_velocity: float
    left_joint_position: float
    right_joint_position: float
    left_wheel_velocity: float
    right_wheel_velocity: float


class DifferentialDriveOdometry:
    """Track differential-drive pose from wheel encoder counts."""

    def __init__(
        self,
        wheel_radius: float,
        wheel_separation: float,
        counts_per_revolution: int,
        left_counts_per_revolution: int | None = None,
        right_counts_per_revolution: int | None = None,
    ) -> None:
        self.wheel_radius = wheel_radius
        self.wheel_separation = wheel_separation
        default_cpr = max(int(counts_per_revolution), 1)
        self.left_counts_per_revolution = max(int(left_counts_per_revolution or default_cpr), 1)
        self.right_counts_per_revolution = max(int(right_counts_per_revolution or default_cpr), 1)

        self.x = 0.0
        self.y = 0.0
        self.yaw = 0.0

        self._last_stamp_sec = None
        self._last_left_count = None
        self._last_right_count = None

        self.left_joint_position = 0.0
        self.right_joint_position = 0.0

    @property
    def meters_per_count(self) -> float:
        return (2.0 * math.pi * self.wheel_radius) / float(
            0.5 * (self.left_counts_per_revolution + self.right_counts_per_revolution)
        )

    def reset(self) -> None:
        self.x = 0.0
        self.y = 0.0
        self.yaw = 0.0
        self._last_stamp_sec = None
        self._last_left_count = None
        self._last_right_count = None
        self.left_joint_position = 0.0
        self.right_joint_position = 0.0

    def update(
        self,
        stamp_sec: float,
        left_count: int,
        right_count: int,
        left_velocity_mps: float,
        right_velocity_mps: float,
    ) -> OdometryState:
        left_wheel_angle_scale = (2.0 * math.pi) / float(self.left_counts_per_revolution)
        right_wheel_angle_scale = (2.0 * math.pi) / float(self.right_counts_per_revolution)
        self.left_joint_position = left_count * left_wheel_angle_scale
        self.right_joint_position = right_count * right_wheel_angle_scale

        linear_velocity = 0.5 * (left_velocity_mps + right_velocity_mps)
        angular_velocity = 0.0
        if self.wheel_separation > 0.0:
            angular_velocity = (right_velocity_mps - left_velocity_mps) / self.wheel_separation

        if self._last_left_count is None or self._last_right_count is None or self._last_stamp_sec is None:
            self._last_left_count = left_count
            self._last_right_count = right_count
            self._last_stamp_sec = stamp_sec
            return OdometryState(
                stamp_sec=stamp_sec,
                x=self.x,
                y=self.y,
                yaw=self.yaw,
                linear_velocity=linear_velocity,
                angular_velocity=angular_velocity,
                left_joint_position=self.left_joint_position,
                right_joint_position=self.right_joint_position,
                left_wheel_velocity=left_velocity_mps,
                right_wheel_velocity=right_velocity_mps,
            )

        left_delta = left_count - self._last_left_count
        right_delta = right_count - self._last_right_count
        dt = stamp_sec - self._last_stamp_sec

        # Detect MCU restart: a backward jump larger than 10 full wheel revolutions
        # indicates the encoder counter reset to zero, not actual motion.
        restart_threshold = max(self.left_counts_per_revolution, self.right_counts_per_revolution) * 10
        if abs(left_delta) > restart_threshold or abs(right_delta) > restart_threshold:
            self._last_left_count = left_count
            self._last_right_count = right_count
            self._last_stamp_sec = stamp_sec
            return OdometryState(
                stamp_sec=stamp_sec,
                x=self.x,
                y=self.y,
                yaw=self.yaw,
                linear_velocity=0.0,
                angular_velocity=0.0,
                left_joint_position=self.left_joint_position,
                right_joint_position=self.right_joint_position,
                left_wheel_velocity=0.0,
                right_wheel_velocity=0.0,
            )

        # MCU uses int64 encoder counts — rollover is effectively eliminated.
        left_distance = left_delta * ((2.0 * math.pi * self.wheel_radius) / float(self.left_counts_per_revolution))
        right_distance = right_delta * (
            (2.0 * math.pi * self.wheel_radius) / float(self.right_counts_per_revolution)
        )

        delta_s = 0.5 * (left_distance + right_distance)
        delta_theta = 0.0
        if self.wheel_separation > 0.0:
            delta_theta = (right_distance - left_distance) / self.wheel_separation

        heading_mid = self.yaw + (0.5 * delta_theta)
        self.x += delta_s * math.cos(heading_mid)
        self.y += delta_s * math.sin(heading_mid)
        self.yaw = math.atan2(math.sin(self.yaw + delta_theta), math.cos(self.yaw + delta_theta))

        if dt <= 0.0:
            dt = 0.0

        self._last_left_count = left_count
        self._last_right_count = right_count
        self._last_stamp_sec = stamp_sec

        return OdometryState(
            stamp_sec=stamp_sec,
            x=self.x,
            y=self.y,
            yaw=self.yaw,
            linear_velocity=linear_velocity,
            angular_velocity=angular_velocity,
            left_joint_position=self.left_joint_position,
            right_joint_position=self.right_joint_position,
            left_wheel_velocity=left_velocity_mps,
            right_wheel_velocity=right_velocity_mps,
        )
