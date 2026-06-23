from glob import glob
from setuptools import setup

package_name = "navbot_base"

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
    install_requires=["setuptools", "pyserial"],
    zip_safe=True,
    maintainer="robotics",
    maintainer_email="robotics@example.com",
    description="Serial bridge and odometry package for the Maker Pi RP2040 navbot.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "serial_bridge = navbot_base.serial_bridge:main",
            "heading_controller = navbot_base.heading_controller:main",
        ],
    },
)
