from setuptools import find_packages, setup
from glob import glob

package_name = "our_robot"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/launch", glob("launch/*.launch.py")),
        (f"share/{package_name}/config", glob("config/*.yaml")),
        (f"share/{package_name}/config", glob("config/*.rviz")),
        (f"share/{package_name}/urdf", glob("urdf/*.xacro")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="DASE7503 Team",
    maintainer_email="kfeng8021@gmail.com",
    description="DASE7503 robot mission FSM + QR scanner + manual fallback + battery monitor",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "qr_scanner_node = our_robot.qr_scanner_node:main",
            "mission_fsm_node = our_robot.mission_fsm_node:main",
            "manual_mission_node = our_robot.manual_mission_node:main",
            "battery_monitor_node = our_robot.battery_monitor_node:main",
            "odom_tf_broadcaster = our_robot.odom_tf_broadcaster:main",
        ],
    },
)
