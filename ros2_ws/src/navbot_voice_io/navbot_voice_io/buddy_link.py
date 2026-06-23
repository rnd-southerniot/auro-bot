"""Serial transport to the ESP32-S3 buddy.

Wraps pyserial + :class:`navbot_voice_io.protocol.FrameParser` in a background
reader thread that invokes an ``on_frame(Frame)`` callback. Send helpers cover
the protocol message types. Transport-only: the ROS node interprets frames.

pyserial is imported lazily so this module imports on machines without it.
"""
from __future__ import annotations

import threading
from typing import Callable

from navbot_voice_io import protocol
from navbot_voice_io.protocol import Frame, FrameParser


class BuddyLink:
    def __init__(self, port: str, baud: int, on_frame: Callable[[Frame], None]) -> None:
        self.port = port
        self.baud = baud
        self._on_frame = on_frame
        self._ser = None
        self._parser = FrameParser()
        self._reader: threading.Thread | None = None
        self._running = False
        self._seq = 0
        self._write_lock = threading.Lock()

    def open(self) -> None:
        import serial  # lazy

        # Deassert DTR/RTS before opening so connecting does NOT trigger the
        # CH343 auto-reset (which would reboot the buddy every time the brain
        # reconnects).
        self._ser = serial.Serial()
        self._ser.port = self.port
        self._ser.baudrate = self.baud
        self._ser.timeout = 0.05
        self._ser.dtr = False
        self._ser.rts = False
        self._ser.open()
        self._running = True
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def close(self) -> None:
        self._running = False
        if self._reader is not None:
            self._reader.join(timeout=1.0)
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None

    def is_open(self) -> bool:
        return self._ser is not None and getattr(self._ser, "is_open", False)

    def _read_loop(self) -> None:
        while self._running and self._ser is not None:
            try:
                data = self._ser.read(4096)
            except Exception:
                break  # device went away; node will reconnect
            if data:
                for frame in self._parser.feed(data):
                    try:
                        self._on_frame(frame)
                    except Exception:
                        pass  # never let a callback kill the reader

    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFF
        return self._seq

    def _send(self, msg_type: int, payload: bytes = b"") -> None:
        if self._ser is None:
            return
        frame = protocol.encode_frame(msg_type, self._next_seq(), payload)
        with self._write_lock:
            try:
                self._ser.write(frame)
            except Exception:
                pass

    def _send_json(self, msg_type: int, obj: dict) -> None:
        import json

        self._send(msg_type, json.dumps(obj, separators=(",", ":")).encode("utf-8"))

    # -- typed senders --
    def send_hello(self, fw: str = "pi") -> None:
        self._send_json(protocol.T_HELLO, {"role": "pi", "fw": fw, "proto_ver": protocol.PROTO_VER})

    def send_ping(self) -> None:
        self._send(protocol.T_PING)

    def send_pong(self) -> None:
        self._send(protocol.T_PONG)

    def send_face(self, state: str) -> None:
        self._send_json(protocol.T_FACE, {"state": state})

    def send_tts(self, pcm: bytes) -> None:
        self._send(protocol.T_AUDIO_TTS, pcm)

    def send_tts_end(self) -> None:
        self._send(protocol.T_AUDIO_TTS_END)

    def send_cmd(self, cmd: str, **kwargs) -> None:
        self._send_json(protocol.T_CMD, {"cmd": cmd, **kwargs})
