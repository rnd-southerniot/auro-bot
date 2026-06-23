from glob import glob
from setuptools import setup

package_name = "navbot_lidar"

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
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="robotics",
    maintainer_email="robotics@example.com",
    description="LiDAR wrapper package for makerpi-rp2040-ros2-navbot.",
    license="Apache-2.0",
)
