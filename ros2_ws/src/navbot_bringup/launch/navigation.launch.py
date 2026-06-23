import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource


def generate_launch_description():
    base_lidar_launch = os.path.join(
        get_package_share_directory("navbot_bringup"),
        "launch",
        "base_lidar.launch.py",
    )
    nav_launch = os.path.join(
        get_package_share_directory("navbot_navigation"),
        "launch",
        "nav2.launch.py",
    )

    return LaunchDescription(
        [
            IncludeLaunchDescription(PythonLaunchDescriptionSource(base_lidar_launch)),
            IncludeLaunchDescription(PythonLaunchDescriptionSource(nav_launch)),
        ]
    )
