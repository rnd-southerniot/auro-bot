from glob import glob
from setuptools import setup

package_name = "navbot_imu"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/launch", glob("launch/*.py")),
        (f"share/{package_name}/config", glob("config/*.yaml")),
    ],
    install_requires=["setuptools", "smbus2"],
    zip_safe=True,
    maintainer="robotics",
    maintainer_email="robotics@example.com",
    description="Pi-side L3GD20 + LSM303D IMU reader for the navbot.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "l3gd20_lsm303d_reader = navbot_imu.l3gd20_lsm303d_reader:main",
        ],
    },
)
