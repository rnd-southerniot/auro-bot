import os

from ament_index_python.packages import PackageNotFoundError, get_package_share_directory
from launch import LaunchDescription
from launch.actions import LogInfo, OpaqueFunction
from launch_ros.actions import Node


def _launch_setup(_context):
    config = os.path.join(
        get_package_share_directory("navbot_lidar"),
        "config",
        "scan_range_filter.yaml",
    )

    try:
        get_package_share_directory("laser_filters")
        return [
            Node(
                package="laser_filters",
                executable="scan_to_scan_filter_chain",
                name="scan_range_filter",
                output="screen",
                parameters=[config],
                remappings=[
                    ("scan", "/scan_raw"),
                    ("scan_filtered", "/scan"),
                ],
            )
        ]
    except PackageNotFoundError:
        return [
            LogInfo(
                msg="navbot_lidar: install ros-jazzy-laser-filters for /scan filtering"
            )
        ]


def generate_launch_description():
    return LaunchDescription([OpaqueFunction(function=_launch_setup)])
