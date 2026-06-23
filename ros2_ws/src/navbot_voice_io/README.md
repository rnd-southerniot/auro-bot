# navbot_voice_io

Pi-side serial bridge to the **ESP32-S3 voice buddy**. Implements the Pi end of
the wire protocol in
[`firmware/esp32s3_voice_buddy/PROTOCOL.md`](../../../firmware/esp32s3_voice_buddy/PROTOCOL.md):
framed control + audio over the buddy's CDC serial (CH343) link.

- `protocol.py` — frame encode/parse + CRC (pure Python; `python3 -m
  navbot_voice_io.protocol` self-tests the framing).
- `buddy_link.py` — pyserial transport + reader thread.
- `voice_io_node.py` — ROS bridge: publishes `/buddy/wake`, `/buddy/stop`,
  `/buddy/event`, `/buddy/status`; subscribes `/buddy/face`. Auto-reconnects.

## P1 gate — `buddy-link-test`

With a flashed buddy plugged into the Pi:

```bash
ros2 launch navbot_voice_io voice_io.launch.py loopback:=true
# speak at the buddy -> the phrase echoes from the buddy speaker (mic->Pi->speaker
# over serial). Publish a face cue:
ros2 topic pub --once /buddy/face std_msgs/String "{data: listening}"
```

Loopback proves the full audio + control path before STT/TTS (P3) exist. The
brain (`navbot_voice`) later sets `node.on_mic_pcm` to consume mic audio for
Whisper and pushes Piper TTS via `link.send_tts(...)`.
