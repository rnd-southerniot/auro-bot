"""Remote-mic TCP listener — a second audio source for the buddy brain.

A battery-powered push-to-talk device (the ``voicelog`` board, ``voicelog-fw``)
streams 16 kHz / 16-bit mono PCM here over a tiny framed TCP protocol. Per
push-to-talk session it sends:

    START <device_id>  ->  N x AUDIO <pcm chunk>  ->  END

On END we hand the concatenated PCM to a callback, which submits it to the SAME
STT -> brain -> TTS pipeline the on-buddy mic uses (the reply still plays from the
buddy speaker). The audio format matches the buddy exactly, so no transcoding.

Wire format (length-prefixed, big-endian):
    1 byte  type    (0x01 START, 0x02 AUDIO, 0x03 END)
    4 bytes length  (uint32, payload byte count)
    N bytes payload (START: device-id utf-8; AUDIO: raw PCM; END: empty)

Stdlib only; LAN/robot-AP, no auth (trusted network). Push-to-talk gives explicit
endpoints, so there is no silence timer here — END closes the utterance.
"""
from __future__ import annotations

import socket
import struct
import threading
from typing import Callable

T_START = 0x01
T_AUDIO = 0x02
T_END = 0x03

_HDR = struct.Struct(">BI")            # type (u8) + length (u32 BE)
MAX_PAYLOAD = 1 << 20                  # 1 MiB per-frame guard
MAX_UTTERANCE_BYTES = 16000 * 2 * 30   # 30 s @ 16 kHz/16-bit — drop runaway sessions


class RemoteMic:
    """TCP listener that turns a remote PTT device's PCM stream into utterances."""

    def __init__(
        self,
        port: int,
        on_utterance: Callable[[bytes, str], None],
        host: str = "0.0.0.0",
    ) -> None:
        self.host = host
        self.port = port
        self._on_utterance = on_utterance
        self._sock: socket.socket | None = None
        self._running = False

    def start(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(2)
        self._running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()
        print(f"[remote-mic] listening on {self.host}:{self.port}", flush=True)

    def close(self) -> None:
        self._running = False
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    # -- internals --
    def _accept_loop(self) -> None:
        while self._running and self._sock is not None:
            try:
                conn, addr = self._sock.accept()
            except OSError:
                break  # socket closed / shutting down
            threading.Thread(target=self._serve, args=(conn, addr), daemon=True).start()

    @staticmethod
    def _recvn(conn: socket.socket, n: int) -> bytes | None:
        """Read exactly ``n`` bytes, or None on EOF/short read."""
        buf = bytearray()
        while len(buf) < n:
            chunk = conn.recv(n - len(buf))
            if not chunk:
                return None
            buf += chunk
        return bytes(buf)

    def _serve(self, conn: socket.socket, addr) -> None:
        device = ""
        pcm = bytearray()
        active = False
        try:
            conn.settimeout(30.0)
            while self._running:
                hdr = self._recvn(conn, _HDR.size)
                if hdr is None:
                    break
                mtype, length = _HDR.unpack(hdr)
                if length > MAX_PAYLOAD:
                    print(f"[remote-mic] oversized frame ({length}B) from {addr[0]}; closing", flush=True)
                    break
                payload = self._recvn(conn, length) if length else b""
                if length and payload is None:
                    break
                if mtype == T_START:
                    device = payload.decode("utf-8", "replace").strip()
                    pcm = bytearray()
                    active = True
                    print(f"[remote-mic] START dev={device or '?'} from {addr[0]}", flush=True)
                elif mtype == T_AUDIO:
                    if active:
                        pcm += payload
                        if len(pcm) > MAX_UTTERANCE_BYTES:
                            print("[remote-mic] utterance over 30 s cap; truncating", flush=True)
                            active = False
                elif mtype == T_END:
                    if active and pcm:
                        print(f"[remote-mic] END dev={device or '?'} {len(pcm)}B", flush=True)
                        try:
                            self._on_utterance(bytes(pcm), device)
                        except Exception as exc:  # noqa: BLE001 — never kill the listener
                            print(f"[remote-mic] on_utterance error: {exc}", flush=True)
                    active = False
                    pcm = bytearray()
                # unknown frame types are ignored (forward-compat)
        except OSError:
            pass  # connection reset / timeout — drop this session, keep listening
        finally:
            try:
                conn.close()
            except OSError:
                pass
