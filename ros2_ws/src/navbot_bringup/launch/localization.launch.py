"""Map-based full navigation bring-up (session 11).

Replaces slam_imu.launch.py's slam_toolbox with map_server + AMCL and
ALSO brings up the Nav2 stack. Use this launch when you have a
pre-saved map and want to navigate on it. Use slam_imu.launch.py
when you want to build a new map.

TF tree after bring-up:
    map (anchor) -> odom             (AMCL)
    odom         -> base_footprint   (EKF)
    base_footprint -> base_link, laser_link, imu_link    (URDF)

Launches:
  - base + LiDAR            (navbot_bringup/base_lidar.launch.py)
  - IMU driver + comp filter  (navbot_imu/imu_fusion.launch.py)
  - robot_localization EKF  (navbot_localization/ekf.launch.py)
  - map_server + AMCL       (Nav2 localization_launch.py)
  - Nav2 controller/planner (navbot_navigation/nav2.launch.py)

Launch args:
  map    — path to a map yaml. Optional; falls back to the
           yaml_filename param in nav2_params.yaml
           (/home/arif/projects/claude-navbot/maps/office_lab.yaml).
"""

import os

from ament_index_python.packages import PackageNotFoundError, get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo, OpaqueFunction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression


def _launch_setup(_context):
    base_lidar = os.path.join(
        get_package_share_directory("navbot_bringup"),
        "launch",
        "base_lidar.launch.py",
    )
    imu_fusion = os.path.join(
        get_package_share_directory("navbot_imu"),
        "launch",
        "imu_fusion.launch.py",
    )
    ekf = os.path.join(
        get_package_share_directory("navbot_localization"),
        "launch",
        "ekf.launch.py",
    )
    nav2_params = os.path.join(
        get_package_share_directory("navbot_navigation"),
        "config",
        "nav2_params.yaml",
    )
    nav2_launch_in_navbot = os.path.join(
        get_package_share_directory("navbot_navigation"),
        "launch",
        "nav2.launch.py",
    )

    try:
        nav2_share = get_package_share_directory("nav2_bringup")
    except PackageNotFoundError:
        return [LogInfo(msg="navbot_bringup: install Nav2 to enable localization bring-up")]

    loc_launch = os.path.join(nav2_share, "launch", "localization_launch.py")
    map_arg = LaunchConfiguration("map")

    return [
        IncludeLaunchDescription(PythonLaunchDescriptionSource(base_lidar)),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(imu_fusion)),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(ekf)),
        # Nav2 localization (map_server + amcl). `map` arg overrides
        # yaml_filename if provided.
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(loc_launch),
            launch_arguments={
                "params_file": nav2_params,
                "use_sim_time": "false",
                "map": map_arg,
                "autostart": "true",
            }.items(),
        ),
        # Full Nav2 navigation stack (controller, planner, bt, recoveries).
        IncludeLaunchDescription(PythonLaunchDescriptionSource(nav2_launch_in_navbot)),
    ]


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "map",
                default_value="",
                description="Path to map yaml. If empty, falls back to map_server.yaml_filename in nav2_params.yaml.",
            ),
            OpaqueFunction(function=_launch_setup),
        ]
    )
