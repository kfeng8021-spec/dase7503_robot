"""
B range (手动控制) launch — 比赛保底方案.

启动:
  - LiDAR (oradar MS200, 发 /scan_lidar)
  - laser_safety_gate (cmd_vel_raw + scan → cmd_vel, 自动避障停车)
  - 相机 + qr_detector_node (Group10 BE 版本 + 5s 去重, 实测能用)
  - manual_mission_node (监听 QR + 写 CSV + 键盘 u/d 控制升降)

agent: 由 systemd 管 (这里不启动避免 serial 冲突)

比赛 SOP:
  1. 跑这个 launch
  2. 另一终端跑 teleop_twist_keyboard (remap cmd_vel → cmd_vel_raw):
       ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r /cmd_vel:=/cmd_vel_raw
  3. 第三终端 (前台抓键盘) 按 u/d 升降:
       ros2 run our_robot manual_mission_node
  4. 推车扫各 QR + 按 u/d 控制升降
  5. 实时看 QR 检测结果:
       ros2 topic echo /qr_result
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    hard_stop = LaunchConfiguration("hard_stop_dist", default="0.25")
    slow_down = LaunchConfiguration("slow_down_dist", default="0.50")

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

    camera = Node(
        package="camera_ros",
        executable="camera_node",
        name="camera_node",
        output="log",
        parameters=[{"width": 640, "height": 480, "frame_rate": 30.0}],
        remappings=[
            ("/camera_node/image_raw", "/camera/image_raw"),
            ("/camera_node/image_raw/compressed", "/camera/image_raw/compressed"),
            ("/camera_node/camera_info", "/camera/camera_info"),
        ],
    )

    qr = Node(
        package="our_robot",
        executable="qr_detector_node",
        name="qr_detector",
        output="screen",
    )

    return LaunchDescription([
        DeclareLaunchArgument("hard_stop_dist", default_value="0.25"),
        DeclareLaunchArgument("slow_down_dist", default_value="0.50"),
        lidar,
        safety,
        camera,
        qr,
    ])
