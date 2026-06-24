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
    # Angular-only, never translates, so it is exempt from the linear motion
    # budget; bounded instead by the requested angle (<= one full turn). Still
    # drive-mode gated, e-stop checked, and abortable by the "stop" word.
    _ROTATE_RATE = min(SafetyGate.MAX_ANGULAR, 0.5)  # rad/s, shared so headings stay self-consistent

    def _spin(self, radians_to_turn: float) -> bool:
        """Rotate in place by ``radians_to_turn`` (+ = left/CCW). Returns True if aborted."""
        if abs(radians_to_turn) < 1e-3:
            return False
        ang = math.copysign(self._ROTATE_RATE, radians_to_turn)
        deadline = time.time() + abs(radians_to_turn) / self._ROTATE_RATE
        try:
            while time.time() < deadline:
                if self.safety.aborted:
                    return True
                self.robot.cmd_vel(0.0, ang)  # ~5 Hz holds the web watchdog open
                time.sleep(0.2)
        finally:
            try:
                self.robot.stop()
            except Exception:  # noqa: BLE001
                pass
        return False

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
