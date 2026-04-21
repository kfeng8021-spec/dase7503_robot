"""
B range 完整手动模式 (Game Demonstration 评分 B range).

所有自动化功能都启动, 但 FSM 换成手动版 (只记 QR 时间戳, 不发 Nav2 目标).

用法:
  # 终端 1: 启动全部节点
  ros2 launch our_robot robot_manual.launch.py

  # 终端 2: 键盘控制底盘 (WASD / 箭头)
  ros2 run teleop_twist_keyboard teleop_twist_keyboard

  # 终端 3: 手动控制升降 (u/d)
  ros2 run our_robot manual_mission_node
  (已在 launch 中拉起, 如终端不方便输入再单独拉)
"""
from launch import LaunchDescription
from launch.actions import ExecuteProcess
from launch.substitutions import Command, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_share = FindPackageShare("our_robot")

    agent = ExecuteProcess(
        cmd=["ros2", "run", "micro_ros_agent", "micro_ros_agent",
             "serial", "--dev", "/dev/ttyUSB0", "-b", "115200"],
        output="screen",
    )
    urdf_path = PathJoinSubstitution([pkg_share, "urdf", "robot.urdf.xacro"])
    robot_state = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        parameters=[{"robot_description": Command(["xacro ", urdf_path])}],
    )
    camera = Node(package="camera_ros", executable="camera_node", output="log")
    qr = Node(package="our_robot", executable="qr_scanner_node", output="screen")
    battery = Node(package="our_robot", executable="battery_monitor_node", output="screen")
    manual_fsm = Node(
        package="our_robot",
        executable="manual_mission_node",
        output="screen",
        prefix="xterm -e",   # 独立窗口, 键盘输入不冲突
    )

    return LaunchDescription([agent, robot_state, camera, qr, battery, manual_fsm])
