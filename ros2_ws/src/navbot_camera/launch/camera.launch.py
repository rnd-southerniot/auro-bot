import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    config_file = os.path.join(
        get_package_share_directory("navbot_camera"), "config", "camera.yaml"
    )

    # The camera is the XIAO ESP32-S3 Sense Wi-Fi board (firmware/xiao_esp32s3_sense_cam),
    # which serves JPEG over HTTP. There is no on-Pi camera driver to launch — the
    # frame_grabber is a thin HTTP client. Override the board address without editing
    # config via camera_url:=http://<ip>.
    return LaunchDescription(
        [
            DeclareLaunchArgument("log_level", default_value="info"),
            DeclareLaunchArgument(
                "camera_url",
                default_value="http://192.168.68.107",
                description="XIAO camera base URL (override the board address here)",
            ),
            Node(
                package="navbot_camera",
                executable="frame_grabber",
                name="navbot_camera_frame_grabber",
                output="screen",
                parameters=[
                    config_file,
                    {"camera_url": LaunchConfiguration("camera_url")},
                ],
                arguments=["--ros-args", "--log-level", LaunchConfiguration("log_level")],
            ),
        ]
    )
