"""
比赛当天一键启动: micro-ROS agent + LiDAR + camera + QR + Nav2 + Mission FSM + battery + URDF.

用法:
  ros2 launch our_robot robot_full.launch.py
  ros2 launch our_robot robot_full.launch.py map:=/path/to/my_map.yaml
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
    ekf_params = PathJoinSubstitution([pkg_share, "config", "ekf.yaml"])

    map_file = LaunchConfiguration(
        "map", default=os.path.expanduser("~/maps/gamefield_map.yaml")
    )
    use_sim_time = LaunchConfiguration("use_sim_time", default="false")

    # micro-ROS agent: 由 systemd 启 (factory FW, /dev/ttyUSB0 @ 921600, domain 20).
    # 原来这里 ExecuteProcess 启 agent 和 systemd 冲串口, 去掉.

    # 2. URDF robot_state_publisher (TF 树 base_footprint→base_link→laser→camera)
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

    # 3. LiDAR (Oradar MS200, 内联 Node 以覆盖 scan_topic).
    # 发 /scan_lidar 而非 /scan, 因为 ESP32 factory FW 也发 /scan (空数据).
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

    # 4. Camera (IMX708 via camera_ros)
    # camera_ros 默认 publish 到 /camera_node/image_raw (node name 当 namespace).
    # qr_detector / yolo 订阅 /camera/image_raw, 必须 explicit remap.
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

    # 5. QR Detector (Group10 实测能用版本, 订阅 /camera/image_raw, 5s 去重)
    # 之前是 qr_scanner_node (订阅 compressed), 改成 qr_detector_node 跟单跑测试一致.
    qr_scanner = Node(
        package="our_robot",
        executable="qr_detector_node",
        name="qr_detector",
        output="screen",
    )

    # 5b. YOLO Detector (Tutorial 7 加分项, onnxruntime CPU, yolov8n)
    # 订 /camera/image_raw/compressed, 发 /yolo/detections/compressed
    # 和 qr_scanner 共用相机图像流, 互不冲突.
    yolo = Node(
        package="our_robot",
        executable="yolo_detector_node",
        name="yolo_detector",
        output="log",
        parameters=[{
            "confidence_threshold": 0.5,
            "iou_threshold": 0.45,
            "show_window": False,
            "input_size": 640,
        }],
    )

    # 6. Battery Monitor
    battery = Node(
        package="our_robot",
        executable="battery_monitor_node",
        name="battery_monitor",
        output="screen",
    )

    # 6a. QoS bridge: ESP32 BE publish → RELIABLE for EKF
    qos_bridge = Node(
        package="our_robot",
        executable="qos_bridge_node",
        name="qos_bridge",
        output="log",
    )

    # 6b. EKF 融合 wheel odom + IMU → 发 odom→base_footprint TF
    ekf = Node(
        package="robot_localization",
        executable="ekf_node",
        name="ekf_filter_node",
        parameters=[ekf_params],
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

    # 8b. cmd_vel relay: /cmd_vel_nav → /cmd_vel (绕过 velocity_smoother + collision_monitor)
    # nav2 default chain controller→smoother→collision→/cmd_vel 实测卡死,
    # 直接 controller→/cmd_vel 让 ESP32 收到驱动信号.
    cmd_vel_relay = Node(
        package="our_robot",
        executable="cmd_vel_relay_node",
        name="cmd_vel_relay",
        output="screen",
    )

    # 8c. nav2 bootstrap: 发 /initialpose + 调 lifecycle_manager_navigation
    # manage_nodes(STARTUP) 重新激活 navigation 链.
    # 修 P0a/P0b 根因: AMCL 没收 initialpose → controller_server configure 超时
    # → lifecycle_manager_navigation 卡 inactive → costmap 不发 → controller 不动.
    # 实测 2026-04-27 凌晨, 见 nav2_bootstrap_node.py docstring.
    nav2_bootstrap = Node(
        package="our_robot",
        executable="nav2_bootstrap_node",
        name="nav2_bootstrap",
        output="screen",
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
        robot_state,
        qos_bridge,
        ekf,
        lidar,
        camera,
        qr_scanner,
        # yolo,   # 暂禁: Pi5 CPU 跑不动 nav2+camera+yolo 同时跑, controller 频率掉到 7Hz fail
        battery,
        nav2_localization,
        nav2_navigation,
        cmd_vel_relay,
        nav2_bootstrap,
        mission_fsm,
    ])
