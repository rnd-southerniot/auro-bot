"""Headless Claude Code brain (P5, subscription auth).

Per utterance, spawns ``claude -p "<transcript>"`` with a single sanctioned tool
— the ``navbotctl`` CLI (Bash) — which talks back to this process's loopback
control server (:func:`navbot_voice.robot_tools.serve_tools`). Claude plans and
acts; its final text is read aloud. Uses the robot's Claude Code subscription
(OAuth, auto-refreshing), so there is no metered API key and no token to expire.

Motion stays gated by the shared :class:`SafetyGate`: drive mode is off by
default and the on-device "stop" word aborts any in-flight drive regardless of
what Claude is doing.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from typing import Callable

from navbot_voice.robot_client import RobotClient
from navbot_voice.robot_tools import RobotTools, serve_tools
from navbot_voice.safety import SafetyGate

CLAUDE_BIN = os.path.expanduser(os.environ.get("NAVBOT_CLAUDE_BIN", "~/.local/bin/claude"))
CONTROL_HOST = "127.0.0.1"
CONTROL_PORT = int(os.environ.get("NAVBOT_CTL_PORT", "8077"))
CLAUDE_TIMEOUT_S = float(os.environ.get("NAVBOT_CLAUDE_TIMEOUT", "90"))
MAX_TURNS = os.environ.get("NAVBOT_CLAUDE_MAX_TURNS", "8")

SYSTEM_PROMPT = (
    "You are the voice and brain of a small two-wheeled differential-drive robot. "
    "The user just spoke to you out loud; their words are your prompt, and your final "
    "reply is read back through a small speaker — so end with exactly ONE short, "
    "friendly spoken sentence, plain text (no markdown, lists, code, or emoji).\n\n"
    "To act on the robot, run the `navbotctl` command with the Bash tool. Commands:\n"
    "  navbotctl drive-mode on        # enable motion (OFF by default; required before driving)\n"
    "  navbotctl drive-mode off       # disable motion\n"
    "  navbotctl drive --linear <m/s> --angular <rad/s> --duration <s>\n"
    "                                 # forward +, back -; turn left/CCW +, right -.\n"
    "                                 # values are hard-clamped (|linear|<=0.12, |angular|<=0.6,\n"
    "                                 # duration<=3) and the robot auto-stops when done. A\n"
    "                                 # cumulative limit (~6 s total) caps motion per request, so\n"
    "                                 # do NOT chain drives for a long ask (e.g. 'drive 40 s'):\n"
    "                                 # make one short move and say you keep moves brief for safety.\n"
    "  navbotctl turn --degrees <d>   # rotate in place (+ = left/CCW); for facing a target.\n"
    "                                 # In-place rotation, exempt from the ~6 s drive limit.\n"
    "  navbotctl look-around [--target \"<thing>\"]\n"
    "                                 # spin a full 360 in place, snapping a photo at each of 8\n"
    "                                 # headings; prints '<deg> -> <JPEG path>' for each. Read every\n"
    "                                 # frame to find the thing. Needs drive mode on.\n"
    "  navbotctl stop                 # stop now and leave drive mode\n"
    "  navbotctl status               # controller / e-stop / odometry / motor voltage / lidar\n"
    "  navbotctl face <state>         # idle|listening|thinking|speaking|driving|halted|low_battery\n"
    "  navbotctl look                 # grab a photo from the robot's camera; prints the saved\n"
    "                                 # JPEG path. Then use the Read tool on that path to SEE it.\n"
    "  navbotctl say \"<sentence>\"      # speak a sentence aloud NOW through the speaker. Use for\n"
    "                                 # mid-task progress/announcements (e.g. after a search,\n"
    "                                 # 'Found it, turning to face it now.'). Your FINAL reply is\n"
    "                                 # already spoken, so don't use say to repeat it.\n\n"
    "Rules:\n"
    "- To see / look / 'what do you see' / describe surroundings: run `navbotctl look`, then Read "
    "the JPEG path it prints, and answer from the image in one spoken sentence.\n"
    "- To SEARCH / find / 'look for' / 'where is' a thing: `navbotctl drive-mode on`, then "
    "`navbotctl look-around --target \"<thing>\"`. Read EVERY printed frame path. If you spot the "
    "target, `navbotctl turn --degrees <heading of that frame>` to face it, then say you found it "
    "and where. If it's in none of the frames, say you looked all around and couldn't find it.\n"
    "- To move: first `navbotctl drive-mode on`, then `navbotctl drive ...`. Move conservatively "
    "(~0.10 m/s, ~0.5 rad/s, 1-2 s).\n"
    "- If the command output says it refused to move, tell the user why in your reply.\n"
    "- If asked to stop, run `navbotctl stop`. The user can also just say 'stop', which hardware-"
    "stops the robot instantly — never argue with a stop.\n"
    "- Use `navbotctl status` for status/battery/e-stop questions.\n"
    "- You can see through the camera (`navbotctl look`) but cannot navigate to named places — say "
    "so honestly in one sentence rather than pretending."
)


class ClaudeBrain:
    def __init__(
        self,
        set_face: Callable[[str], None] | None = None,
        speak: Callable[[str], None] | None = None,
    ) -> None:
        if not (os.path.exists(CLAUDE_BIN) or shutil.which("claude")):
            raise RuntimeError(f"claude binary not found at {CLAUDE_BIN}")
        self.robot = RobotClient()
        self.safety = SafetyGate()
        self.tools = RobotTools(self.robot, self.safety, set_face=set_face, speak=speak)
        self._server = serve_tools(self.tools, CONTROL_HOST, CONTROL_PORT)
        self._workdir = os.path.expanduser("~/.cache/navbot_brain")
        os.makedirs(self._workdir, exist_ok=True)
        self._bin = CLAUDE_BIN if os.path.exists(CLAUDE_BIN) else "claude"

    def run(self, transcript: str) -> str:
        env = dict(os.environ)
        env["NAVBOT_CTL_URL"] = f"http://{CONTROL_HOST}:{CONTROL_PORT}"
        # make sure navbotctl + claude resolve regardless of how the brain was launched
        env["PATH"] = os.path.expanduser("~/.local/bin") + os.pathsep + env.get("PATH", "")
        cmd = [
            self._bin, "-p", transcript,
            "--output-format", "text",
            "--append-system-prompt", SYSTEM_PROMPT,
            "--allowedTools", "Bash(navbotctl:*)", "Read",
            "--max-turns", str(MAX_TURNS),
        ]
        try:
            proc = subprocess.run(
                cmd, cwd=self._workdir, env=env,
                capture_output=True, text=True, timeout=CLAUDE_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return "Sorry, that took too long. I've stopped."
        reply = (proc.stdout or "").strip()
        if not reply:
            err = (proc.stderr or "").strip().splitlines()[-1:] or [""]
            print(f"[claude] empty reply (rc={proc.returncode}): {err[0]}", flush=True)
            return "Okay."
        return reply
