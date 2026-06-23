from launch import LaunchDescription
from launch.actions import ExecuteProcess, LogInfo


def generate_launch_description():
    return LaunchDescription(
        [
            LogInfo(msg="navbot_teleop: requires teleop_twist_keyboard on the current ROS environment"),
            ExecuteProcess(
                cmd=[
                    "ros2",
                    "run",
                    "teleop_twist_keyboard",
                    "teleop_twist_keyboard",
                    "--ros-args",
                    "--remap",
                    "cmd_vel:=/cmd_vel",
                ],
                output="screen",
            ),
        ]
    )
