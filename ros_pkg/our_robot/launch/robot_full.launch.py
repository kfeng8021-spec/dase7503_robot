"""
比赛当天一键启动: micro-ROS agent + LiDAR + camera + QR + Nav2 + Mission FSM.

用法:
  ros2 launch our_robot robot_full.launch.py

调参:
  ros2 launch our_robot robot_full.launch.py map:=/path/to/my_map.yaml
"""
import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    map_file = LaunchConfiguration(
        "map", default=os.path.expanduser("~/maps/gamefield_map.yaml")
    )
    use_sim_time = LaunchConfiguration("use_sim_time", default="false")

    # 1. micro-ROS Agent (接 ESP32)
    # 注意: Full Plan 里波特率是 115200, 跟 ESP32 固件里的 Serial.begin() 必须一致
    micro_ros_agent = ExecuteProcess(
        cmd=[
            "ros2", "run", "micro_ros_agent", "micro_ros_agent",
            "serial", "--dev", "/dev/ttyUSB0", "-b", "115200",
        ],
        output="screen",
    )

    # 2. LiDAR (MS200)
    lidar = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare("ydlidar_ros2_driver"),
                "launch", "ydlidar_launch.py",
            ])
        ])
    )

    # 3. Camera (IMX708 via camera_ros)
    camera = Node(
        package="camera_ros",
        executable="camera_node",
        name="camera_node",
        output="screen",
        parameters=[{"width": 640, "height": 480, "frame_rate": 30.0}],
    )

    # 4. QR Scanner
    qr_scanner = Node(
        package="our_robot",
        executable="qr_scanner_node",
        name="qr_scanner",
        output="screen",
    )

    # 5. Nav2 (localization + navigation, 加载已建好的地图)
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
        }.items(),
    )

    # 6. Mission FSM (主逻辑)
    mission_fsm = Node(
        package="our_robot",
        executable="mission_fsm_node",
        name="mission_fsm",
        output="screen",
    )

    return LaunchDescription([
        DeclareLaunchArgument("map", default_value=map_file),
        DeclareLaunchArgument("use_sim_time", default_value="false"),
        micro_ros_agent,
        lidar,
        camera,
        qr_scanner,
        nav2_localization,
        nav2_navigation,
        mission_fsm,
    ])
