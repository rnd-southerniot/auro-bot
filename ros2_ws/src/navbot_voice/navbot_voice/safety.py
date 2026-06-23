"""Motion safety gate for the voice brain (P4/P5).

Sits on top of the robot's existing three-layer motion watchdog (web 0.35 s
``_command_timer_cb`` -> serial_bridge 0.5 s -> RP2040 0.5 s). The LLM can only
ask the robot to move through commands that are **clamped**, **drive-mode
gated**, and **abortable**; the on-device "stop" word and the hardware e-stop
both override it. Nothing here ever touches the Pico — motion goes out via
``RobotClient`` (/api/cmd_vel, /api/stop) only.

Env overrides (all optional): ``NAVBOT_MAX_LINEAR`` (m/s), ``NAVBOT_MAX_ANGULAR``
(rad/s), ``NAVBOT_MAX_DURATION`` (s), ``NAVBOT_MIN_MOTOR_V`` (V; 0 disables the
voltage gate — /api/status often reports motor_voltage as null).
"""
from __future__ import annotations

import os
import threading
from typing import Any


def _envf(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class SafetyGate:
    MAX_LINEAR = _envf("NAVBOT_MAX_LINEAR", 0.12)     # hard clamp, m/s
    MAX_ANGULAR = _envf("NAVBOT_MAX_ANGULAR", 0.6)    # hard clamp, rad/s
    MAX_DURATION = _envf("NAVBOT_MAX_DURATION", 3.0)  # hard clamp, s
    MIN_MOTOR_V = _envf("NAVBOT_MIN_MOTOR_V", 0.0)    # 0 = voltage gate disabled

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._drive_mode = False
        self._abort = threading.Event()  # set by the on-device "stop" word

    # -- drive-mode gate (OFF by default; user must opt in by voice) --
    def set_drive_mode(self, on: bool) -> None:
        with self._lock:
            self._drive_mode = bool(on)
        if not on:
            self._abort.set()  # leaving drive mode also kills any in-flight move

    @property
    def drive_mode(self) -> bool:
        with self._lock:
            return self._drive_mode

    # -- immediate halt (on-device "stop"/"halt" word, e-stop, or operator) --
    def halt(self) -> None:
        with self._lock:
            self._drive_mode = False
        self._abort.set()

    def begin_move(self) -> None:
        """Arm a sanctioned move: clear the abort latch so the drive loop runs."""
        self._abort.clear()

    @property
    def aborted(self) -> bool:
        return self._abort.is_set()

    # -- clamps --
    def clamp(self, linear: float, angular: float, duration: float) -> tuple[float, float, float]:
        lin = max(-self.MAX_LINEAR, min(self.MAX_LINEAR, float(linear)))
        ang = max(-self.MAX_ANGULAR, min(self.MAX_ANGULAR, float(angular)))
        dur = max(0.0, min(self.MAX_DURATION, float(duration)))
        return lin, ang, dur

    # -- live preconditions for motion --
    def can_move(self, status: dict[str, Any] | None) -> tuple[bool, str]:
        if not self.drive_mode:
            return False, "drive mode is off"
        estop = (status or {}).get("estop") or {}
        if estop.get("active"):
            return False, "the e-stop is engaged"
        batt = (status or {}).get("batteries") or {}
        volts = batt.get("motor_voltage")
        if self.MIN_MOTOR_V > 0 and isinstance(volts, (int, float)) and volts < self.MIN_MOTOR_V:
            return False, f"the motor battery is low ({volts:.1f} volts)"
        return True, ""
