"""
比赛当天一键启动: micro-ROS agent + LiDAR + camera + QR + Nav2 + Mission FSM + battery + URDF.

用法:
  ros2 launch our_robot robot_full.launch.py
  ros2 launch our_robot robot_full.launch.py map:=/path/to/my_map.yaml
"""
import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_share = FindPackageShare("our_robot")
    nav2_params = PathJoinSubstitution([pkg_share, "config", "nav2_params.yaml"])

    map_file = LaunchConfiguration(
        "map", default=os.path.expanduser("~/maps/gamefield_map.yaml")
    )
    use_sim_time = LaunchConfiguration("use_sim_time", default="false")
    esp_dev = LaunchConfiguration("esp_dev", default="/dev/ttyUSB0")

    # 1. micro-ROS Agent (ESP32, 波特率 115200 必须跟固件 Serial.begin 一致)
    agent = ExecuteProcess(
        cmd=[
            "ros2", "run", "micro_ros_agent", "micro_ros_agent",
            "serial", "--dev", esp_dev, "-b", "115200",
        ],
        output="screen",
    )

    # 2. URDF robot_state_publisher (TF 树 base_footprint→base_link→laser→camera)
    urdf_path = PathJoinSubstitution([pkg_share, "urdf", "robot.urdf.xacro"])
    robot_state = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        parameters=[{"robot_description": Command(["xacro ", urdf_path])}],
        output="log",
    )

    # 3. LiDAR (MS200)
    lidar = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare("ydlidar_ros2_driver"),
                "launch", "ydlidar_launch.py",
            ])
        ])
    )

    # 4. Camera (IMX708 via camera_ros)
    camera = Node(
        package="camera_ros",
        executable="camera_node",
        name="camera_node",
        output="log",
        parameters=[{"width": 640, "height": 480, "frame_rate": 30.0}],
    )

    # 5. QR Scanner
    qr_scanner = Node(
        package="our_robot",
        executable="qr_scanner_node",
        name="qr_scanner",
        output="screen",
    )

    # 6. Battery Monitor
    battery = Node(
        package="our_robot",
        executable="battery_monitor_node",
        name="battery_monitor",
        output="screen",
    )

    # 6b. Odom TF Broadcaster (补齐 odom -> base_footprint TF, Nav2 必需)
    odom_tf = Node(
        package="our_robot",
        executable="odom_tf_broadcaster",
        name="odom_tf_broadcaster",
        output="log",
    )

    # 7. Nav2 Localization (AMCL, 加载赛前建好的地图)
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

    # 8. Nav2 Navigation (planner + controller)
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

    # 9. Mission FSM
    mission_fsm = Node(
        package="our_robot",
        executable="mission_fsm_node",
        name="mission_fsm",
        output="screen",
    )

    return LaunchDescription([
        DeclareLaunchArgument("map", default_value=map_file),
        DeclareLaunchArgument("use_sim_time", default_value="false"),
        DeclareLaunchArgument("esp_dev", default_value="/dev/ttyUSB0"),
        agent,
        robot_state,
        odom_tf,
        lidar,
        camera,
        qr_scanner,
        battery,
        nav2_localization,
        nav2_navigation,
        mission_fsm,
    ])
