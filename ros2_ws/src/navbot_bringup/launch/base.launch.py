import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    description_launch = os.path.join(
        get_package_share_directory("navbot_description"),
        "launch",
        "robot_state_publisher.launch.py",
    )
    base_launch = os.path.join(
        get_package_share_directory("navbot_base"),
        "launch",
        "base_bridge.launch.py",
    )
    serial_port = LaunchConfiguration("serial_port")

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "serial_port",
                default_value="/dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00",
                description="USB serial device for the RP2040 base controller",
            ),
            IncludeLaunchDescription(PythonLaunchDescriptionSource(description_launch)),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(base_launch),
                launch_arguments={"serial_port": serial_port}.items(),
            ),
        ]
    )
