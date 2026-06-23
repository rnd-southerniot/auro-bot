import os

from ament_index_python.packages import PackageNotFoundError, get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _launch_setup(_context):
    config = os.path.join(
        get_package_share_directory("navbot_lidar"),
        "config",
        "sllidar_c1.yaml",
    )
    serial_port = LaunchConfiguration("serial_port")
    serial_baudrate = LaunchConfiguration("serial_baudrate")
    frame_id = LaunchConfiguration("frame_id")
    inverted = LaunchConfiguration("inverted")
    angle_compensate = LaunchConfiguration("angle_compensate")
    scan_mode = LaunchConfiguration("scan_mode")

    try:
        get_package_share_directory("sllidar_ros2")
        return [
            Node(
                package="sllidar_ros2",
                executable="sllidar_node",
                name="sllidar_node",
                output="screen",
                parameters=[
                    config,
                    {
                        "serial_port": serial_port,
                        "serial_baudrate": serial_baudrate,
                        "frame_id": frame_id,
                        "inverted": inverted,
                        "angle_compensate": angle_compensate,
                        "scan_mode": scan_mode,
                    },
                ],
                remappings=[("scan", "/scan_raw")],
            )
        ]
    except PackageNotFoundError:
        return [
            LogInfo(
                msg="navbot_lidar: install or source sllidar_ros2 to enable /scan"
            )
        ]


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "serial_port",
                default_value="/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0",
            ),
            DeclareLaunchArgument("serial_baudrate", default_value="460800"),
            DeclareLaunchArgument("frame_id", default_value="laser_link"),
            DeclareLaunchArgument("inverted", default_value="false"),
            DeclareLaunchArgument("angle_compensate", default_value="true"),
            DeclareLaunchArgument("scan_mode", default_value="Standard"),
            OpaqueFunction(function=_launch_setup),
        ]
    )
