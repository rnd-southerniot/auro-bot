"""navbot_voice — the on-robot voice brain (P0 skeleton).

P0 scope: stand up the ROS node, connect to the navbot_web control surface, and
report robot status. No audio, no LLM, no motion yet — those land in later
phases (see docs plan). This validates the brain <-> control-surface link in
isolation so the rest of the pipeline builds on a proven foundation.
"""
from __future__ import annotations

import urllib.error

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from navbot_voice.robot_client import RobotClient


class VoiceAgent(Node):
    def __init__(self) -> None:
        super().__init__("navbot_voice_agent")

        self.declare_parameter("robot_api_base", "http://127.0.0.1:8080")
        self.declare_parameter("status_poll_period", 5.0)
        self.declare_parameter("http_timeout", 2.0)

        base = str(self.get_parameter("robot_api_base").value)
        timeout = float(self.get_parameter("http_timeout").value)
        period = float(self.get_parameter("status_poll_period").value)

        self.client = RobotClient(base_url=base, timeout=timeout)
        self.get_logger().info(f"navbot_voice brain (P0 skeleton) — control surface: {base}")
        self._poll()  # one immediate read so a failed link surfaces at startup
        self.create_timer(period, self._poll)

    def _poll(self) -> None:
        try:
            status = self.client.get_status()
            self.get_logger().info(self.client.summarize_status(status))
        except urllib.error.URLError as exc:
            self.get_logger().warn(
                f"control surface unreachable at {self.client.base_url} ({exc}); "
                "is the navbot_web console running? (launch_web_console.sh)"
            )
        except Exception as exc:  # pragma: no cover - defensive
            self.get_logger().warn(f"status read failed: {exc}")


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = VoiceAgent()
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
