"""navbot_voice_io — Pi-side ROS bridge to the ESP32-S3 buddy.

Opens the buddy CDC serial link and translates the wire protocol to/from ROS:
  publishes  /buddy/wake (Empty), /buddy/stop (Empty), /buddy/event (String),
             /buddy/status (String)
  subscribes /buddy/face (String)  -> FACE frame to the buddy

Audio: mic frames (T_AUDIO_MIC) arrive from the buddy and TTS frames go back.
In ``loopback`` mode (the P1 /navbot:buddy-link-test) mic frames are echoed
straight back as TTS so a spoken phrase comes out the buddy speaker — proving
the full audio path over serial. The brain (navbot_voice, P3) will instead
consume mic frames for STT and push Piper TTS frames; that hook is
``self.on_mic_pcm``.

Reconnects automatically if the board is unplugged/re-enumerates. Runs fine
(idle, warning) when no board is present.
"""
from __future__ import annotations

import glob
import json
import os

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Empty, String

from navbot_voice_io import protocol
from navbot_voice_io.buddy_link import BuddyLink
from navbot_voice_io.protocol import Frame


class VoiceIoNode(Node):
    def __init__(self) -> None:
        super().__init__("navbot_voice_io")

        # "auto" -> resolve the CH343 buddy by /dev/serial/by-id; an explicit
        # path is honored but never a known non-buddy device (Pico/CP2102).
        self.declare_parameter("buddy_serial", "auto")
        self.declare_parameter("baud", 1000000)
        self.declare_parameter("loopback", False)
        self.declare_parameter("ping_period", 2.0)

        self.port = str(self.get_parameter("buddy_serial").value)
        self.baud = int(self.get_parameter("baud").value)
        self.loopback = bool(self.get_parameter("loopback").value)

        self.pub_wake = self.create_publisher(Empty, "/buddy/wake", 10)
        self.pub_stop = self.create_publisher(Empty, "/buddy/stop", 10)
        self.pub_event = self.create_publisher(String, "/buddy/event", 10)
        self.pub_status = self.create_publisher(String, "/buddy/status", 10)
        self.create_subscription(String, "/buddy/face", self._on_face, 10)

        # Hook for the brain (P3): callable(pcm_bytes) -> None. None in P1.
        self.on_mic_pcm = None

        self.link: BuddyLink | None = None
        self._mic_frames = 0
        self._connect()
        self.create_timer(2.0, self._ensure_connected)
        self.create_timer(float(self.get_parameter("ping_period").value), self._ping)

        mode = "LOOPBACK (echo mic->speaker)" if self.loopback else "bridge"
        self.get_logger().info(f"navbot_voice_io {mode} on {self.port} @ {self.baud}")

    # -- connection management --
    _FORBIDDEN = ("Pico", "CP2102")  # RP2040 motion controller / LiDAR adapter

    def _resolve_port(self) -> str | None:
        """Resolve the buddy's serial path, never a known non-buddy device."""
        byids = sorted(glob.glob("/dev/serial/by-id/*"))
        if self.port not in ("", "auto"):
            # explicit path: refuse if it resolves to a forbidden device
            real = os.path.realpath(self.port)
            for link in byids:
                if os.path.realpath(link) == real and any(x in link for x in self._FORBIDDEN):
                    self.get_logger().error(
                        f"refusing {self.port}: resolves to {os.path.basename(link)} "
                        "(motion controller / LiDAR), not the buddy"
                    )
                    return None
            return self.port if os.path.exists(self.port) else None
        # auto: pick the buddy's WCH/CH343 by-id (VID 1a86 / "USB Single Serial")
        # that is not a forbidden device
        for link in byids:
            low = link.lower()
            if any(k in low for k in ("ch343", "ch34", "wch", "1a86", "single_serial")) and not any(
                x in link for x in self._FORBIDDEN
            ):
                return link
        return None

    def _connect(self) -> None:
        port = self._resolve_port()
        if port is None:
            self.link = None
            self.get_logger().warn(
                f"no buddy (CH343) serial found (param='{self.port}'); will retry"
            )
            return
        try:
            link = BuddyLink(port, self.baud, self._on_frame)
            link.open()
            self.link = link
            link.send_hello()
            self.get_logger().info(f"buddy link open on {port}")
        except Exception as exc:
            self.link = None
            self.get_logger().warn(f"buddy not available on {port} ({exc}); will retry")

    def _ensure_connected(self) -> None:
        if self.link is None or not self.link.is_open():
            if self.link is not None:
                self.link.close()
                self.link = None
            self._connect()

    def _ping(self) -> None:
        if self.link is not None and self.link.is_open():
            self.link.send_ping()

    # -- inbound frames from the buddy --
    def _on_frame(self, frame: Frame) -> None:
        t = frame.type
        if t == protocol.T_AUDIO_MIC:
            self._mic_frames += 1
            if self.loopback and self.link is not None:
                self.link.send_tts(frame.payload)  # echo straight back
            elif self.on_mic_pcm is not None:
                self.on_mic_pcm(frame.payload)
            return
        if t == protocol.T_EVENT:
            obj = self._safe_json(frame)
            event = obj.get("event", "")
            self.pub_event.publish(String(data=json.dumps(obj)))
            if event == "wake":
                self.pub_wake.publish(Empty())
            elif event == "stop":
                self.pub_stop.publish(Empty())
                self.get_logger().warn("buddy STOP event")
            return
        if t == protocol.T_STATUS:
            self.pub_status.publish(String(data=json.dumps(self._safe_json(frame))))
            return
        if t == protocol.T_HELLO:
            self.get_logger().info(f"buddy hello: {self._safe_json(frame)}")
            return
        if t == protocol.T_PING and self.link is not None:
            self.link.send_pong()
            return

    @staticmethod
    def _safe_json(frame: Frame) -> dict:
        try:
            return frame.json()
        except Exception:
            return {}

    # -- outbound --
    def _on_face(self, msg: String) -> None:
        if self.link is not None and self.link.is_open():
            self.link.send_face(msg.data.strip())

    def destroy_node(self) -> None:  # noqa: D102
        if self.link is not None:
            self.link.close()
        super().destroy_node()


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = VoiceIoNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
