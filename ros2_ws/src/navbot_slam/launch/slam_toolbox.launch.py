import os

from ament_index_python.packages import PackageNotFoundError, get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, LogInfo, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource


def _launch_setup(_context):
    params_file = os.path.join(
        get_package_share_directory("navbot_slam"),
        "config",
        "slam_toolbox.yaml",
    )

    try:
        slam_share = get_package_share_directory("slam_toolbox")
    except PackageNotFoundError:
        return [LogInfo(msg="navbot_slam: install slam_toolbox to enable SLAM bringup")]

    launch_file = os.path.join(slam_share, "launch", "online_async_launch.py")
    return [
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(launch_file),
            launch_arguments={"slam_params_file": params_file}.items(),
        )
    ]


def generate_launch_description():
    return LaunchDescription([OpaqueFunction(function=_launch_setup)])
