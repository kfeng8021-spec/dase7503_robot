"""
Teleop + LiDAR 避障 launch.

起这些节点:
  - micro-ROS Agent (ESP32)
  - MS200 LiDAR (/scan)
  - laser_safety_gate (/cmd_vel_raw + /scan -> /cmd_vel)

另一个终端跑遥控 (把 teleop 的默认 /cmd_vel 重映射到 /cmd_vel_raw):
  source /opt/ros/jazzy/setup.bash
  source ~/ros2_ws/install/setup.bash
  ros2 run teleop_twist_keyboard teleop_twist_keyboard \\
    --ros-args -r /cmd_vel:=/cmd_vel_raw

参数:
  esp_dev         default /dev/esp32 (fallback: /dev/ttyUSB0)
  lidar_dev       default /dev/lidar (fallback: /dev/ttyUSB1)
  hard_stop_dist  default 0.25 m — 小于此直接停这个方向
  slow_down_dist  default 0.50 m — 介于这两个之间线性缩放
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    esp_dev = LaunchConfiguration("esp_dev")
    lidar_dev = LaunchConfiguration("lidar_dev")
    hard_stop = LaunchConfiguration("hard_stop_dist")
    slow_down = LaunchConfiguration("slow_down_dist")

    agent = ExecuteProcess(
        cmd=[
            "ros2", "run", "micro_ros_agent", "micro_ros_agent",
            "serial", "--dev", esp_dev, "-b", "115200",
        ],
        output="screen",
    )

    lidar = Node(
        package="oradar_lidar",
        executable="oradar_scan",
        name="MS200",
        output="screen",
        parameters=[{
            "device_model": "MS200",
            "frame_id": "laser_link",
            "scan_topic": "scan",
            "port_name": lidar_dev,
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
            "scan_topic": "scan",
            "cmd_in_topic": "cmd_vel_raw",
            "cmd_out_topic": "cmd_vel",
            "watchdog_sec": 0.5,
        }],
    )

    return LaunchDescription([
        DeclareLaunchArgument("esp_dev", default_value="/dev/esp32"),
        DeclareLaunchArgument("lidar_dev", default_value="/dev/lidar"),
        DeclareLaunchArgument("hard_stop_dist", default_value="0.25"),
        DeclareLaunchArgument("slow_down_dist", default_value="0.50"),
        agent,
        lidar,
        safety,
    ])
