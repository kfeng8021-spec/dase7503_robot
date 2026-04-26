"""
QR 检测 launch — camera_ros::camera_node + our_robot::qr_detector_node.

来源: ~/camera_ws (Group 10 实测能用版本) 集成进 our_robot package.
- camera_ros 节点: 来自 third_party/camera_ros (chistianrauch fork @ 03c9e03), 依赖
  third_party/libcamera (raspberrypi fork @ fe601eb6 + libpisp). 需要先 build
  ~/camera_ws 或把 third_party/{libcamera,camera_ros} build 到 dase7503_robot install.
- qr_detector_node: Group 10 vision node, 订阅 /camera/image_raw (Image, 非 compressed),
  pyzbar 解码 START/END/RACK[A-D]_*, 发布 /qr_result + 保存 G10_Evidence_*.png.

用法 (Pi5):
  source ~/camera_ws/install/setup.bash       # 用 Group10 自编 libcamera + camera_ros
  source ~/dase7503_robot/install/setup.bash  # our_robot package
  export ROS_DOMAIN_ID=20
  ros2 launch our_robot qr_detect.launch.py
"""
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    camera = Node(
        package="camera_ros",
        executable="camera_node",
        output="screen",
        parameters=[{"camera": 0, "width": 640, "height": 480}],
    )
    qr = Node(
        package="our_robot",
        executable="qr_detector_node",
        output="screen",
    )
    return LaunchDescription([camera, qr])
