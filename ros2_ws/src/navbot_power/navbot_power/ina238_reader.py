"""INA238 driver for the Navbot Pi 5 power rail monitor.

Hardware: Adafruit INA238 breakout (STEMMA QT), 15 mOhm shunt on-board.
I2C address: 0x40 (configurable via A0/A1 jumpers).
Bus: I2C bus 1 on Raspberry Pi 5.

Datasheet reference: TI SBOSA20C (INA237, February 2021, revised 2024).
    NOTE: INA237 and INA238 are register-identical. Only gain error and
    offset specs differ; this driver works for both parts.

Register map highlights (SBOSA20C):
    0x00  CONFIG        RW  (default 0x0000)
    0x01  ADC_CONFIG    RW  (default 0xFB68 -- continuous all, 1052 us, avg=1)
    0x02  SHUNT_CAL     RW  (default 0x1000; CURRENT=0, POWER=0 when 0)
    0x04  VSHUNT        RO  (5 uV or 1.25 uV / LSB per ADCRANGE, two's compl.)
    0x05  VBUS          RO  (3.125 mV / LSB, positive only)
    0x06  DIETEMP       RO  (125 m degC / LSB, two's complement)
    0x07  CURRENT       RO  (CURRENT_LSB, computed from SHUNT_CAL)
    0x08  POWER         RO  (24-bit, 0.2 * CURRENT_LSB / LSB)
    0x0B  DIAG_ALRT     RW  (default 0x0001)
    0x3E  MANUFACTURER_ID  RO  (0x5449 = 'TI' ASCII)
    0x3F  DEVICE_ID        RO  (DIEID 0x23 in upper byte; rev in lower byte.
                                 Our chip reads 0x2380. Register is present
                                 in SBOSA20C but NOT documented in the older
                                 SBOSA20A revision -- this gap caused
                                 confusion during Phase C driver debugging.)

Deployment context: this chip monitors System 1 (Pi compute rail) only.
See docs/power-architecture.md for full robot power architecture, including
the important caveat that the Pi 5 GPIO 5V pin is NOT isolated from the
battery rail when the Pi is on USB-C wall power (0.94 A measured through
the INA238 shunt with Pi on wall adapter, 2026-04-20).

Driver state as of commit b309625: production. Publish rate: 2 Hz.
Topics: /power/ina238/{bus_voltage_v, current_a, power_w, temperature_c,
                        shunt_voltage_v, status}.
"""

import json
import math
from dataclasses import dataclass
from typing import Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32, String

try:
    from smbus2 import SMBus
except ImportError:  # pragma: no cover
    SMBus = None


REG_CONFIG = 0x00
REG_ADC_CONFIG = 0x01
REG_SHUNT_CAL = 0x02
REG_VSHUNT = 0x04
REG_VBUS = 0x05
REG_DIETEMP = 0x06
REG_CURRENT = 0x07
REG_POWER = 0x08
REG_DIAG_ALRT = 0x0B
REG_MANUFACTURER_ID = 0x3E
REG_DEVICE_ID = 0x3F

MANUFACTURER_ID_TI = 0x5449
DEVICE_ID_INA238 = 0x2380

# ADC_CONFIG value written at init:
#   MODE   = 0xF (continuous bus+shunt+temp)
#   VBUSCT = 0x5 (1052 us conversion)
#   VSHCT  = 0x5 (1052 us conversion)
#   VTCT   = 0x5 (1052 us conversion)
#   AVG    = 0x2 (16 samples — ~50 ms per averaged output, ~20 Hz effective)
# At 2 Hz poll rate the driver reads one of many already-averaged values,
# giving low-noise telemetry on a switching-regulator rail.
ADC_CONFIG_VALUE = 0xFB6A

# CONFIG bit 4 = ADCRANGE. 0 = +/-163.84 mV (5 uV/LSB), 1 = +/-40.96 mV (1.25 uV/LSB).
# ADCRANGE=1 gives 4x better current resolution at the cost of a lower max range.


@dataclass
class Ina238Status:
    available: bool
    message: str
    bus_voltage_v: float = math.nan
    current_a: float = math.nan
    power_w: float = math.nan
    temperature_c: float = math.nan
    shunt_voltage_v: float = math.nan
    config_raw: int = 0
    adc_config_raw: int = 0
    shunt_cal_raw: int = 0
    diag_alert_raw: int = 0
    manufacturer_id: int = 0
    device_id: int = 0
    power_raw: int = 0


class Ina238Reader:
    def __init__(
        self,
        i2c_bus: int,
        address: int,
        shunt_resistance_ohm: float,
        max_current_a: float,
        adcrange: int = 1,
    ) -> None:
        self.i2c_bus = i2c_bus
        self.address = address
        self.shunt_resistance_ohm = shunt_resistance_ohm
        self.max_current_a = max_current_a
        self.adcrange = 1 if adcrange else 0
        self.current_lsb = max_current_a / 32768.0
        self.power_lsb = self.current_lsb * 0.2
        # SHUNT_CAL gets a 4x multiplier when ADCRANGE=1 per datasheet eq. 2.
        cal_multiplier = 4 if self.adcrange else 1
        self.shunt_cal = max(
            1,
            min(0xFFFF, int(round(
                819_200_000.0 * self.current_lsb * self.shunt_resistance_ohm * cal_multiplier
            ))),
        )
        self.config_value = (self.adcrange & 0x1) << 4
        self._bus: Optional[SMBus] = None

    def connect(self) -> None:
        if SMBus is None:
            raise RuntimeError("python3-smbus2 is not installed")
        if self._bus is None:
            self._bus = SMBus(self.i2c_bus)
            # Refuse to program the chip unless the identity matches INA238.
            mfg = self._read_u16(REG_MANUFACTURER_ID)
            dev = self._read_u16(REG_DEVICE_ID)
            if mfg != MANUFACTURER_ID_TI or (dev & 0xFFF0) != DEVICE_ID_INA238:
                self._bus.close()
                self._bus = None
                raise RuntimeError(
                    f"INA238 identity mismatch: MFG=0x{mfg:04X} DEV=0x{dev:04X}, "
                    f"expected MFG=0x{MANUFACTURER_ID_TI:04X} DEV=0x{DEVICE_ID_INA238:04X}"
                )
            # CONFIG: set ADCRANGE per driver configuration.
            self._write_u16(REG_CONFIG, self.config_value)
            # ADC_CONFIG: continuous mode with 16-sample averaging.
            self._write_u16(REG_ADC_CONFIG, ADC_CONFIG_VALUE)
            # SHUNT_CAL: computed current-to-digital calibration.
            self._write_u16(REG_SHUNT_CAL, self.shunt_cal)

    def close(self) -> None:
        if self._bus is not None:
            self._bus.close()
            self._bus = None

    def _read_u16(self, reg: int) -> int:
        assert self._bus is not None
        raw = self._bus.read_word_data(self.address, reg)
        return ((raw & 0xFF) << 8) | (raw >> 8)

    def _read_u24(self, reg: int) -> int:
        assert self._bus is not None
        data = self._bus.read_i2c_block_data(self.address, reg, 3)
        return (data[0] << 16) | (data[1] << 8) | data[2]

    def _write_u16(self, reg: int, value: int) -> None:
        assert self._bus is not None
        raw = ((value & 0xFF) << 8) | ((value >> 8) & 0xFF)
        self._bus.write_word_data(self.address, reg, raw)

    @staticmethod
    def _to_signed(value: int) -> int:
        return value - 0x10000 if value & 0x8000 else value

    @staticmethod
    def _dietemp_celsius(temp_raw: int) -> float:
        value = temp_raw >> 4
        if value & 0x800:
            value -= 0x1000
        return value * 0.125

    def read_status(self) -> Ina238Status:
        self.connect()
        assert self._bus is not None

        config = self._read_u16(REG_CONFIG)
        adc_config = self._read_u16(REG_ADC_CONFIG)
        shunt_cal = self._read_u16(REG_SHUNT_CAL)
        vshunt_raw = self._read_u16(REG_VSHUNT)
        vbus_raw = self._read_u16(REG_VBUS)
        temp_raw = self._read_u16(REG_DIETEMP)
        current_raw = self._read_u16(REG_CURRENT)
        power_raw = self._read_u24(REG_POWER)
        diag_alert = self._read_u16(REG_DIAG_ALRT)
        manufacturer_id = self._read_u16(REG_MANUFACTURER_ID)
        device_id = self._read_u16(REG_DEVICE_ID)

        adcrange = (config >> 4) & 0x1
        shunt_lsb = 1.25e-6 if adcrange else 5.0e-6

        bus_voltage_v = vbus_raw * 3.125e-3
        shunt_voltage_v = self._to_signed(vshunt_raw) * shunt_lsb
        temperature_c = self._dietemp_celsius(temp_raw)
        current_a = self._to_signed(current_raw) * self.current_lsb
        power_w = power_raw * self.power_lsb

        available = manufacturer_id == MANUFACTURER_ID_TI and (device_id & 0xFFF0) == DEVICE_ID_INA238
        if available:
            message = "INA238 responding on I2C"
        else:
            message = "I2C device responded, but ID registers do not match INA238"

        return Ina238Status(
            available=available,
            message=message,
            bus_voltage_v=bus_voltage_v,
            current_a=current_a,
            power_w=power_w,
            temperature_c=temperature_c,
            shunt_voltage_v=shunt_voltage_v,
            config_raw=config,
            adc_config_raw=adc_config,
            shunt_cal_raw=shunt_cal,
            diag_alert_raw=diag_alert,
            manufacturer_id=manufacturer_id,
            device_id=device_id,
            power_raw=power_raw,
        )


class Ina238ReaderNode(Node):
    def __init__(self) -> None:
        super().__init__("navbot_ina238_reader")
        self.declare_parameter("i2c_bus", 1)
        self.declare_parameter("i2c_address", 0x40)
        self.declare_parameter("shunt_resistance_ohm", 0.015)
        self.declare_parameter("max_current_a", 3.0)
        self.declare_parameter("adcrange", 1)
        self.declare_parameter("poll_hz", 2.0)

        self.reader = Ina238Reader(
            i2c_bus=int(self.get_parameter("i2c_bus").value),
            address=int(self.get_parameter("i2c_address").value),
            shunt_resistance_ohm=float(self.get_parameter("shunt_resistance_ohm").value),
            max_current_a=float(self.get_parameter("max_current_a").value),
            adcrange=int(self.get_parameter("adcrange").value),
        )

        self.bus_voltage_pub = self.create_publisher(Float32, "/power/ina238/bus_voltage_v", 10)
        self.current_pub = self.create_publisher(Float32, "/power/ina238/current_a", 10)
        self.power_pub = self.create_publisher(Float32, "/power/ina238/power_w", 10)
        self.temperature_pub = self.create_publisher(Float32, "/power/ina238/temperature_c", 10)
        self.shunt_voltage_pub = self.create_publisher(Float32, "/power/ina238/shunt_voltage_v", 10)
        self.status_pub = self.create_publisher(String, "/power/ina238/status", 10)

        # Perform an initial read so we can emit a startup diagnostic line.
        # Surfaces wiring or chip-identity problems during bringup rather than
        # silently publishing zeros. See Phase C investigation 2026-04-20.
        try:
            initial = self.reader.read_status()
            self.get_logger().info(
                f"INA238 init: MFG=0x{initial.manufacturer_id:04X} "
                f"DEV=0x{initial.device_id:04X} "
                f"VBUS={initial.bus_voltage_v:.3f}V "
                f"SHUNT_CAL={initial.shunt_cal_raw} "
                f"ADCRANGE={(initial.config_raw >> 4) & 1} "
                f"available={initial.available}"
            )
        except Exception as exc:
            self.get_logger().warning(f"INA238 initial probe failed: {exc}")

        poll_hz = max(0.1, float(self.get_parameter("poll_hz").value))
        self.timer = self.create_timer(1.0 / poll_hz, self._poll)
        self._last_error: Optional[str] = None

    def _publish_float(self, publisher, value: float) -> None:
        msg = Float32()
        msg.data = float(value)
        publisher.publish(msg)

    def _publish_status(self, payload: dict) -> None:
        msg = String()
        msg.data = json.dumps(payload, sort_keys=True)
        self.status_pub.publish(msg)

    def _poll(self) -> None:
        try:
            status = self.reader.read_status()
            self._publish_float(self.bus_voltage_pub, status.bus_voltage_v)
            self._publish_float(self.current_pub, status.current_a)
            self._publish_float(self.power_pub, status.power_w)
            self._publish_float(self.temperature_pub, status.temperature_c)
            self._publish_float(self.shunt_voltage_pub, status.shunt_voltage_v)
            payload = {
                "available": status.available,
                "message": status.message,
                "bus_voltage_v": status.bus_voltage_v,
                "current_a": status.current_a,
                "power_w": status.power_w,
                "temperature_c": status.temperature_c,
                "shunt_voltage_v": status.shunt_voltage_v,
                "config_raw": status.config_raw,
                "adc_config_raw": status.adc_config_raw,
                "shunt_cal_raw": status.shunt_cal_raw,
                "diag_alert_raw": status.diag_alert_raw,
                "manufacturer_id": status.manufacturer_id,
                "device_id": status.device_id,
                "power_raw": status.power_raw,
            }
            self._publish_status(payload)
            if self._last_error is not None:
                self.get_logger().info("INA238 read recovered")
                self._last_error = None
        except Exception as exc:  # pragma: no cover
            message = str(exc)
            payload = {
                "available": False,
                "message": message,
            }
            self._publish_status(payload)
            if message != self._last_error:
                self.get_logger().warning(f"INA238 read failed: {message}")
                self._last_error = message

    def destroy_node(self) -> bool:
        self.reader.close()
        return super().destroy_node()


def main() -> None:
    rclpy.init()
    node = Ina238ReaderNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
