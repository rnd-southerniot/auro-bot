import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    config_file = os.path.join(
        get_package_share_directory("navbot_camera"), "config", "camera.yaml"
    )
    use_driver = LaunchConfiguration("use_camera_driver")

    return LaunchDescription(
        [
            # Set use_camera_driver:=false to run only the frame_grabber (e.g. when
            # camera_ros / the CSI module is not present yet).
            DeclareLaunchArgument("use_camera_driver", default_value="true"),
            DeclareLaunchArgument("log_level", default_value="info"),
            Node(
                package="camera_ros",
                executable="camera_node",
                name="camera",
                output="screen",
                parameters=[config_file],
                remappings=[("~/image_raw", "/camera/image_raw"),
                            ("~/camera_info", "/camera/camera_info")],
                condition=IfCondition(use_driver),
            ),
            Node(
                package="navbot_camera",
                executable="frame_grabber",
                name="navbot_camera_frame_grabber",
                output="screen",
                parameters=[config_file],
                arguments=["--ros-args", "--log-level", LaunchConfiguration("log_level")],
            ),
        ]
    )
