"""Launch the Pi-side IMU reader and an imu_complementary_filter that
publishes a fused orientation on /imu/data.

Pipeline:
  l3gd20_lsm303d_reader
    /imu/l3gd20_lsm303d/raw  (remap)-> /imu/data_raw
    /imu/l3gd20_lsm303d/mag  (remap)-> /imu/mag    (published but unused
                                                     while use_mag:=False)
  imu_complementary_filter
    subscribes: /imu/data_raw, /imu/mag
    publishes:  /imu/data

2026-04-22 (session 10): mag fusion explored and REVERTED.
Hard-iron calibration succeeded (|vec| 1.43 → 0.42 gauss, clean
sphere, static rotation tracks physical heading cleanly). But
3-trial spin-and-return benchmark revealed mag fusion DEGRADES
heading during motion: EKF round-trip drift 9.73° (stdev 10.69°)
vs raw /odom 0.36°. Motor coils active during spinning distort
the local magnetic field at the IMU's axle-height mount; the
complementary filter then applies distorted readings and yaw
drifts. The ±4.0 gauss gain + offset calibration remain in the
driver/yaml so re-enabling is a one-line change once the IMU
can be physically relocated further from the motor stack.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    imu_config = PathJoinSubstitution(
        [FindPackageShare("navbot_imu"), "config", "l3gd20_lsm303d.yaml"]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument("log_level", default_value="info"),
            Node(
                package="navbot_imu",
                executable="l3gd20_lsm303d_reader",
                name="navbot_l3gd20_lsm303d_reader",
                output="screen",
                parameters=[imu_config],
                remappings=[
                    ("/imu/l3gd20_lsm303d/raw", "/imu/data_raw"),
                    ("/imu/l3gd20_lsm303d/mag", "/imu/mag"),
                ],
                arguments=["--ros-args", "--log-level", LaunchConfiguration("log_level")],
            ),
            Node(
                package="imu_complementary_filter",
                executable="complementary_filter_node",
                name="imu_complementary_filter",
                output="screen",
                parameters=[
                    {
                        "use_mag": False,
                        "do_bias_estimation": True,
                        "do_adaptive_gain": True,
                        "gain_acc": 0.01,
                        "gain_mag": 0.01,
                        "publish_tf": False,
                        "publish_debug_topics": False,
                        "fixed_frame": "odom",
                    }
                ],
            ),
        ]
    )
