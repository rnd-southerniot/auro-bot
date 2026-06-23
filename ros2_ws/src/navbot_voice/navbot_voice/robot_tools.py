"""Robot tool executor + localhost control server (P5).

``RobotTools`` is the single place motion actually happens: it maps the small
tool set (set_drive_mode / drive / stop / get_status / set_face) onto the
navbot_web control surface (/api/*) under the :class:`SafetyGate`, and onto the
buddy face via a callback. It is brain-agnostic — driven by either the Claude
Code brain (over the local control server below) or the in-process SDK agent.

``serve_tools`` exposes those methods over a loopback HTTP server so a *separate*
process (the ``navbotctl`` CLI invoked by headless ``claude -p``) can call them
while the **drive loop and the on-device "stop" word still share one
SafetyGate** — both live in this (the brain's) process, so a stop aborts an
in-flight drive correctly. The Pico is never touched; motion is /api/* only.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from navbot_voice.robot_client import RobotClient
from navbot_voice.safety import SafetyGate

FACE_STATES = {"idle", "listening", "thinking", "speaking", "driving", "halted", "low_battery"}


class RobotTools:
    def __init__(
        self,
        robot: RobotClient,
        safety: SafetyGate,
        set_face: Callable[[str], None] | None = None,
    ) -> None:
        self.robot = robot
        self.safety = safety
        self._face = set_face or (lambda _state: None)

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

    def drive(self, linear: Any, angular: Any, duration: Any) -> str:
        try:
            status = self.robot.get_status()
        except Exception:  # noqa: BLE001
            status = {}
        ok, reason = self.safety.can_move(status)
        if not ok:
            return f"refused to move: {reason}"

        lin, ang, dur = self.safety.clamp(linear, angular, duration)
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
