"""
B range (手动控制) launch — 自动导航失败时的保底方案.

启动:
  - micro-ROS Agent
  - 相机 + QR 扫描 (任务要求必须扫 QR)
  - teleop_twist_keyboard (需要在前台终端)
  - manual_mission_node (监听 QR + 记录时间戳 + 控制升降)

比赛 SOP:
  1. 比赛开始前先跑 robot_full.launch.py 试自动
  2. 3 分钟倒计时前如果自动失败 -> Ctrl-C -> 切这个 launch
  3. 用键盘控制机器人 + 扫 QR + 按键抬升降机构
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    esp_dev = LaunchConfiguration("esp_dev", default="/dev/esp32")

    agent = ExecuteProcess(
        cmd=["ros2", "run", "micro_ros_agent", "micro_ros_agent",
             "serial", "--dev", esp_dev, "-b", "115200"],
        output="screen",
    )
    camera = Node(package="camera_ros", executable="camera_node", output="screen")
    qr = Node(package="our_robot", executable="qr_scanner_node", output="screen")
    manual_fsm = Node(
        package="our_robot",
        executable="manual_mission_node",
        output="screen",
    )

    return LaunchDescription([
        DeclareLaunchArgument("esp_dev", default_value="/dev/esp32"),
        agent, camera, qr, manual_fsm,
    ])
