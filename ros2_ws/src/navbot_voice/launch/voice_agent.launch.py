import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    config_file = os.path.join(
        get_package_share_directory("navbot_voice"), "config", "voice_agent.yaml"
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument("log_level", default_value="info"),
            Node(
                package="navbot_voice",
                executable="voice_agent",
                name="navbot_voice_agent",
                output="screen",
                parameters=[config_file],
                arguments=["--ros-args", "--log-level", LaunchConfiguration("log_level")],
            ),
        ]
    )
