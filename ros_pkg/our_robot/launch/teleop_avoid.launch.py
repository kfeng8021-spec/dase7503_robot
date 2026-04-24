"""
Teleop + LiDAR 避障 launch.

起这些节点:
  - MS200 LiDAR (oradar_lidar 的 oradar_scan, 发布 /scan_lidar, port=/dev/lidar)
  - laser_safety_gate (/cmd_vel_raw + /scan_lidar -> /cmd_vel)

依赖前置(这个 launch 不启动):
  - systemd `micro-ros-agent` 已 running (factory FW, serial @ /dev/ttyUSB0 @ 921600,
    ROS_DOMAIN_ID=20). 验证: `systemctl is-active micro-ros-agent` → active
  - LiDAR 通过 USB 接 Pi5 (课程材料: "Lidar will be connected with Raspberry Pi 5"),
    udev 规则建 /dev/lidar 符号链接 (CH343 VID 1a86:55d4).

为什么 scan 不发 /scan 而发 /scan_lidar:
  ESP32 factory FW 会持续发布 /scan, 即使板上 LiDAR 口不接, ranges 也是全 0.0.
  如果 oradar 也发 /scan, 两个 publisher 会让下游读到交替的真假数据 → safety gate
  永远触发硬停. 所以 oradar 发 /scan_lidar, 下游订 /scan_lidar, 完全避开 ESP32 那一路.

另一个终端跑遥控 (把 teleop 的默认 /cmd_vel 重映射到 /cmd_vel_raw):
  source /opt/ros/jazzy/setup.bash
  source ~/ros2_ws/install/setup.bash
  ros2 run teleop_twist_keyboard teleop_twist_keyboard \\
    --ros-args -r /cmd_vel:=/cmd_vel_raw

参数:
  hard_stop_dist  default 0.25 m — 小于此直接停这个方向
  slow_down_dist  default 0.50 m — 介于这两个之间线性缩放
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    hard_stop = LaunchConfiguration("hard_stop_dist")
    slow_down = LaunchConfiguration("slow_down_dist")

    lidar = Node(
        package="oradar_lidar",
        executable="oradar_scan",
        name="MS200",
        output="screen",
        parameters=[{
            "device_model": "MS200",
            "frame_id": "laser_link",
            "scan_topic": "scan_lidar",
            "port_name": "/dev/lidar",
            "baudrate": 230400,
            "angle_min": 0.0,
            "angle_max": 360.0,
            "range_min": 0.05,
            "range_max": 20.0,
            "clockwise": False,
            "motor_speed": 10,
        }],
    )

    safety = Node(
        package="our_robot",
        executable="laser_safety_node",
        name="laser_safety_gate",
        output="screen",
        parameters=[{
            "hard_stop_dist": hard_stop,
            "slow_down_dist": slow_down,
            "scan_topic": "scan_lidar",
            "cmd_in_topic": "cmd_vel_raw",
            "cmd_out_topic": "cmd_vel",
            "watchdog_sec": 0.5,
        }],
    )

    return LaunchDescription([
        DeclareLaunchArgument("hard_stop_dist", default_value="0.25"),
        DeclareLaunchArgument("slow_down_dist", default_value="0.50"),
        lidar,
        safety,
    ])
