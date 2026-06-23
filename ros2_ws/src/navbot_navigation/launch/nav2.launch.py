import os

from ament_index_python.packages import PackageNotFoundError, get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, LogInfo, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource


def _launch_setup(_context):
    params_file = os.path.join(
        get_package_share_directory("navbot_navigation"),
        "config",
        "nav2_params.yaml",
    )

    try:
        nav2_share = get_package_share_directory("nav2_bringup")
    except PackageNotFoundError:
        return [LogInfo(msg="navbot_navigation: install Nav2 to enable navigation bringup")]

    # Nav2 Jazzy navigation_launch.py includes velocity_smoother which
    # subscribes to cmd_vel_nav and publishes to cmd_vel, so the serial
    # bridge receives commands on /cmd_vel without extra remapping.
    launch_file = os.path.join(nav2_share, "launch", "navigation_launch.py")
    return [
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(launch_file),
            launch_arguments={"params_file": params_file, "use_sim_time": "false"}.items(),
        )
    ]


def generate_launch_description():
    return LaunchDescription([OpaqueFunction(function=_launch_setup)])
