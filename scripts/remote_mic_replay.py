#!/usr/bin/env python3
"""Replay a WAV to the brain's remote-mic TCP listener — dev/test for the 2nd mic.

Lets you exercise the push-to-talk path end-to-end WITHOUT the voicelog firmware:
streams a 16 kHz / 16-bit mono WAV as the same START/AUDIO/END frames the voicelog
will send, so the brain transcribes it and replies out the buddy speaker.

    python3 scripts/remote_mic_replay.py <host> <clip.wav> [--port 8079] [--device test]

Frame wire format mirrors navbot_voice_io/remote_mic.py:
    1 byte type (0x01 START | 0x02 AUDIO | 0x03 END) + 4-byte BE length + payload.
Stdlib only.
"""
from __future__ import annotations

import argparse
import socket
import struct
import sys
import time
import wave

T_START, T_AUDIO, T_END = 0x01, 0x02, 0x03
HDR = struct.Struct(">BI")
FRAME_BYTES = 640  # 320 samples @ 16 kHz = 20 ms, matches the buddy framing


def _send(sock: socket.socket, mtype: int, payload: bytes = b"") -> None:
    sock.sendall(HDR.pack(mtype, len(payload)) + payload)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("host")
    ap.add_argument("wav")
    ap.add_argument("--port", type=int, default=8079)
    ap.add_argument("--device", default="replay")
    args = ap.parse_args(argv)

    with wave.open(args.wav, "rb") as w:
        if w.getframerate() != 16000 or w.getsampwidth() != 2 or w.getnchannels() != 1:
            print(f"warn: expected 16 kHz/16-bit/mono, got "
                  f"{w.getframerate()} Hz/{w.getsampwidth()*8}-bit/{w.getnchannels()}ch", file=sys.stderr)
        pcm = w.readframes(w.getnframes())

    with socket.create_connection((args.host, args.port), timeout=10) as s:
        _send(s, T_START, args.device.encode("utf-8"))
        for i in range(0, len(pcm), FRAME_BYTES):
            _send(s, T_AUDIO, pcm[i:i + FRAME_BYTES])
            time.sleep(0.018)  # ~real-time pacing
        _send(s, T_END)
    print(f"sent {len(pcm)} bytes ({len(pcm)/32000:.1f}s) to {args.host}:{args.port} as dev={args.device}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
