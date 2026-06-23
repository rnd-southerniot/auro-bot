"""Standalone buddy link tester — no ROS required.

Opens the ESP32-S3 buddy's CDC serial, speaks the wire protocol, and:
  - prints HELLO / STATUS frames,
  - measures the AUDIO_MIC frame rate + RMS level,
  - echoes mic audio back as AUDIO_TTS (so your voice plays from the buddy
    speaker) unless --no-echo,
  - cycles FACE states so you can confirm the display reacts.

This is the P1 ``buddy-link-test`` and runs on any host the buddy is plugged
into (the robot Pi, or this gateway Pi). Reuses the framing verified
byte-identical to the firmware.

    python3 -m navbot_voice_io.loopback_tool                 # auto-detect port
    python3 -m navbot_voice_io.loopback_tool --port /dev/ttyACM0 --seconds 20
    python3 -m navbot_voice_io.loopback_tool --no-echo       # monitor only
"""
from __future__ import annotations

import argparse
import glob
import math
import os
import struct
import time

try:  # works as a package module (on the robot) or as a loose file (copied to a Mac)
    from navbot_voice_io import protocol
    from navbot_voice_io.protocol import FrameParser
except ImportError:  # pragma: no cover - standalone use
    import protocol  # type: ignore
    from protocol import FrameParser  # type: ignore

_FORBIDDEN = ("Pico", "CP2102")  # never the motion controller / LiDAR


def detect_port() -> str | None:
    for link in sorted(glob.glob("/dev/serial/by-id/*")):
        low = link.lower()
        # CH343 enumerates as WCH VID 1a86 / "USB Single Serial" (not "CH343").
        if (any(k in low for k in ("ch343", "ch34", "wch", "1a86", "single_serial"))
                and not any(x in link for x in _FORBIDDEN)):
            return os.path.realpath(link)
    # fall back to a lone ttyACM that is not a forbidden by-id
    accs = sorted(glob.glob("/dev/ttyACM*"))
    forbidden_real = {
        os.path.realpath(p)
        for p in glob.glob("/dev/serial/by-id/*")
        if any(x in p for x in _FORBIDDEN)
    }
    free = [p for p in accs if os.path.realpath(p) not in forbidden_real]
    return free[0] if len(free) == 1 else None


def rms(pcm: bytes) -> float:
    n = len(pcm) // 2
    if n == 0:
        return 0.0
    samples = struct.unpack(f"<{n}h", pcm[: n * 2])
    return math.sqrt(sum(s * s for s in samples) / n)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=None)
    ap.add_argument("--baud", type=int, default=1000000)
    ap.add_argument("--seconds", type=float, default=15.0)
    ap.add_argument("--no-echo", action="store_true", help="monitor only; do not echo mic->speaker")
    args = ap.parse_args()

    try:
        import serial
    except Exception:
        print("pyserial not installed: pip install pyserial"); return 2

    port = args.port or detect_port()
    if not port:
        print("no buddy serial found (auto). Specify --port; refusing Pico/CP2102."); return 2
    print(f"opening {port} @ {args.baud} (echo={'off' if args.no_echo else 'ON'})")
    ser = serial.Serial(port, args.baud, timeout=0.05)
    time.sleep(0.2)
    ser.reset_input_buffer()

    parser = FrameParser()
    seq = 0

    def send(t, payload=b""):
        nonlocal seq
        ser.write(protocol.encode_frame(t, seq, payload))
        seq = (seq + 1) & 0xFF

    send(protocol.T_HELLO, b'{"role":"host","fw":"loopback","proto_ver":1}')

    faces = ["idle", "listening", "thinking", "speaking", "driving", "idle"]
    t0 = time.time()
    next_ping = t0 + 2.0
    next_face = t0 + 1.0
    fi = 0
    mic_frames = 0
    mic_bytes = 0
    peak_rms = 0.0
    hello_seen = False
    status_seen = 0

    while time.time() - t0 < args.seconds:
        data = ser.read(4096)
        if data:
            for f in parser.feed(data):
                if f.type == protocol.T_AUDIO_MIC:
                    mic_frames += 1
                    mic_bytes += len(f.payload)
                    peak_rms = max(peak_rms, rms(f.payload))
                    if not args.no_echo:
                        send(protocol.T_AUDIO_TTS, f.payload)
                elif f.type == protocol.T_HELLO:
                    hello_seen = True
                    print(f"  HELLO  {f.json()}")
                elif f.type == protocol.T_STATUS:
                    status_seen += 1
                    if status_seen <= 2:
                        print(f"  STATUS {f.json()}")
                elif f.type == protocol.T_EVENT:
                    print(f"  EVENT  {f.json()}")
                elif f.type == protocol.T_PING:
                    send(protocol.T_PONG)
        now = time.time()
        if now >= next_ping:
            send(protocol.T_PING); next_ping = now + 2.0
        if now >= next_face:
            send(protocol.T_FACE, f'{{"state":"{faces[fi % len(faces)]}"}}'.encode())
            fi += 1
            next_face = now + 1.5
    if not args.no_echo:
        send(protocol.T_AUDIO_TTS_END)
    send(protocol.T_FACE, b'{"state":"idle"}')

    dur = time.time() - t0
    rate = mic_frames / dur if dur else 0.0
    ser.close()
    print("\n== buddy-link-test result ==")
    print(f"  hello_seen   = {hello_seen}")
    print(f"  status_frames= {status_seen}")
    print(f"  mic_frames   = {mic_frames}  ({rate:.1f}/s, expect ~50/s for 20 ms frames)")
    print(f"  mic_bytes    = {mic_bytes}")
    print(f"  mic_peak_rms = {peak_rms:.0f}  (speak/clap to push this up)")
    print(f"  crc_errors   = {parser.crc_errors}  resyncs={parser.resyncs}")
    expected_rate = 40 <= rate <= 60
    ok = hello_seen and status_seen >= 1 and mic_frames > 0 and parser.crc_errors == 0 and expected_rate
    print("  VERDICT:", "PASS" if ok else "review (see fields above)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
