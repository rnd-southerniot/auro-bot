import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    config_file = os.path.join(
        get_package_share_directory("navbot_voice_io"), "config", "voice_io.yaml"
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument("loopback", default_value="false"),
            DeclareLaunchArgument("log_level", default_value="info"),
            Node(
                package="navbot_voice_io",
                executable="voice_io_node",
                name="navbot_voice_io",
                output="screen",
                parameters=[config_file, {"loopback": LaunchConfiguration("loopback")}],
                arguments=["--ros-args", "--log-level", LaunchConfiguration("log_level")],
            ),
        ]
    )
