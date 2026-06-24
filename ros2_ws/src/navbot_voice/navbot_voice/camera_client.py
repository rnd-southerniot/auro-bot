"""HTTP client for the XIAO ESP32-S3 Sense networked camera (P6 perception).

The robot's eyes are a Seeed XIAO ESP32-S3 Sense on Wi-Fi serving JPEG over HTTP
(``firmware/xiao_esp32s3_sense_cam``). The voice brain's ``look()`` /
``describe_scene()`` tools need a single fresh still — not the live MJPEG stream —
so we just ``GET <base>/snapshot``. Stdlib ``urllib`` only, same idiom as
``robot_client.py``.

Endpoints (XIAO firmware README, Phase 5.2):
  GET <base>/snapshot  -> single JPEG (control plane, :80)
  GET <base>/status    -> JSON health {fps, motion, rssi_dbm, uptime_s, ...}

Config: ``NAVBOT_CAMERA_URL`` env (default the address measured on AP "Auro").
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_CAMERA_URL = os.environ.get("NAVBOT_CAMERA_URL", "http://192.168.68.110")
# Where grabbed frames land. Absolute so the headless brain's Read tool can open
# them by path; shared with navbot_camera's default save_dir.
DEFAULT_SAVE_DIR = os.environ.get(
    "NAVBOT_CAMERA_SAVE_DIR", str(Path.home() / "navbot_captures" / "frames")
)


class CameraClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 4.0,
        save_dir: str | None = None,
    ) -> None:
        self.base_url = (base_url or DEFAULT_CAMERA_URL).rstrip("/")
        self.timeout = timeout
        self.save_dir = Path(save_dir or DEFAULT_SAVE_DIR).expanduser()

    def _get(self, path: str) -> bytes:
        with urllib.request.urlopen(f"{self.base_url}{path}", timeout=self.timeout) as resp:
            return resp.read()

    def snapshot_bytes(self) -> bytes:
        """Fetch one fresh JPEG. Raises on transport error; validates the SOI."""
        jpeg = self._get("/snapshot")
        if jpeg[:3] != b"\xff\xd8\xff":
            raise ValueError(f"camera did not return a JPEG (got {len(jpeg)} bytes)")
        return jpeg

    def grab(self, tag: str = "") -> str:
        """Fetch a snapshot, save it under save_dir, return the absolute path.

        ``tag`` is appended to the filename so rapid successive grabs (e.g. a
        ``look_around`` sweep firing several within one second) don't collide on
        the second-resolution timestamp.
        """
        jpeg = self.snapshot_bytes()
        self.save_dir.mkdir(parents=True, exist_ok=True)
        suffix = f"_{tag}" if tag else ""
        path = self.save_dir / f"frame_{time.strftime('%Y%m%d_%H%M%S')}{suffix}.jpg"
        path.write_bytes(jpeg)
        return str(path)

    def status(self) -> dict[str, Any]:
        raw = self._get("/status")
        return json.loads(raw.decode("utf-8")) if raw else {}
