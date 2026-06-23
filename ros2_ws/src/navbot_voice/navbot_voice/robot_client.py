"""Thin HTTP client for the navbot_web control surface.

The voice brain reaches the robot ONLY through the sanctioned navbot_web API
(`/api/status`, `/api/cmd_vel`, `/api/stop`) — never the Pico serial port, and
never a parallel motor path. This mirrors the endpoints in
``navbot_web/navbot_web/server.py`` and reuses its bearer-token convention
(``NAVBOT_WEB_TOKEN`` env var or ``~/.navbot_web_token``).

Motion safety is preserved by the existing three-layer watchdog: a single
``/api/cmd_vel`` post is re-published by the web server at 10 Hz for
``command_hold_timeout`` (~0.35 s) then auto-zeroed; serial_bridge zeroes after
0.5 s; the RP2040 halts after 0.5 s. To drive for a duration the caller re-posts
``cmd_vel`` at ~5 Hz then calls :meth:`stop` — see ``navbot_voice`` tools.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class RobotClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8080", timeout: float = 2.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._token = self._load_api_token()

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

    # ---- reads ----
    def get_status(self) -> dict[str, Any]:
        """GET /api/status — full robot snapshot (raises on transport error)."""
        return self._request("GET", "/api/status")

    # ---- writes (motion) ----
    def cmd_vel(self, linear: float, angular: float) -> dict[str, Any]:
        return self._request("POST", "/api/cmd_vel", {"linear": float(linear), "angular": float(angular)})

    def stop(self) -> dict[str, Any]:
        return self._request("POST", "/api/stop", {})

    # ---- internals ----
    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self._token:
            req.add_header("Authorization", f"Bearer {self._token}")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            payload = resp.read().decode("utf-8")
        return json.loads(payload) if payload else {}

    def summarize_status(self, status: dict[str, Any]) -> str:
        """One-line human/agent summary of a /api/status snapshot.

        Robust to nulls: the server converts non-finite floats (e.g. NaN motor
        voltage when no data) to JSON null, so numeric fields may be None.
        """
        def num(section: dict[str, Any] | None, key: str) -> float:
            value = (section or {}).get(key)
            return value if isinstance(value, (int, float)) else float("nan")

        ctrl = status.get("controller") or {}
        estop = status.get("estop") or {}
        odom = status.get("odom") or {}
        batt = status.get("batteries") or {}
        scan = status.get("scan") or {}
        return (
            f"controller={ctrl.get('state', '?')} "
            f"estop={'ON' if estop.get('active') else 'off'} "
            f"odom=({num(odom, 'x'):.2f},{num(odom, 'y'):.2f},yaw{num(odom, 'yaw'):.2f}) "
            f"motor_v={num(batt, 'motor_voltage'):.2f} "
            f"scan_alive={scan.get('alive', False)}"
        )
