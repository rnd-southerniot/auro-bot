"""Pi <-> ESP32-S3 buddy wire protocol — framing + parsing.

Pure-Python, no ROS/serial deps, so it is unit-testable on its own. Implements
the frame format in ``firmware/esp32s3_voice_buddy/PROTOCOL.md``:

    0xA5 0x5A | type | seq | len_lo | len_hi | payload | crc_lo | crc_hi

CRC-16/CCITT-FALSE over ``type..payload``. Run ``python3 -m
navbot_voice_io.protocol`` for a self-test.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

MAGIC0 = 0xA5
MAGIC1 = 0x5A

# message types
T_HELLO = 0x01
T_PING = 0x02
T_PONG = 0x03
T_AUDIO_MIC = 0x10
T_AUDIO_TTS = 0x11
T_AUDIO_TTS_END = 0x12
T_EVENT = 0x20
T_FACE = 0x30
T_STATUS = 0x31
T_CMD = 0x40

PROTO_VER = 1
MAX_PAYLOAD = 0xFFFF


def crc16(data: bytes) -> int:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF)."""
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
    return crc


def encode_frame(msg_type: int, seq: int, payload: bytes = b"") -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise ValueError(f"payload too large: {len(payload)} > {MAX_PAYLOAD}")
    n = len(payload)
    header = bytes([msg_type & 0xFF, seq & 0xFF, n & 0xFF, (n >> 8) & 0xFF]) + payload
    crc = crc16(header)
    return bytes([MAGIC0, MAGIC1]) + header + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def encode_json(msg_type: int, seq: int, obj: dict) -> bytes:
    return encode_frame(msg_type, seq, json.dumps(obj, separators=(",", ":")).encode("utf-8"))


@dataclass
class Frame:
    type: int
    seq: int
    payload: bytes

    def json(self) -> dict:
        return json.loads(self.payload.decode("utf-8")) if self.payload else {}


class FrameParser:
    """Streaming parser: ``feed(bytes)`` returns a list of complete Frames.

    Tolerates partial frames across feeds, resynchronises on a bad CRC or lost
    framing by dropping one byte and rescanning, and bounds buffer growth.
    """

    def __init__(self, max_buffer: int = 1 << 16) -> None:
        self._buf = bytearray()
        self._max_buffer = max_buffer
        self.crc_errors = 0
        self.resyncs = 0

    def feed(self, data: bytes) -> list[Frame]:
        self._buf.extend(data)
        if len(self._buf) > self._max_buffer:
            # runaway with no valid framing — keep the tail
            del self._buf[: len(self._buf) - self._max_buffer]
        out: list[Frame] = []
        while True:
            frame = self._try_one(out)
            if not frame:
                break
        return out

    def _try_one(self, out: list[Frame]) -> bool:
        buf = self._buf
        # find magic
        i = buf.find(bytes([MAGIC0, MAGIC1]))
        if i == -1:
            # keep only a possible trailing magic0
            if buf and buf[-1] == MAGIC0:
                del buf[:-1]
            else:
                buf.clear()
            return False
        if i > 0:
            del buf[:i]
            self.resyncs += 1
        if len(buf) < 6:
            return False  # need header
        n = buf[4] | (buf[5] << 8)
        total = 2 + 4 + n + 2
        if len(buf) < total:
            return False  # wait for the rest
        header = bytes(buf[2 : 6 + n])
        crc_rx = buf[6 + n] | (buf[7 + n] << 8)
        if crc16(header) != crc_rx:
            self.crc_errors += 1
            del buf[:1]  # drop one byte, rescan
            return True
        out.append(Frame(type=buf[2], seq=buf[3], payload=bytes(buf[6 : 6 + n])))
        del buf[:total]
        return True


def _selftest() -> int:
    p = FrameParser()
    # control + audio round-trip, streamed in odd chunks, with junk + a corrupted frame
    msgs = [
        encode_json(T_HELLO, 0, {"role": "pi", "fw": "test", "proto_ver": PROTO_VER}),
        encode_frame(T_AUDIO_MIC, 1, bytes(range(256)) * 2 + bytes(128)),  # 640 bytes
        encode_json(T_EVENT, 2, {"event": "stop"}),
    ]
    stream = b"\x00\x11garbage" + msgs[0] + msgs[1][:5] + msgs[1][5:] + b"\xa5" + msgs[2]
    bad = bytearray(encode_json(T_FACE, 3, {"state": "halted"}))
    bad[7] ^= 0xFF  # corrupt a payload byte -> CRC fail -> must resync, not crash
    stream += bytes(bad) + encode_json(T_PING, 4, {})
    frames: list[Frame] = []
    for k in range(0, len(stream), 7):  # feed in 7-byte chunks
        frames += p.feed(stream[k : k + 7])
    types = [f.type for f in frames]
    ok = True
    expect = [T_HELLO, T_AUDIO_MIC, T_EVENT, T_PING]
    if types != expect:
        print(f"FAIL: types {types} != {expect}"); ok = False
    if frames and frames[2].json().get("event") != "stop":
        print("FAIL: event payload"); ok = False
    if frames[1].payload != bytes(range(256)) * 2 + bytes(128):
        print("FAIL: audio payload roundtrip"); ok = False
    if p.crc_errors < 1:
        print("FAIL: corrupted frame should have raised a crc error"); ok = False
    print(f"frames={types} crc_errors={p.crc_errors} resyncs={p.resyncs}")
    print("SELFTEST OK" if ok else "SELFTEST FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_selftest())
