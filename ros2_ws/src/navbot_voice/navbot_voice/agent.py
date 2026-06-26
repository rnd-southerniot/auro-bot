"""Voice agent — the Claude tool-use brain that drives the robot from speech (P5).

Takes a Whisper transcript, lets Claude plan with a small, safety-gated tool set
mapped onto the sanctioned navbot_web control surface, executes the tools, and
returns a short spoken reply. All motion goes through :class:`RobotClient`
(/api/cmd_vel, /api/stop) under the :class:`SafetyGate`; the on-device "stop"
word and the hardware e-stop override everything here.

Model: defaults to Haiku 4.5 for low-latency intent (the user-approved plan's
"fast intent" role); override with ``NAVBOT_LLM_MODEL`` (e.g. ``claude-sonnet-4-6``).
Auth: the Anthropic SDK reads ``ANTHROPIC_API_KEY`` from the environment.
"""
from __future__ import annotations

import base64
import os
import time
from typing import Any, Callable

from navbot_voice.camera_client import CameraClient
from navbot_voice.robot_client import RobotClient
from navbot_voice.safety import SafetyGate

DEFAULT_MODEL = os.environ.get("NAVBOT_LLM_MODEL", "claude-haiku-4-5")
# Vision uses the stronger "reasoning/vision" model from the plan (Sonnet), since
# Haiku handles fast intent but the scene description benefits from Sonnet.
VISION_MODEL = os.environ.get("NAVBOT_VISION_MODEL", "claude-sonnet-4-6")

SYSTEM_PROMPT = (
    "You are Auro, the voice and brain of a small two-wheeled differential-drive robot. "
    "The user may address you as \"Auro\"; answer to that name and refer to yourself as Auro. "
    "A person is talking to you out loud; your spoken reply is read back through a "
    "small speaker, so keep replies to ONE short sentence, friendly and plain — no "
    "markdown, lists, or emoji.\n\n"
    "You can act on the robot with the provided tools. Rules you must follow:\n"
    "- The robot will NOT move until drive mode is on. If the person asks to move and "
    "drive mode is off, call set_drive_mode(enabled=true) first, then drive.\n"
    "- Move conservatively. Forward is positive linear (about 0.10 m/s is normal); "
    "turning left is positive angular (about 0.5 rad/s). Use short durations (1-2 s). "
    "Speeds and durations are hard-clamped, so larger numbers are reduced, not honored. "
    "There is also a cumulative motion limit per request (~6 s total): do NOT chain many "
    "drives to satisfy a long ask like 'drive for 40 seconds' — do one short, safe move and "
    "tell the person you keep moves brief for safety.\n"
    "- The person can say 'stop' at any time; that is handled instantly in hardware, "
    "so never argue with a stop. Use the stop tool yourself if asked to stop.\n"
    "- For 'what's your status' or battery/e-stop questions, call get_status.\n"
    "- To see / look around / answer 'what do you see', call look with a short query; it returns "
    "a description from the robot's camera that you relay in one spoken sentence.\n"
    "- If you can't do something (e.g. navigate to named places), say so honestly in one sentence "
    "rather than pretending."
)


class VoiceAgent:
    def __init__(
        self,
        robot: RobotClient,
        safety: SafetyGate,
        set_face: Callable[[str], None] | None = None,
        model: str | None = None,
        max_turns: int = 6,
    ) -> None:
        import anthropic  # lazy: raises a clear error if the SDK isn't installed

        self.robot = robot
        self.safety = safety
        self._face = set_face or (lambda _state: None)
        self.model = model or DEFAULT_MODEL
        self.max_turns = max_turns
        self.client = anthropic.Anthropic()  # ANTHROPIC_API_KEY from env
        self.camera = CameraClient()
        self.tools = self._tool_schema()

    # -- public entry: transcript -> spoken reply --
    def run(self, transcript: str) -> str:
        messages: list[dict[str, Any]] = [{"role": "user", "content": transcript}]
        reply = ""
        for _ in range(self.max_turns):
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=512,
                system=SYSTEM_PROMPT,
                tools=self.tools,
                messages=messages,
            )
            text = " ".join(b.text for b in resp.content if b.type == "text").strip()
            if text:
                reply = text
            if resp.stop_reason != "tool_use":
                break
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if block.type == "tool_use":
                    out = self._dispatch(block.name, block.input or {})
                    results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": out}
                    )
            messages.append({"role": "user", "content": results})
        return reply or "Okay."

    # -- tool definitions --
    @staticmethod
    def _tool_schema() -> list[dict[str, Any]]:
        return [
            {
                "name": "set_drive_mode",
                "description": "Enable or disable motion. Drive mode is OFF by default; "
                "the robot cannot move until it is enabled. Turn it off when the person "
                "is done driving.",
                "input_schema": {
                    "type": "object",
                    "properties": {"enabled": {"type": "boolean"}},
                    "required": ["enabled"],
                },
            },
            {
                "name": "drive",
                "description": "Drive the base for a short duration. linear m/s (forward +, "
                "back -), angular rad/s (left/CCW +, right -), duration seconds. Values are "
                "hard-clamped (|linear|<=0.12, |angular|<=0.6, duration<=3). Requires drive "
                "mode on. The robot auto-stops when the duration ends.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "linear": {"type": "number"},
                        "angular": {"type": "number"},
                        "duration": {"type": "number"},
                    },
                    "required": ["linear", "angular", "duration"],
                },
            },
            {
                "name": "stop",
                "description": "Stop the robot immediately and leave drive mode.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_status",
                "description": "Read the robot's current state (controller, e-stop, odometry, "
                "motor voltage, lidar).",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "set_face",
                "description": "Set the buddy's animated face: idle, listening, thinking, "
                "speaking, driving, halted, low_battery.",
                "input_schema": {
                    "type": "object",
                    "properties": {"state": {"type": "string"}},
                    "required": ["state"],
                },
            },
            {
                "name": "look",
                "description": "Look through the robot's camera and describe what it sees. "
                "Pass a short query for what to focus on (e.g. 'what is in front of me?', "
                "'is there a person?'); returns a brief description of the live scene.",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
            },
        ]

    # -- tool execution --
    def _dispatch(self, name: str, args: dict[str, Any]) -> str:
        try:
            if name == "set_drive_mode":
                on = bool(args.get("enabled"))
                self.safety.set_drive_mode(on)
                return "drive mode " + ("enabled" if on else "disabled")
            if name == "drive":
                return self._drive(
                    args.get("linear", 0.0), args.get("angular", 0.0), args.get("duration", 0.0)
                )
            if name == "stop":
                self._face("halted")
                try:
                    self.robot.stop()
                except Exception as exc:  # noqa: BLE001
                    return f"stop request failed: {exc}"
                self.safety.halt()
                return "stopped"
            if name == "get_status":
                status = self.robot.get_status()
                return self.robot.summarize_status(status)
            if name == "set_face":
                self._face(str(args.get("state", "idle")))
                return "ok"
            if name == "look":
                return self._look(str(args.get("query", "") or "Describe what you see."))
        except Exception as exc:  # noqa: BLE001
            return f"error: {exc}"
        return f"unknown tool: {name}"

    def _look(self, query: str) -> str:
        self._face("thinking")
        try:
            jpeg = self.camera.snapshot_bytes()
        except Exception as exc:  # noqa: BLE001
            self._face("idle")
            return f"camera unavailable: {exc}"
        b64 = base64.b64encode(jpeg).decode("ascii")
        try:
            resp = self.client.messages.create(
                model=VISION_MODEL,
                max_tokens=256,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {
                            "type": "base64", "media_type": "image/jpeg", "data": b64}},
                        {"type": "text", "text":
                            f"This is the live view from a small robot's camera. {query} "
                            "Answer in one or two short, plain sentences."},
                    ],
                }],
            )
            text = " ".join(b.text for b in resp.content if b.type == "text").strip()
        except Exception as exc:  # noqa: BLE001
            text = f"could not analyze the image: {exc}"
        finally:
            self._face("idle")
        return text or "I couldn't make out the scene."

    def _drive(self, linear: Any, angular: Any, duration: Any) -> str:
        try:
            status = self.robot.get_status()
        except Exception:  # noqa: BLE001
            status = {}
        ok, reason = self.safety.can_move(status)
        if not ok:
            return f"refused to move: {reason}"

        lin, ang, dur = self.safety.clamp(linear, angular, duration)
        dur, budget_reason = self.safety.reserve_motion(dur)
        if dur <= 0.0:
            return f"refused to move: {budget_reason}"
        self.safety.begin_move()
        self._face("driving")
        aborted = False
        deadline = time.time() + dur
        try:
            while time.time() < deadline:
                if self.safety.aborted:
                    aborted = True
                    break
                try:
                    self.robot.cmd_vel(lin, ang)  # re-posted ~5 Hz to hold the web 0.35 s watchdog
                except Exception as exc:  # noqa: BLE001
                    self._face("idle")
                    return f"drive command failed: {exc}"
                time.sleep(0.2)
        finally:
            try:
                self.robot.stop()
            except Exception:  # noqa: BLE001
                pass
        self._face("idle")
        if aborted:
            return "stopped early"
        return f"moved (linear {lin:.2f}, angular {ang:.2f}) for {dur:.1f} s"
