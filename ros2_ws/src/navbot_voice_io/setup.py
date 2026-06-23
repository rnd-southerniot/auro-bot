from glob import glob
from setuptools import setup

package_name = "navbot_voice_io"

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
    description="Pi-side serial bridge to the ESP32-S3 voice buddy.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "voice_io_node = navbot_voice_io.voice_io_node:main",
        ],
    },
)
