"""Motion safety gate for the voice brain (P4/P5).

Sits on top of the robot's existing three-layer motion watchdog (web 0.35 s
``_command_timer_cb`` -> serial_bridge 0.5 s -> RP2040 0.5 s). The LLM can only
ask the robot to move through commands that are **clamped**, **drive-mode
gated**, and **abortable**; the on-device "stop" word and the hardware e-stop
both override it. Nothing here ever touches the Pico — motion goes out via
``RobotClient`` (/api/cmd_vel, /api/stop) only.

Per-call clamps bound a single ``drive`` to ``MAX_DURATION`` s, but the brain can
satisfy an over-long request (e.g. "drive for 40 seconds") by *chaining* many
clamped drives in one wake-episode. ``reserve_motion`` adds a cumulative
per-episode budget so chained drives share one cap, regardless of how the LLM
splits them. See docs/validation for the 2026-06-25 finding.

Env overrides (all optional): ``NAVBOT_MAX_LINEAR`` (m/s), ``NAVBOT_MAX_ANGULAR``
(rad/s), ``NAVBOT_MAX_DURATION`` (s), ``NAVBOT_MIN_MOTOR_V`` (V; 0 disables the
voltage gate — /api/status often reports motor_voltage as null),
``NAVBOT_MAX_EPISODE_S`` (s; cumulative drive-time per episode),
``NAVBOT_EPISODE_IDLE_S`` (s; quiet gap that starts a fresh episode).
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any


def _envf(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class SafetyGate:
    MAX_LINEAR = _envf("NAVBOT_MAX_LINEAR", 0.12)     # hard clamp, m/s
    MAX_ANGULAR = _envf("NAVBOT_MAX_ANGULAR", 0.6)    # hard clamp, rad/s
    MAX_DURATION = _envf("NAVBOT_MAX_DURATION", 3.0)  # hard clamp, s (per call)
    MIN_MOTOR_V = _envf("NAVBOT_MIN_MOTOR_V", 0.0)    # 0 = voltage gate disabled
    MAX_EPISODE_S = _envf("NAVBOT_MAX_EPISODE_S", 6.0)   # cumulative drive-time per episode, s
    EPISODE_IDLE_S = _envf("NAVBOT_EPISODE_IDLE_S", 10.0)  # quiet gap that starts a fresh episode, s

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._drive_mode = False
        self._abort = threading.Event()  # set by the on-device "stop" word
        self._episode_used = 0.0          # drive-time granted in the current episode, s
        self._episode_last_end = 0.0      # monotonic time the last grant nominally ends

    # -- drive-mode gate (OFF by default; user must opt in by voice) --
    def set_drive_mode(self, on: bool) -> None:
        with self._lock:
            self._drive_mode = bool(on)
            self._episode_used = 0.0  # a drive-mode toggle starts a fresh motion budget
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
            self._episode_used = 0.0
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

    # -- cumulative per-episode motion budget --
    def reserve_motion(self, duration: float) -> tuple[float, str]:
        """Grant up to ``duration`` s of drive-time against the episode budget.

        Drives chained within one wake-episode (each new ``drive`` arriving less
        than ``EPISODE_IDLE_S`` after the previous one ends) share a single
        ``MAX_EPISODE_S`` budget, so the brain cannot honor an over-long request
        ("drive for 40 seconds") by issuing many clamped ``MAX_DURATION`` drives.
        A quiet gap of ``EPISODE_IDLE_S`` resets the budget for a fresh command.

        Returns ``(granted_s, reason)``. ``granted_s`` may be less than
        ``duration`` (budget partly spent) or ``0.0`` when the cap is reached, in
        which case ``reason`` explains the refusal. Reserving up front (rather
        than billing actual elapsed time) errs toward stopping sooner.
        """
        now = time.monotonic()
        with self._lock:
            if now - self._episode_last_end >= self.EPISODE_IDLE_S:
                self._episode_used = 0.0
            remaining = self.MAX_EPISODE_S - self._episode_used
            granted = max(0.0, min(float(duration), remaining))
            if granted <= 1e-3:
                self._episode_last_end = now  # keep the episode "alive" so it stays capped
                return 0.0, (
                    f"reached the motion limit for one command "
                    f"({self.MAX_EPISODE_S:.0f} s); say 'stop' or wait a moment"
                )
            self._episode_used += granted
            self._episode_last_end = now + granted
            return granted, ""

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
