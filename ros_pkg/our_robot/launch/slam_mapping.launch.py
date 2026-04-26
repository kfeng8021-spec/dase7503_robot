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
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_share = FindPackageShare("our_robot")
    slam_params = PathJoinSubstitution([pkg_share, "config", "slam_toolbox_params.yaml"])
    ekf_params = PathJoinSubstitution([pkg_share, "config", "ekf.yaml"])

    # micro-ROS agent: 由 systemd 启 (factory FW, /dev/ttyUSB0 @ 921600, domain 20).
    # 原来这里 ExecuteProcess 启 agent 和 systemd 冲串口, 去掉.

    # 2. LiDAR (ORADAR MS200, 直接内联 Node 以覆盖 scan_topic).
    # 发 /scan_lidar 而非 /scan, 因为 ESP32 factory FW 也发 /scan (空数据),
    # 两个 publisher 同名会污染 SLAM 输入.
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

    # 3. URDF robot_state_publisher (给 TF 树提供 base_link -> laser_link 等静态 TF)
    from launch.substitutions import Command
    pkg_share = FindPackageShare("our_robot")
    urdf_path = PathJoinSubstitution([pkg_share, "urdf", "robot.urdf.xacro"])
    robot_state = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        parameters=[{
            "robot_description": ParameterValue(
                Command(["xacro ", urdf_path]), value_type=str
            )
        }],
        output="log",
    )

    # 3b. EKF 融合 wheel odom + IMU → 发 odom→base_footprint TF
    # (取代 odom_tf_broadcaster, 修 Mecanum 打滑 yaw drift)
    ekf = Node(
        package="robot_localization",
        executable="ekf_node",
        name="ekf_filter_node",
        parameters=[ekf_params],
        output="screen",
    )

    # 4. SLAM Toolbox (online async 模式, 边走边建).
    # 不手工 Node() — async_slam_toolbox_node 是 lifecycle 节点, 需要外部
    # configure+activate. 直接用 slam_toolbox 官方 online_async_launch.py,
    # 它自己处理 lifecycle 转换.
    slam = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare("slam_toolbox"),
                "launch", "online_async_launch.py",
            ])
        ]),
        launch_arguments={
            "slam_params_file": slam_params,
            "use_sim_time": "false",
        }.items(),
    )

    # 5. Teleop 提示: 单独终端跑 ros2 run teleop_twist_keyboard teleop_twist_keyboard
    # 这里不拉起 (终端抢焦点)

    return LaunchDescription([
        robot_state,
        ekf,
        lidar,
        slam,
    ])
