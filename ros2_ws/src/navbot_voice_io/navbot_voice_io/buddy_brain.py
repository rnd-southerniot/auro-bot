"""P3 buddy brain — speech echo loop (no LLM yet).

Owns the buddy serial link. On the wake word it collects the AFE-enhanced
``AUDIO_MIC`` stream until a short silence, transcribes it with faster-whisper,
and (for P3) echoes it back through Piper TTS to the buddy speaker — driving the
face listening -> thinking -> speaking -> idle. The LLM brain replaces the echo
in P5.

Run on the robot (buddy on ttyACM1):
    python3 -m navbot_voice_io.buddy_brain
"""
from __future__ import annotations

import os
import subprocess
import threading
import time

from navbot_voice_io import protocol
from navbot_voice_io.buddy_link import BuddyLink
from navbot_voice_io.loopback_tool import detect_port

WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base.en")
PIPER_BIN = os.path.expanduser(os.environ.get("PIPER_BIN", "~/piper/piper/piper"))
PIPER_VOICE = os.path.expanduser(os.environ.get("PIPER_VOICE", "~/piper/en_US-amy-low.onnx"))

SAMPLE_RATE = 16000
UTTERANCE_SILENCE_S = 0.6   # end-of-utterance: no mic frames for this long
MIN_UTTERANCE_S = 0.3       # ignore blips shorter than this
TTS_FRAME_BYTES = 640       # 320 samples @ 16 kHz = 20 ms


class BuddyBrain:
    def __init__(self, port: str) -> None:
        self.link = BuddyLink(port, 1000000, self._on_frame)
        self._whisper = None
        self._np = None
        self._lock = threading.Lock()
        self._buf = bytearray()
        self._collecting = False
        self._last_audio = 0.0
        self._busy = False

    def start(self) -> None:
        import numpy as np
        from faster_whisper import WhisperModel

        self._np = np
        print(f"loading faster-whisper '{WHISPER_MODEL}' (first run downloads the model)...", flush=True)
        self._whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
        print("whisper ready.", flush=True)

        self.link.open()
        self.link.send_hello("brain")
        self.link.send_face("idle")
        threading.Thread(target=self._utterance_watch, daemon=True).start()
        print("buddy brain running — say 'Jarvis' then your phrase.", flush=True)

    # -- link callbacks (BuddyLink reader thread) --
    def _on_frame(self, f) -> None:
        if f.type == protocol.T_EVENT:
            ev = f.json().get("event")
            if ev == "wake" and not self._busy:
                with self._lock:
                    self._buf = bytearray()
                    self._collecting = True
                    self._last_audio = time.time()
                print("[wake]", flush=True)
            elif ev == "stop":
                with self._lock:
                    self._collecting = False
                self.link.send_face("halted")
                print("[STOP]", flush=True)
        elif f.type == protocol.T_AUDIO_MIC and self._collecting:
            with self._lock:
                self._buf += f.payload
                self._last_audio = time.time()

    # -- end-of-utterance detector + processing (own thread) --
    def _utterance_watch(self) -> None:
        while True:
            time.sleep(0.1)
            audio = None
            with self._lock:
                if self._collecting and self._buf and (time.time() - self._last_audio) > UTTERANCE_SILENCE_S:
                    audio = bytes(self._buf)
                    self._buf = bytearray()
                    self._collecting = False
            if audio is not None and len(audio) >= int(SAMPLE_RATE * 2 * MIN_UTTERANCE_S):
                self._process(audio)
            elif audio is not None:
                self.link.send_face("idle")  # too short

    def _process(self, pcm: bytes) -> None:
        self._busy = True
        try:
            self.link.send_face("thinking")
            text = self._stt(pcm)
            print(f"heard: {text!r}", flush=True)
            if not text.strip():
                self.link.send_face("idle")
                return
            self.link.send_face("speaking")
            self._speak("You said: " + text)   # P3 echo; LLM reply lands in P5
            self.link.send_face("idle")
        finally:
            self._busy = False

    def _stt(self, pcm: bytes) -> str:
        audio = self._np.frombuffer(pcm, dtype=self._np.int16).astype(self._np.float32) / 32768.0
        segments, _ = self._whisper.transcribe(audio, language="en", beam_size=1)
        return " ".join(s.text for s in segments).strip()

    def _speak(self, text: str) -> None:
        proc = subprocess.run(
            [PIPER_BIN, "-m", PIPER_VOICE, "--output-raw"],
            input=text.encode("utf-8"), capture_output=True,
        )
        pcm = proc.stdout
        for i in range(0, len(pcm), TTS_FRAME_BYTES):
            self.link.send_tts(pcm[i:i + TTS_FRAME_BYTES])
            time.sleep(0.018)   # pace ~ real-time so the buddy's 16 KB buffer doesn't overflow
        self.link.send_tts_end()


def main() -> int:
    port = detect_port()
    if not port:
        print("no buddy (CH343) serial found")
        return 2
    brain = BuddyBrain(port)
    brain.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
