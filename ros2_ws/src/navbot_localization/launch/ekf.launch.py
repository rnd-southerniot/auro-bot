import os

from ament_index_python.packages import PackageNotFoundError, get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _launch_setup(_context):
    params_file = os.path.join(
        get_package_share_directory("navbot_localization"),
        "config",
        "ekf.yaml",
    )
    use_sim_time = LaunchConfiguration("use_sim_time")

    try:
        get_package_share_directory("robot_localization")
    except PackageNotFoundError:
        return [
            LogInfo(
                msg="navbot_localization: install robot_localization to enable EKF bringup"
            )
        ]

    # NOTE: intentionally do NOT pass {"use_sim_time": use_sim_time}
    # as a launch-time override — the LaunchConfiguration resolves to
    # a STRING at launch time, and robot_localization's ekf_node does
    # not coerce string→bool for this param. It then treats any non-
    # empty string as truthy and blocks on "Waiting for clock to
    # start...". Keep use_sim_time in the yaml only.
    return [
        Node(
            package="robot_localization",
            executable="ekf_node",
            name="ekf_filter_node",
            output="screen",
            parameters=[params_file],
            remappings=[("odometry/filtered", "/odometry/filtered")],
        )
    ]


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument("use_sim_time", default_value="false"),
            OpaqueFunction(function=_launch_setup),
        ]
    )
