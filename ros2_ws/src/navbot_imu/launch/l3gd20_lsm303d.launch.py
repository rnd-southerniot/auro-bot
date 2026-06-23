from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    config_file = PathJoinSubstitution([FindPackageShare("navbot_imu"), "config", "l3gd20_lsm303d.yaml"])

    return LaunchDescription(
        [
            DeclareLaunchArgument("log_level", default_value="info"),
            Node(
                package="navbot_imu",
                executable="l3gd20_lsm303d_reader",
                name="navbot_l3gd20_lsm303d_reader",
                output="screen",
                parameters=[config_file],
                arguments=["--ros-args", "--log-level", LaunchConfiguration("log_level")],
            ),
        ]
    )
