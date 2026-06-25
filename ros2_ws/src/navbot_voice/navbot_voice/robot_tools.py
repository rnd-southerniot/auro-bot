"""Robot tool executor + localhost control server (P5).

``RobotTools`` is the single place motion actually happens: it maps the small
tool set (set_drive_mode / drive / stop / get_status / set_face / look) onto the
navbot_web control surface (/api/*) under the :class:`SafetyGate`, the buddy face
via a callback, and the XIAO camera via :class:`CameraClient` (look). It is
brain-agnostic — driven by either the Claude Code brain (over the local control
server below) or the in-process SDK agent.

``serve_tools`` exposes those methods over a loopback HTTP server so a *separate*
process (the ``navbotctl`` CLI invoked by headless ``claude -p``) can call them
while the **drive loop and the on-device "stop" word still share one
SafetyGate** — both live in this (the brain's) process, so a stop aborts an
in-flight drive correctly. The Pico is never touched; motion is /api/* only.
"""
from __future__ import annotations

import json
import math
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from navbot_voice.camera_client import CameraClient
from navbot_voice.robot_client import RobotClient
from navbot_voice.safety import SafetyGate

FACE_STATES = {"idle", "listening", "thinking", "speaking", "driving", "halted", "low_battery"}


class RobotTools:
    def __init__(
        self,
        robot: RobotClient,
        safety: SafetyGate,
        set_face: Callable[[str], None] | None = None,
        camera: CameraClient | None = None,
    ) -> None:
        self.robot = robot
        self.safety = safety
        self._face = set_face or (lambda _state: None)
        self.camera = camera or CameraClient()

    def set_drive_mode(self, enabled: bool) -> str:
        self.safety.set_drive_mode(bool(enabled))
        return "drive mode " + ("enabled" if enabled else "disabled")

    def stop(self) -> str:
        self._face("halted")
        try:
            self.robot.stop()
        except Exception as exc:  # noqa: BLE001
            return f"stop request failed: {exc}"
        self.safety.halt()
        return "stopped"

    def get_status(self) -> str:
        try:
            return self.robot.summarize_status(self.robot.get_status())
        except Exception as exc:  # noqa: BLE001
            return f"status unavailable: {exc}"

    def set_face(self, state: str) -> str:
        state = str(state)
        if state not in FACE_STATES:
            return f"unknown face state: {state}"
        self._face(state)
        return "ok"

    def look(self) -> str:
        """Grab a fresh camera frame; return the saved JPEG path (for the brain to read)."""
        self._face("thinking")
        try:
            path = self.camera.grab()
        except Exception as exc:  # noqa: BLE001
            return f"camera unavailable: {exc}"
        finally:
            self._face("idle")
        return f"saved camera frame to {path}"

    def drive(self, linear: Any, angular: Any, duration: Any) -> str:
        try:
            status = self.robot.get_status()
        except Exception:  # noqa: BLE001
            status = {}
        ok, reason = self.safety.can_move(status)
        if not ok:
            return f"refused to move: {reason}"

        lin, ang, dur = self.safety.clamp(linear, angular, duration)
        dur, budget_reason = self.safety.reserve_motion(dur)
        if dur <= 0.0:
            return f"refused to move: {budget_reason}"
        self.safety.begin_move()
        self._face("driving")
        aborted = False
        deadline = time.time() + dur
        try:
            while time.time() < deadline:
                if self.safety.aborted:
                    aborted = True
                    break
                try:
                    self.robot.cmd_vel(lin, ang)  # ~5 Hz keeps the web 0.35 s watchdog alive
                except Exception as exc:  # noqa: BLE001
                    self._face("idle")
                    return f"drive command failed: {exc}"
                time.sleep(0.2)
        finally:
            try:
                self.robot.stop()
            except Exception:  # noqa: BLE001
                pass
        self._face("idle")
        if aborted:
            return "stopped early"
        return f"moved (linear {lin:.2f}, angular {ang:.2f}) for {dur:.1f} s"

    # -- in-place rotation (shared by look_around + turn) --
    # Closed-loop on the IMU *gyro*: we integrate the z-axis angular rate to
    # measure how far we have ACTUALLY rotated, rather than trusting
    # commanded-time x rate (the old open-loop spin, which wheel slip silently
    # corrupted -- a "turn 67" could land ~30 deg off). We use the gyro rate,
    # NOT the compass yaw: imu.yaw_rad is magnetometer-derived and indoors near
    # the motors it barely tracks rotation (measured +2.8 deg over a real 60+
    # deg turn), so it is useless here. If the IMU is unavailable we degrade to
    # the original timed spin. Angular-only, never translates, so exempt from
    # the linear motion budget; still drive-mode gated, e-stop checked, bounded
    # by a hard time ceiling, and abortable by the "stop" word.
    _ROTATE_RATE = min(SafetyGate.MAX_ANGULAR, 0.5)   # rad/s cruise (shared so headings stay self-consistent)
    _SPIN_MIN_RATE = min(_ROTATE_RATE, 0.25)          # rad/s floor so we still close the last few degrees
    _SPIN_KP = 1.5                                    # rad/s per rad of remaining angle (slow down near target)
    _SPIN_STOP_LEAD = math.radians(2.0)               # stop this far short, for command/stop latency
    _SPIN_CEILING_FACTOR = 2.5                        # hard time ceiling = this x the nominal time

    def _gyro_z(self) -> float | None:
        """Live IMU z-axis angular rate (rad/s, + = CCW), or None if unusable."""
        try:
            imu = (self.robot.get_status() or {}).get("imu") or {}
        except Exception:  # noqa: BLE001
            return None
        gz = imu.get("angular_velocity_z")
        if not imu.get("alive") or not isinstance(gz, (int, float)) or math.isnan(gz):
            return None
        return float(gz)

    def _gyro_bias(self) -> float | None:
        """Average the gyro at rest to cancel its zero-rate offset; None if no IMU."""
        samples = []
        for _ in range(4):
            gz = self._gyro_z()
            if gz is not None:
                samples.append(gz)
            time.sleep(0.04)
        if len(samples) < 2:
            return None
        return sum(samples) / len(samples)

    def _spin_timed(self, radians_to_turn: float) -> bool:
        """Open-loop timed spin -- fallback used only when the IMU is unavailable."""
        ang = math.copysign(self._ROTATE_RATE, radians_to_turn)
        deadline = time.monotonic() + abs(radians_to_turn) / self._ROTATE_RATE
        while time.monotonic() < deadline:
            if self.safety.aborted:
                return True
            self.robot.cmd_vel(0.0, ang)  # keeps the web watchdog open
            time.sleep(0.1)
        return False

    def _spin(self, radians_to_turn: float) -> bool:
        """Rotate in place by ``radians_to_turn`` (+ = left/CCW). Returns True if aborted."""
        if abs(radians_to_turn) < 1e-3:
            return False
        direction = math.copysign(1.0, radians_to_turn)
        target = abs(radians_to_turn)
        bias = self._gyro_bias()  # also gives the IMU a beat to prove it's alive
        try:
            if bias is None:  # no usable IMU -> degrade to the old timed spin
                return self._spin_timed(radians_to_turn)
            turned = 0.0
            last = time.monotonic()
            ceiling = last + (target / self._ROTATE_RATE) * self._SPIN_CEILING_FACTOR + 1.0
            while True:
                if self.safety.aborted:
                    return True
                now = time.monotonic()
                remaining = target - abs(turned)
                if remaining <= self._SPIN_STOP_LEAD or now >= ceiling:
                    return False
                rate = max(self._SPIN_MIN_RATE, min(self._ROTATE_RATE, self._SPIN_KP * remaining))
                self.robot.cmd_vel(0.0, direction * rate)  # command first to hold the watchdog open
                time.sleep(0.06)
                gz = self._gyro_z()
                t2 = time.monotonic()
                if gz is not None:  # integrate actual rotation; a missing sample just isn't counted
                    turned += (gz - bias) * (t2 - last)
                last = t2
        finally:
            try:
                self.robot.stop()
            except Exception:  # noqa: BLE001
                pass

    def look_around(self, steps: Any = 8, target: Any = "") -> str:
        """Sweep a full 360° in place, grabbing one stationary frame per heading.

        Returns the heading->image-path list for the brain to Read and search;
        this tool does not judge image content. The robot ends back near its
        start heading (steps * step-angle == 360°). Pair with ``turn`` to face a
        target once the brain has found it.
        """
        try:
            status = self.robot.get_status()
        except Exception:  # noqa: BLE001
            status = {}
        ok, reason = self.safety.can_move(status)
        if not ok:
            return f"refused to look around: {reason}"

        try:
            steps = int(steps)
        except (TypeError, ValueError):
            steps = 8
        steps = max(4, min(12, steps))
        target = str(target or "").strip()

        self.safety.begin_move()
        step_rad = 2.0 * math.pi / steps
        frames: list[tuple[int, str]] = []
        aborted = False
        for i in range(steps):
            if self.safety.aborted:
                aborted = True
                break
            self._face("thinking")
            heading = round(i * 360.0 / steps)
            try:
                path = self.camera.grab(tag=f"scan{i:02d}")
            except Exception as exc:  # noqa: BLE001
                path = f"(camera error: {exc})"
            frames.append((heading, path))
            if self._spin(step_rad):  # rotate to the next heading
                aborted = True
                break
        self._face("idle")
        if not frames:
            return "look-around captured no frames"
        lines = "\n".join(f"  {h:>3} deg -> {p}" for h, p in frames)
        head = (
            f"swept {len(frames)} headings"
            + (f" looking for '{target}'" if target else "")
            + (" (aborted early)" if aborted else "")
            + ". Read each frame to find the target, then `turn <degrees>` to face it:\n"
        )
        return head + lines

    def turn(self, degrees: Any) -> str:
        """Rotate in place by a relative angle (+ = left/CCW), to face a target."""
        try:
            status = self.robot.get_status()
        except Exception:  # noqa: BLE001
            status = {}
        ok, reason = self.safety.can_move(status)
        if not ok:
            return f"refused to turn: {reason}"
        try:
            deg = float(degrees)
        except (TypeError, ValueError):
            return "turn needs a number of degrees"
        deg = max(-360.0, min(360.0, deg))
        self.safety.begin_move()
        self._face("driving")
        aborted = self._spin(math.radians(deg))
        self._face("idle")
        if aborted:
            return "stopped early"
        return f"turned {deg:.0f} degrees"

    # -- dispatch by name (shared by the control server and the SDK agent) --
    def dispatch(self, name: str, args: dict[str, Any]) -> str:
        try:
            if name == "set_drive_mode":
                return self.set_drive_mode(bool(args.get("enabled")))
            if name == "drive":
                return self.drive(args.get("linear", 0.0), args.get("angular", 0.0), args.get("duration", 0.0))
            if name == "stop":
                return self.stop()
            if name == "get_status":
                return self.get_status()
            if name == "set_face":
                return self.set_face(args.get("state", "idle"))
            if name == "look":
                return self.look()
            if name == "look_around":
                return self.look_around(args.get("steps", 8), args.get("target", ""))
            if name == "turn":
                return self.turn(args.get("degrees", 0.0))
        except Exception as exc:  # noqa: BLE001
            return f"error: {exc}"
        return f"unknown tool: {name}"


def serve_tools(tools: RobotTools, host: str = "127.0.0.1", port: int = 8077) -> ThreadingHTTPServer:
    """Start a loopback control server over ``tools`` in a daemon thread.

    POST /tool/<name> with a JSON body -> {"result": "<string>"}. Loopback only;
    no auth (it never leaves localhost and only reaches the already-gated /api/*).
    """

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: Any) -> None:  # silence default stderr logging
            pass

        def do_POST(self) -> None:  # noqa: N802
            if not self.path.startswith("/tool/"):
                self.send_response(404)
                self.end_headers()
                return
            name = self.path[len("/tool/"):]
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length else b""
            try:
                args = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                args = {}
            result = tools.dispatch(name, args if isinstance(args, dict) else {})
            body = json.dumps({"result": result}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
