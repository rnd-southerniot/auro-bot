import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    base_lidar_launch = os.path.join(
        get_package_share_directory("navbot_bringup"),
        "launch",
        "base_lidar.launch.py",
    )
    imu_launch = os.path.join(
        get_package_share_directory("navbot_imu"),
        "launch",
        "l3gd20_lsm303d.launch.py",
    )
    ekf_launch = os.path.join(
        get_package_share_directory("navbot_localization"),
        "launch",
        "ekf.launch.py",
    )
    heading_controller_launch = os.path.join(
        get_package_share_directory("navbot_base"),
        "launch",
        "heading_controller.launch.py",
    )
    base_start_delay = LaunchConfiguration("base_start_delay")
    base_serial_port = LaunchConfiguration("base_serial_port")
    lidar_serial_port = LaunchConfiguration("lidar_serial_port")

    return LaunchDescription(
        [
            DeclareLaunchArgument("base_start_delay", default_value="3.0"),
            DeclareLaunchArgument(
                "base_serial_port",
                default_value="/dev/serial/by-id/usb-Raspberry_Pi_Pico_E661410403114B35-if00",
            ),
            DeclareLaunchArgument(
                "lidar_serial_port",
                default_value="/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0",
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(base_lidar_launch),
                launch_arguments={
                    "base_start_delay": base_start_delay,
                    "base_serial_port": base_serial_port,
                    "lidar_serial_port": lidar_serial_port,
                }.items(),
            ),
            IncludeLaunchDescription(PythonLaunchDescriptionSource(imu_launch)),
            IncludeLaunchDescription(PythonLaunchDescriptionSource(heading_controller_launch)),
            IncludeLaunchDescription(PythonLaunchDescriptionSource(ekf_launch)),
        ]
    )
