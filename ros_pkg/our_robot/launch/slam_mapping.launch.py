"""
赛前 SLAM 建图 launch.

流程:
  1. 到赛场, Pi5 上电
  2. ros2 launch our_robot slam_mapping.launch.py
  3. 另一终端 teleop 手动推: ros2 run teleop_twist_keyboard teleop_twist_keyboard
  4. 覆盖全场 2-3 圈 (看 RViz 里地图边缘闭合)
  5. ~/dase7503_robot/scripts/save_map.sh  保存到 ~/maps/gamefield_map.{yaml,pgm}

如果队友想自己单独跑, 不要用 robot_full.launch.py (它加载已有地图做定位, 不建图).
"""
import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_share = FindPackageShare("our_robot")
    slam_params = PathJoinSubstitution([pkg_share, "config", "slam_toolbox_params.yaml"])

    esp_dev = LaunchConfiguration("esp_dev", default="/dev/esp32")

    # 1. micro-ROS Agent (底盘必须上线, SLAM 需要 odom)
    agent = ExecuteProcess(
        cmd=[
            "ros2", "run", "micro_ros_agent", "micro_ros_agent",
            "serial", "--dev", esp_dev, "-b", "115200",
        ],
        output="screen",
    )

    # 2. LiDAR
    lidar = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare("ydlidar_ros2_driver"),
                "launch", "ydlidar_launch.py",
            ])
        ])
    )

    # 3. URDF robot_state_publisher (给 TF 树提供 base_link -> laser_link 等静态 TF)
    from launch.substitutions import Command
    pkg_share = FindPackageShare("our_robot")
    urdf_path = PathJoinSubstitution([pkg_share, "urdf", "robot.urdf.xacro"])
    robot_state = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        parameters=[{"robot_description": Command(["xacro ", urdf_path])}],
        output="log",
    )

    # 3b. odom -> base_footprint TF (SLAM 也需要)
    odom_tf = Node(
        package="our_robot",
        executable="odom_tf_broadcaster",
        name="odom_tf_broadcaster",
        output="log",
    )

    # 4. SLAM Toolbox (online async 模式, 边走边建)
    slam = Node(
        package="slam_toolbox",
        executable="async_slam_toolbox_node",
        name="slam_toolbox",
        parameters=[slam_params, {"use_sim_time": False}],
        output="screen",
    )

    # 5. Teleop 提示: 单独终端跑 ros2 run teleop_twist_keyboard teleop_twist_keyboard
    # 这里不拉起 (终端抢焦点)

    return LaunchDescription([
        DeclareLaunchArgument("esp_dev", default_value="/dev/esp32"),
        agent,
        robot_state,
        odom_tf,
        lidar,
        slam,
    ])
