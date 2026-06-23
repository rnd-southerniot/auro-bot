from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    config_file = PathJoinSubstitution([FindPackageShare("navbot_web"), "config", "web_console.yaml"])

    host = LaunchConfiguration("host")
    port = LaunchConfiguration("port")
    capture_root = LaunchConfiguration("capture_root")

    return LaunchDescription(
        [
            DeclareLaunchArgument("host", default_value="0.0.0.0"),
            DeclareLaunchArgument("port", default_value="8080"),
            DeclareLaunchArgument("capture_root", default_value="/tmp/navbot_captures"),
            Node(
                package="navbot_web",
                executable="web_console",
                name="navbot_web_console",
                output="screen",
                parameters=[config_file, {"host": host, "port": port, "capture_root": capture_root}],
            ),
        ]
    )
