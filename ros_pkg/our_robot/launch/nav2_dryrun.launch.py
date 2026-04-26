"""
nav2_dryrun.launch.py — 起 nav2 全栈但车不会动.

包含:
  - robot_state_publisher (URDF + TF)
  - odom_tf_broadcaster (odom→base_footprint, 替代 EKF, 省 Pi5 CPU)
  - LiDAR (oradar /scan_lidar)
  - nav2_localization (map_server + amcl)
  - nav2_navigation (planner_server + controller_server + bt_navigator + ...)
  - nav2_bootstrap (发 initialpose + 触发 manage_nodes startup)

不起:
  - mission_fsm (没人发 nav goal → controller 不输出 cmd_vel)
  - cmd_vel_relay (没意义, controller 没源)
  - camera / qr / yolo / battery / EKF (省 CPU, 测 nav2 lifecycle 用)

车不动条件: cmd_vel 发布者数 = 2 但 idle (没 nav goal → controller 不发).

用途: P0 验证 (lifecycle / costmap 是否起来) + RViz 看 map / amcl / costmap 不让车动.
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
    nav2_params = PathJoinSubstitution([pkg_share, "config", "nav2_params.yaml"])

    map_file = LaunchConfiguration(
        "map", default=os.path.expanduser("~/maps/gamefield_map.yaml")
    )
    use_sim_time = LaunchConfiguration("use_sim_time", default="false")

    urdf_path = PathJoinSubstitution([pkg_share, "urdf", "robot.urdf.xacro"])
    robot_state = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        parameters=[{
            "robot_description": ParameterValue(
                Command(["xacro ", urdf_path]), value_type=str
            )
        }],
        output="log",
    )

    odom_tf = Node(
        package="our_robot",
        executable="odom_tf_broadcaster",
        name="odom_tf_broadcaster",
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

    nav2_localization = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare("nav2_bringup"),
                "launch", "localization_launch.py",
            ])
        ]),
        launch_arguments={
            "map": map_file,
            "use_sim_time": use_sim_time,
            "params_file": nav2_params,
        }.items(),
    )

    nav2_navigation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare("nav2_bringup"),
                "launch", "navigation_launch.py",
            ])
        ]),
        launch_arguments={
            "use_sim_time": use_sim_time,
            "params_file": nav2_params,
        }.items(),
    )

    nav2_bootstrap = Node(
        package="our_robot",
        executable="nav2_bootstrap_node",
        name="nav2_bootstrap",
        output="screen",
    )

    return LaunchDescription([
        DeclareLaunchArgument("map", default_value=map_file),
        DeclareLaunchArgument("use_sim_time", default_value="false"),
        robot_state,
        odom_tf,
        lidar,
        nav2_localization,
        nav2_navigation,
        nav2_bootstrap,
    ])
