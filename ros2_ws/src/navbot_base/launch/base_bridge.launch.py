from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    config_file = PathJoinSubstitution(
        [FindPackageShare("navbot_base"), "config", "navbot_base.yaml"]
    )
    serial_port = LaunchConfiguration("serial_port")

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "serial_port",
                default_value="/dev/ttyACM0",
                description="USB serial device for the RP2040 base controller",
            ),
            Node(
                package="navbot_base",
                executable="serial_bridge",
                name="navbot_serial_bridge",
                output="screen",
                parameters=[config_file, {"serial_port": serial_port}],
            )
        ]
    )
