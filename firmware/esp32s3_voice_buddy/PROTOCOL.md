# Pi ↔ Buddy wire protocol (CDC serial over CH343)

The robot's Raspberry Pi and the ESP32-S3 voice buddy talk over the buddy's
USB CDC serial link (CH343 → UART0). One link multiplexes **control** messages
(small JSON) and **audio** (binary PCM) using a single binary frame format.

- **Default baud:** `1000000` (1 Mbps). Raw audio is 256 kbps each direction
  (16 kHz × 16-bit mono); both directions + framing fit comfortably. CH343
  supports up to ~6 Mbps if a future codec/headroom needs it.
- **Audio format:** signed 16-bit little-endian PCM, **16 kHz mono**, **20 ms**
  per frame = 320 samples = **640 bytes**. (ADPCM/Opus can be added later as new
  audio message types without changing the framing.)
- **Endianness:** all multi-byte header fields are little-endian.

## Frame format

```
+------+------+------+------+--------+--------+===========+--------+--------+
| 0xA5 | 0x5A | type | seq  | len_lo | len_hi |  payload  | crc_lo | crc_hi |
+------+------+------+------+--------+--------+===========+--------+--------+
  magic0 magic1  u8     u8     u16 little-endian  len bytes   crc16-ccitt(LE)
```

- `magic` = `0xA5 0x5A` — frame start / resync marker.
- `type`  = message type (below).
- `seq`   = rolling 0–255 counter (per sender); for loss/debug only.
- `len`   = payload length, 0–65535.
- `crc16` = CRC-16/CCITT-FALSE (poly `0x1021`, init `0xFFFF`) over
  `type, seq, len_lo, len_hi, payload` (i.e. everything between magic and crc).

A receiver scans for `magic`, reads the header, waits for `len`+2 more bytes,
verifies the CRC, and on mismatch drops one byte and re-scans (resync).

## Message types

| type   | name           | dir       | payload |
|--------|----------------|-----------|---------|
| `0x01` | HELLO          | both      | JSON `{role, fw, proto_ver}` — handshake on connect |
| `0x02` | PING           | both      | empty — keepalive (expect PONG) |
| `0x03` | PONG           | both      | empty |
| `0x10` | AUDIO_MIC      | buddy→Pi  | 640-byte PCM frame (mic, post-AFE) |
| `0x11` | AUDIO_TTS      | Pi→buddy  | PCM frame to play on the speaker |
| `0x12` | AUDIO_TTS_END  | Pi→buddy  | empty — end of utterance (flush/stop playback) |
| `0x20` | EVENT          | buddy→Pi  | JSON `{"event":"wake"\|"stop"\|"button","detail":...}` |
| `0x30` | FACE           | Pi→buddy  | JSON `{"state":"idle\|listening\|thinking\|speaking\|driving\|halted\|low_battery", ...}` |
| `0x31` | STATUS         | buddy→Pi  | JSON `{"mic_rms":..,"volume":..,"brightness":..,"fw":..}` (~1 Hz) |
| `0x40` | CMD            | Pi→buddy  | JSON `{"cmd":"set_volume\|set_brightness\|mic_mute\|wake_enable", ...}` |

Control payloads are UTF-8 JSON (no embedded newline needed — the framing, not
newlines, delimits messages). Audio payloads are raw bytes.

## Safety-relevant flows

- **Wake:** buddy sends `EVENT {"event":"wake"}` after on-device WakeNet fires;
  the Pi then expects `AUDIO_MIC` frames until VAD end.
- **Stop:** buddy's on-device MultiNet "stop"/"halt" sends `EVENT
  {"event":"stop"}` **immediately and independently of the audio stream**; the
  Pi maps this to `POST /api/stop` (sub-100 ms) and a `FACE {"state":"halted"}`.
- **Barge-in:** while the Pi is streaming `AUDIO_TTS`, the buddy keeps listening
  (AEC); a wake/stop `EVENT` tells the Pi to stop sending TTS and send
  `AUDIO_TTS_END`.

## Versioning

`proto_ver` starts at `1`. Add new `type` codes for new features; never
repurpose an existing code. Both ends log a warning if `proto_ver` differs.
