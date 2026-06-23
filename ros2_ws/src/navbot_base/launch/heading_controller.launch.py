from launch import LaunchDescription
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    config_file = PathJoinSubstitution(
        [FindPackageShare("navbot_base"), "config", "heading_controller.yaml"]
    )

    return LaunchDescription(
        [
            Node(
                package="navbot_base",
                executable="heading_controller",
                name="navbot_heading_controller",
                output="screen",
                parameters=[config_file],
            )
        ]
    )
