import json
import math
from dataclasses import dataclass
from typing import Optional

import rclpy
from geometry_msgs.msg import Vector3Stamped
from rclpy.node import Node
from sensor_msgs.msg import Imu, MagneticField
from std_msgs.msg import String

try:
    from smbus2 import SMBus
except ImportError:  # pragma: no cover
    SMBus = None


L3GD20_REG_WHO_AM_I = 0x0F
L3GD20_REG_CTRL1 = 0x20
L3GD20_REG_CTRL4 = 0x23
L3GD20_REG_OUT_X_L = 0x28
GYRO_WHO_AM_I_VALUES = {0xD3, 0xD4, 0xD7}

LSM303D_REG_WHO_AM_I = 0x0F
LSM303D_REG_CTRL1 = 0x20
LSM303D_REG_CTRL2 = 0x21
LSM303D_REG_CTRL5 = 0x24
LSM303D_REG_CTRL6 = 0x25
LSM303D_REG_CTRL7 = 0x26
LSM303D_REG_OUT_X_L_M = 0x08
LSM303D_REG_OUT_X_L_A = 0x28
LSM303D_WHO_AM_I = 0x49

LSM303DLHC_ACCEL_WHO_AM_I = 0x33
LSM303DLHC_ACCEL_REG_CTRL1 = 0x20
LSM303DLHC_ACCEL_REG_CTRL4 = 0x23
LSM303DLHC_ACCEL_REG_OUT_X_L = 0x28
LSM303DLHC_MAG_REG_CRA = 0x00
LSM303DLHC_MAG_REG_CRB = 0x01
LSM303DLHC_MAG_REG_MR = 0x02
LSM303DLHC_MAG_REG_OUT_X_H = 0x03


def _wrap_pi(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def _compute_ypr(
    accel: tuple[float, float, float],
    mag: tuple[float, float, float],
) -> tuple[float, float, float]:
    ax, ay, az = accel
    mx, my, mz = mag

    roll = math.atan2(ay, az)
    pitch = math.atan2(-ax, math.sqrt((ay * ay) + (az * az)))

    cos_roll = math.cos(roll)
    sin_roll = math.sin(roll)
    cos_pitch = math.cos(pitch)
    sin_pitch = math.sin(pitch)

    mag_x = (mx * cos_pitch) + (mz * sin_pitch)
    mag_y = (mx * sin_roll * sin_pitch) + (my * cos_roll) - (mz * sin_roll * cos_pitch)
    yaw = math.atan2(mag_y, mag_x)
    return _wrap_pi(yaw), pitch, roll


@dataclass
class ImuProbeStatus:
    available: bool
    message: str
    gyro_available: bool = False
    accel_available: bool = False
    mag_available: bool = False
    gyro_address: int = 0
    accel_address: int = 0
    mag_address: int = 0
    gyro_id: int = 0
    accel_id: int = 0
    mag_id: int = 0
    variant: str = "unknown"
    stamp: float = 0.0


class L3gd20Lsm303dReader:
    def __init__(
        self,
        i2c_bus: int,
        gyro_address: int,
        accel_address: int,
        mag_address: int,
        gyro_rad_per_sec_per_lsb: float,
        accel_mps2_per_lsb: float,
        mag_tesla_per_lsb_xy: float,
        mag_tesla_per_lsb_z: float,
        sensor_orientation: str = "y_forward",
    ) -> None:
        self.i2c_bus = i2c_bus
        self.gyro_address = gyro_address
        self.accel_address = accel_address
        self.mag_address = mag_address
        self.gyro_rad_per_sec_per_lsb = gyro_rad_per_sec_per_lsb
        self.accel_mps2_per_lsb = accel_mps2_per_lsb
        self.mag_tesla_per_lsb_xy = mag_tesla_per_lsb_xy
        self.mag_tesla_per_lsb_z = mag_tesla_per_lsb_z
        if sensor_orientation not in ("x_forward", "y_forward", "x_forward_flipped"):
            raise ValueError(
                "sensor_orientation must be 'x_forward', 'y_forward', or "
                f"'x_forward_flipped', got {sensor_orientation!r}"
            )
        self.sensor_orientation = sensor_orientation
        self._bus: Optional[SMBus] = None
        self._configured = False
        self._variant = "unknown"
        self._cached_probe: Optional[ImuProbeStatus] = None

    def connect(self) -> None:
        if SMBus is None:
            raise RuntimeError("python3-smbus2 is not installed")
        if self._bus is None:
            self._bus = SMBus(self.i2c_bus)

    def close(self) -> None:
        if self._bus is not None:
            self._bus.close()
            self._bus = None
        self._configured = False
        self._cached_probe = None

    def _read_u8(self, address: int, register: int) -> int:
        assert self._bus is not None
        return self._bus.read_byte_data(address, register)

    def _write_u8(self, address: int, register: int, value: int) -> None:
        assert self._bus is not None
        self._bus.write_byte_data(address, register, value & 0xFF)

    def _read_vector3(self, address: int, register: int) -> tuple[int, int, int]:
        assert self._bus is not None
        data = self._bus.read_i2c_block_data(address, register | 0x80, 6)
        return (
            self._to_signed((data[1] << 8) | data[0]),
            self._to_signed((data[3] << 8) | data[2]),
            self._to_signed((data[5] << 8) | data[4]),
        )

    def _read_lsm303dlhc_mag(self, address: int) -> tuple[int, int, int]:
        assert self._bus is not None
        data = self._bus.read_i2c_block_data(address, LSM303DLHC_MAG_REG_OUT_X_H, 6)
        x = self._to_signed((data[0] << 8) | data[1])
        z = self._to_signed((data[2] << 8) | data[3])
        y = self._to_signed((data[4] << 8) | data[5])
        return x, y, z

    @staticmethod
    def _to_signed(value: int) -> int:
        return value - 0x10000 if value & 0x8000 else value

    def probe(self) -> ImuProbeStatus:
        self.connect()
        gyro_id = 0
        accel_id = 0
        mag_id = 0
        gyro_ok = False
        accel_ok = False
        mag_ok = False
        variant = "unknown"
        messages: list[str] = []

        try:
            gyro_id = self._read_u8(self.gyro_address, L3GD20_REG_WHO_AM_I)
            gyro_ok = gyro_id in GYRO_WHO_AM_I_VALUES
            if not gyro_ok:
                messages.append(
                    f"L3GD20 WHO_AM_I mismatch at 0x{self.gyro_address:02X}: 0x{gyro_id:02X}"
                )
        except Exception as exc:
            messages.append(f"L3GD20 not responding at 0x{self.gyro_address:02X}: {exc}")

        try:
            accel_id = self._read_u8(self.accel_address, LSM303D_REG_WHO_AM_I)
            if accel_id == LSM303D_WHO_AM_I:
                accel_ok = True
                mag_ok = True
                variant = "lsm303d"
            elif accel_id == LSM303DLHC_ACCEL_WHO_AM_I:
                accel_ok = True
                variant = "lsm303dlhc"
                try:
                    # Older LSM303DLHC magnetometer has no useful WHO_AM_I register. Verify it responds.
                    self._bus.read_byte_data(self.mag_address, LSM303DLHC_MAG_REG_CRA)
                    mag_ok = True
                    mag_id = 0
                except Exception as exc:
                    messages.append(
                        f"LSM303DLHC magnetometer not responding at 0x{self.mag_address:02X}: {exc}"
                    )
            else:
                messages.append(
                    f"LSM303 accel WHO_AM_I mismatch at 0x{self.accel_address:02X}: 0x{accel_id:02X}"
                )
        except Exception as exc:
            messages.append(f"LSM303 accel not responding at 0x{self.accel_address:02X}: {exc}")

        available = gyro_ok and accel_ok and mag_ok
        if available:
            if variant == "lsm303d":
                message = "L3GD20/L3G4200D + LSM303D responding on I2C"
            else:
                message = "L3GD20/L3G4200D + LSM303DLHC responding on I2C"
        else:
            message = " | ".join(messages)
        return ImuProbeStatus(
            available=available,
            message=message,
            gyro_available=gyro_ok,
            accel_available=accel_ok,
            mag_available=mag_ok,
            gyro_address=self.gyro_address,
            accel_address=self.accel_address,
            mag_address=self.mag_address,
            gyro_id=gyro_id,
            accel_id=accel_id,
            mag_id=mag_id,
            variant=variant,
        )

    def _configure(self) -> None:
        if self._configured:
            return
        probe = self.probe()
        if not probe.available:
            raise RuntimeError(probe.message)

        # Gyro: normal mode, XYZ enabled, 245 dps default full-scale.
        self._write_u8(self.gyro_address, L3GD20_REG_CTRL1, 0x0F)
        self._write_u8(self.gyro_address, L3GD20_REG_CTRL4, 0x00)

        if probe.variant == "lsm303d":
            self._write_u8(self.accel_address, LSM303D_REG_CTRL1, 0x57)
            self._write_u8(self.accel_address, LSM303D_REG_CTRL2, 0x00)
            self._write_u8(self.accel_address, LSM303D_REG_CTRL5, 0x64)
            self._write_u8(self.accel_address, LSM303D_REG_CTRL6, 0x20)
            self._write_u8(self.accel_address, LSM303D_REG_CTRL7, 0x00)
        else:
            self._write_u8(self.accel_address, LSM303DLHC_ACCEL_REG_CTRL1, 0x57)
            self._write_u8(self.accel_address, LSM303DLHC_ACCEL_REG_CTRL4, 0x00)
            self._write_u8(self.mag_address, LSM303DLHC_MAG_REG_CRA, 0x14)
            # 2026-04-22 (session 10): CRB 0x20 (±1.3 gauss) → 0x80
            # (±4.0 gauss). Motor hard-iron bias on Y-axis rests
            # at +1.4 gauss, already at the ±1.3 gauss ceiling. During
            # rotation the Y reading saturated at -3.72/+1.86 gauss
            # (datasheet overflow codes). ±4.0 gauss range now covers
            # the full bias + Earth field. Config yaml sensitivity
            # constants (mag_tesla_per_lsb_{xy,z}) MUST match this
            # gain per datasheet Table 75 (XY=450 LSB/gauss,
            # Z=400 LSB/gauss at ±4.0 gauss).
            self._write_u8(self.mag_address, LSM303DLHC_MAG_REG_CRB, 0x80)
            self._write_u8(self.mag_address, LSM303DLHC_MAG_REG_MR, 0x00)
        self._variant = probe.variant
        self._cached_probe = probe
        self._configured = True

    def read_sample(self) -> tuple[
        ImuProbeStatus,
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]:
        """Read gyro, accel, and mag samples.

        Returns all data in **robot frame** (X=forward, Y=left, Z=up).
        The sensor board frame (X=right, Y=forward, Z=up) is remapped
        internally before returning.

        Returns: (probe, gyro, accel, mag_robot, mag_sensor)
            mag_sensor is the raw sensor-frame magnetometer reading,
            needed for applying sensor-frame calibration offsets.
        """
        self.connect()
        self._configure()
        assert self._cached_probe is not None
        probe = self._cached_probe

        gx, gy, gz = self._read_vector3(self.gyro_address, L3GD20_REG_OUT_X_L)
        if probe.variant == "lsm303d":
            ax, ay, az = self._read_vector3(self.accel_address, LSM303D_REG_OUT_X_L_A)
            mx, my, mz = self._read_vector3(self.accel_address, LSM303D_REG_OUT_X_L_M)
        else:
            ax, ay, az = self._read_vector3(self.accel_address, LSM303DLHC_ACCEL_REG_OUT_X_L)
            mx, my, mz = self._read_lsm303dlhc_mag(self.mag_address)

        # Scale raw sensor readings to SI units (still in sensor frame).
        gyro_s = (
            gx * self.gyro_rad_per_sec_per_lsb,
            gy * self.gyro_rad_per_sec_per_lsb,
            gz * self.gyro_rad_per_sec_per_lsb,
        )
        accel_s = (
            ax * self.accel_mps2_per_lsb,
            ay * self.accel_mps2_per_lsb,
            az * self.accel_mps2_per_lsb,
        )
        mag_s = (
            mx * self.mag_tesla_per_lsb_xy,
            my * self.mag_tesla_per_lsb_xy,
            mz * self.mag_tesla_per_lsb_z,
        )

        # Remap sensor frame to robot frame (X=forward, Y=left, Z=up).
        # The sensor_orientation param controls how the physical chip
        # is mounted relative to the robot chassis:
        #   "y_forward" — original mount: sensor-Y points robot-forward,
        #                 sensor-X points robot-right. Maps:
        #                   robot_x =  sensor_y,  robot_y = -sensor_x
        #   "x_forward" — session 9 mount: sensor-X points robot-forward,
        #                 sensor-Y points robot-left. Identity map.
        #   "x_forward_flipped" — 2026-06-16 remount: board flipped 180°
        #                 about the forward (X) axis (roll ≈ 180°). Sensor-X
        #                 still points robot-forward, but Y and Z are
        #                 inverted. Restores Z-up so accel_z ≈ +g and yaw
        #                 (gyro_z) reads +CCW.
        # Z-up is assumed for x_forward/y_forward; Phase 0 confirmed az ≈ +g.
        if self.sensor_orientation == "y_forward":
            gyro = (gyro_s[1], -gyro_s[0], gyro_s[2])
            accel = (accel_s[1], -accel_s[0], accel_s[2])
            mag = (mag_s[1], -mag_s[0], mag_s[2])
        elif self.sensor_orientation == "x_forward_flipped":
            gyro = (gyro_s[0], -gyro_s[1], -gyro_s[2])
            accel = (accel_s[0], -accel_s[1], -accel_s[2])
            mag = (mag_s[0], -mag_s[1], -mag_s[2])
        else:  # "x_forward"
            gyro = gyro_s
            accel = accel_s
            mag = mag_s

        return probe, gyro, accel, mag, mag_s


class L3gd20Lsm303dReaderNode(Node):
    def __init__(self) -> None:
        super().__init__("navbot_l3gd20_lsm303d_reader")
        self.declare_parameter("i2c_bus", 1)
        self.declare_parameter("gyro_address", 0x69)
        self.declare_parameter("accel_address", 0x19)
        self.declare_parameter("mag_address", 0x1E)
        self.declare_parameter("poll_hz", 20.0)
        self.declare_parameter("frame_id", "imu_link")
        self.declare_parameter("sensor_orientation", "y_forward")
        self.declare_parameter("gyro_rad_per_sec_per_lsb", 8.75e-3 * math.pi / 180.0)
        self.declare_parameter("accel_mps2_per_lsb", 0.061e-3 * 9.80665)
        self.declare_parameter("mag_tesla_per_lsb_xy", 1.0e-4 / 1100.0)
        self.declare_parameter("mag_tesla_per_lsb_z", 1.0e-4 / 980.0)
        self.declare_parameter("angular_velocity_variance", 0.0004)
        self.declare_parameter("linear_acceleration_variance", 0.04)
        self.declare_parameter("magnetic_field_variance", 1.0e-10)
        self.declare_parameter("mag_offset_x_t", 0.0)
        self.declare_parameter("mag_offset_y_t", 0.0)
        self.declare_parameter("mag_offset_z_t", 0.0)
        self.declare_parameter("mag_scale_x", 1.0)
        self.declare_parameter("mag_scale_y", 1.0)
        self.declare_parameter("mag_scale_z", 1.0)
        self.declare_parameter("magnetic_declination_rad", 0.0)
        self.declare_parameter("yaw_offset_rad", 0.0)
        self.declare_parameter("yaw_sign", 1.0)
        self.declare_parameter("ypr_filter_alpha", 0.35)

        self.reader = L3gd20Lsm303dReader(
            i2c_bus=int(self.get_parameter("i2c_bus").value),
            gyro_address=int(self.get_parameter("gyro_address").value),
            accel_address=int(self.get_parameter("accel_address").value),
            mag_address=int(self.get_parameter("mag_address").value),
            gyro_rad_per_sec_per_lsb=float(self.get_parameter("gyro_rad_per_sec_per_lsb").value),
            accel_mps2_per_lsb=float(self.get_parameter("accel_mps2_per_lsb").value),
            mag_tesla_per_lsb_xy=float(self.get_parameter("mag_tesla_per_lsb_xy").value),
            mag_tesla_per_lsb_z=float(self.get_parameter("mag_tesla_per_lsb_z").value),
            sensor_orientation=str(self.get_parameter("sensor_orientation").value),
        )
        self.frame_id = str(self.get_parameter("frame_id").value)
        self.angular_velocity_variance = float(self.get_parameter("angular_velocity_variance").value)
        self.linear_acceleration_variance = float(self.get_parameter("linear_acceleration_variance").value)
        self.magnetic_field_variance = float(self.get_parameter("magnetic_field_variance").value)
        self.mag_offset = (
            float(self.get_parameter("mag_offset_x_t").value),
            float(self.get_parameter("mag_offset_y_t").value),
            float(self.get_parameter("mag_offset_z_t").value),
        )
        self.mag_scale = (
            float(self.get_parameter("mag_scale_x").value),
            float(self.get_parameter("mag_scale_y").value),
            float(self.get_parameter("mag_scale_z").value),
        )
        self.magnetic_declination_rad = float(self.get_parameter("magnetic_declination_rad").value)
        self.yaw_offset_rad = float(self.get_parameter("yaw_offset_rad").value)
        self.yaw_sign = 1.0 if float(self.get_parameter("yaw_sign").value) >= 0.0 else -1.0
        self.ypr_filter_alpha = min(1.0, max(0.0, float(self.get_parameter("ypr_filter_alpha").value)))
        self._filtered_yaw: Optional[float] = None

        self.imu_pub = self.create_publisher(Imu, "/imu/l3gd20_lsm303d/raw", 10)
        self.mag_pub = self.create_publisher(MagneticField, "/imu/l3gd20_lsm303d/mag", 10)
        self.ypr_pub = self.create_publisher(Vector3Stamped, "/imu/l3gd20_lsm303d/ypr", 10)
        self.status_pub = self.create_publisher(String, "/imu/l3gd20_lsm303d/status", 10)

        poll_hz = max(0.5, float(self.get_parameter("poll_hz").value))
        self.timer = self.create_timer(1.0 / poll_hz, self._poll)
        self._last_error: Optional[str] = None

    def _publish_status(self, payload: dict) -> None:
        msg = String()
        msg.data = json.dumps(payload, sort_keys=True)
        self.status_pub.publish(msg)

    def _poll(self) -> None:
        try:
            # gyro, accel, mag are in robot frame (X=forward, Y=left, Z=up).
            # mag_sensor is in sensor frame for applying sensor-frame calibration.
            probe, gyro, accel, mag, mag_sensor = self.reader.read_sample()
            now = self.get_clock().now().to_msg()

            # Publish IMU in robot frame.
            imu_msg = Imu()
            imu_msg.header.stamp = now
            imu_msg.header.frame_id = self.frame_id
            imu_msg.orientation_covariance[0] = -1.0
            imu_msg.angular_velocity_covariance[0] = self.angular_velocity_variance
            imu_msg.angular_velocity_covariance[4] = self.angular_velocity_variance
            imu_msg.angular_velocity_covariance[8] = self.angular_velocity_variance
            imu_msg.linear_acceleration_covariance[0] = self.linear_acceleration_variance
            imu_msg.linear_acceleration_covariance[4] = self.linear_acceleration_variance
            imu_msg.linear_acceleration_covariance[8] = self.linear_acceleration_variance
            imu_msg.angular_velocity.x = gyro[0]
            imu_msg.angular_velocity.y = gyro[1]
            imu_msg.angular_velocity.z = gyro[2]
            imu_msg.linear_acceleration.x = accel[0]
            imu_msg.linear_acceleration.y = accel[1]
            imu_msg.linear_acceleration.z = accel[2]
            self.imu_pub.publish(imu_msg)

            # Publish magnetometer in robot frame with hard-iron
            # calibration applied. Offsets live in config in sensor
            # frame; with sensor_orientation=x_forward (identity
            # remap) the robot-frame mag equals sensor-frame mag, so
            # subtracting the sensor-frame offsets is correct. If
            # sensor_orientation is changed, recalibrate the offsets
            # in the new mount — the values will not transfer.
            mag_msg = MagneticField()
            mag_msg.header.stamp = now
            mag_msg.header.frame_id = self.frame_id
            mag_msg.magnetic_field_covariance[0] = self.magnetic_field_variance
            mag_msg.magnetic_field_covariance[4] = self.magnetic_field_variance
            mag_msg.magnetic_field_covariance[8] = self.magnetic_field_variance
            mag_msg.magnetic_field.x = (mag[0] - self.mag_offset[0]) * self.mag_scale[0]
            mag_msg.magnetic_field.y = (mag[1] - self.mag_offset[1]) * self.mag_scale[1]
            mag_msg.magnetic_field.z = (mag[2] - self.mag_offset[2]) * self.mag_scale[2]
            self.mag_pub.publish(mag_msg)

            # Compass heading: apply sensor-frame calibration offsets/scales,
            # then remap to robot frame for YPR computation.
            # Config offsets (mag_offset_x_t, etc.) are in sensor frame.
            cal_sx = (mag_sensor[0] - self.mag_offset[0]) * self.mag_scale[0]
            cal_sy = (mag_sensor[1] - self.mag_offset[1]) * self.mag_scale[1]
            cal_sz = (mag_sensor[2] - self.mag_offset[2]) * self.mag_scale[2]
            # Remap calibrated mag to robot frame for YPR.
            calibrated_mag = (cal_sy, -cal_sx, cal_sz)
            yaw, pitch, roll = _compute_ypr(accel, calibrated_mag)
            yaw = _wrap_pi(
                (yaw * self.yaw_sign) + self.magnetic_declination_rad + self.yaw_offset_rad
            )
            if self._filtered_yaw is None:
                self._filtered_yaw = yaw
            else:
                self._filtered_yaw = _wrap_pi(
                    self._filtered_yaw
                    + (self.ypr_filter_alpha * _wrap_pi(yaw - self._filtered_yaw))
                )
            heading_deg = (math.degrees(self._filtered_yaw) + 360.0) % 360.0

            ypr_msg = Vector3Stamped()
            ypr_msg.header.stamp = now
            ypr_msg.header.frame_id = self.frame_id
            # Vector order is explicit in the topic name: x=yaw, y=pitch, z=roll.
            ypr_msg.vector.x = self._filtered_yaw
            ypr_msg.vector.y = pitch
            ypr_msg.vector.z = roll
            self.ypr_pub.publish(ypr_msg)

            self._publish_status(
                {
                    "available": True,
                    "message": probe.message,
                    "gyro_available": probe.gyro_available,
                    "accel_available": probe.accel_available,
                    "mag_available": probe.mag_available,
                    "gyro_address": probe.gyro_address,
                    "accel_address": probe.accel_address,
                    "mag_address": probe.mag_address,
                    "gyro_id": probe.gyro_id,
                    "accel_id": probe.accel_id,
                    "mag_id": probe.mag_id,
                    "variant": probe.variant,
                    "frame_id": self.frame_id,
                    "yaw_rad": self._filtered_yaw,
                    "pitch_rad": pitch,
                    "roll_rad": roll,
                    "heading_deg": heading_deg,
                }
            )
            if self._last_error is not None:
                self.get_logger().info("IMU read recovered")
                self._last_error = None
        except Exception as exc:  # pragma: no cover
            message = str(exc)
            self._publish_status({"available": False, "message": message, "frame_id": self.frame_id})
            if message != self._last_error:
                self.get_logger().warning(f"IMU read failed: {message}")
                self._last_error = message
            self.reader.close()

    def destroy_node(self) -> bool:
        self.reader.close()
        return super().destroy_node()


def main() -> None:
    rclpy.init()
    node = L3gd20Lsm303dReaderNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
