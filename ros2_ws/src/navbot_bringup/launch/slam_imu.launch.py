"""SLAM + IMU fusion + EKF bring-up.

Launches:
  - base + LiDAR (navbot_bringup/base_lidar.launch.py)
  - slam_toolbox (navbot_slam)
  - IMU driver + complementary filter (navbot_imu/imu_fusion.launch.py)
  - robot_localization EKF (navbot_localization/ekf.launch.py)

After this launch, the TF chain is:
    map -> odom        (slam_toolbox)
    odom -> base_footprint   (ekf_filter_node — NOT serial_bridge)
    base_footprint -> base_link, laser_link, imu_link   (URDF)

The EKF fuses wheel odometry (x, y, vx) with IMU (yaw, vyaw) and
republishes /odometry/filtered. Nav2 should be pointed at this
topic instead of raw /odom.
"""

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
    slam_launch = os.path.join(
        get_package_share_directory("navbot_slam"),
        "launch",
        "slam_toolbox.launch.py",
    )
    imu_launch = os.path.join(
        get_package_share_directory("navbot_imu"),
        "launch",
        "imu_fusion.launch.py",
    )
    ekf_launch = os.path.join(
        get_package_share_directory("navbot_localization"),
        "launch",
        "ekf.launch.py",
    )

    return LaunchDescription(
        [
            IncludeLaunchDescription(PythonLaunchDescriptionSource(base_lidar_launch)),
            IncludeLaunchDescription(PythonLaunchDescriptionSource(slam_launch)),
            IncludeLaunchDescription(PythonLaunchDescriptionSource(imu_launch)),
            IncludeLaunchDescription(PythonLaunchDescriptionSource(ekf_launch)),
        ]
    )
