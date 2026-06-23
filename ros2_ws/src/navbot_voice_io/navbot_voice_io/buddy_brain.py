"""Buddy brain — wake -> STT -> (P5) Claude tool-use -> drive + TTS reply.

Owns the buddy serial link. On the wake word it collects the AFE-enhanced
``AUDIO_MIC`` stream until a short silence, transcribes it with faster-whisper,
then:

  * P5 (``ANTHROPIC_API_KEY`` set): hands the transcript to :class:`VoiceAgent`,
    which plans with Claude and drives the robot through the navbot_web control
    surface under the :class:`SafetyGate`, then speaks Claude's reply.
  * fallback (no key): echoes the transcript back (the P3 behaviour), so the
    voice loop still works without an LLM.

The on-device "stop" word always wins: it fires a serial event that hits
``/api/stop`` and halts the safety gate immediately, independent of Claude.

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

# The brain (LLM/tools/safety) lives in the sibling navbot_voice package. When
# run from source (python3 -m navbot_voice_io.buddy_brain) that package isn't on
# the path; add it so the fast dev loop keeps working without a colcon install.
try:
    from navbot_voice.agent import VoiceAgent
    from navbot_voice.robot_client import RobotClient
    from navbot_voice.safety import SafetyGate
except ImportError:  # pragma: no cover - dev convenience
    import pathlib
    import sys

    _proj = pathlib.Path(__file__).resolve().parents[2] / "navbot_voice"
    if _proj.exists():
        sys.path.insert(0, str(_proj))
    try:
        from navbot_voice.agent import VoiceAgent
        from navbot_voice.robot_client import RobotClient
        from navbot_voice.safety import SafetyGate
    except ImportError:
        VoiceAgent = None  # type: ignore[assignment,misc]
        RobotClient = None  # type: ignore[assignment,misc]
        SafetyGate = None  # type: ignore[assignment,misc]

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
        self._robot = None
        self._safety = None
        self._agent = None

    def _build_agent(self) -> None:
        """Stand up the P5 LLM brain if possible; otherwise stay in P3 echo mode."""
        if VoiceAgent is None or SafetyGate is None or RobotClient is None:
            print("[brain] navbot_voice not importable — echo mode (P3).", flush=True)
            return
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("[brain] no ANTHROPIC_API_KEY — echo mode (P3); set it for voice control.", flush=True)
            return
        try:
            self._robot = RobotClient()
            self._safety = SafetyGate()
            self._agent = VoiceAgent(self._robot, self._safety, set_face=self.link.send_face)
            print(f"[brain] voice control ON (P5) — model {self._agent.model}.", flush=True)
        except Exception as exc:  # noqa: BLE001
            self._agent = None
            print(f"[brain] LLM brain init failed ({exc}) — echo mode (P3).", flush=True)

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
        self._build_agent()
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
                # On-device stop wins instantly and independently of Claude:
                # halt the safety gate (aborts any in-flight drive) and hit
                # /api/stop. Runs on the reader thread; the drive loop polls the
                # same abort flag and bails.
                if self._safety is not None:
                    self._safety.halt()
                if self._robot is not None:
                    try:
                        self._robot.stop()
                    except Exception:  # noqa: BLE001
                        pass
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
            if self._agent is not None:
                reply = self._reply(text)
            else:
                reply = "You said: " + text   # P3 echo (no LLM)
            print(f"reply: {reply!r}", flush=True)
            self.link.send_face("speaking")
            self._speak(reply)
            self.link.send_face("idle")
        finally:
            self._busy = False

    def _reply(self, text: str) -> str:
        """Run the P5 LLM brain; degrade gracefully so a brain error never bricks voice."""
        try:
            return self._agent.run(text)
        except Exception as exc:  # noqa: BLE001
            print(f"[brain] agent error: {exc}", flush=True)
            return "Sorry, my brain hit a snag, but I can still stop and drive."

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
