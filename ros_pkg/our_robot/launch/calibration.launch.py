"""
相机内参标定 launch (Full Plan C4 必做).

用法:
  1. 打印 8×6 棋盘格 (每格 30mm), 贴硬纸板
  2. Pi5 上: ros2 launch our_robot calibration.launch.py
  3. 另一终端: ros2 run camera_calibration cameracalibrator \
       --size 8x6 --square 0.030 image:=/camera/image_raw camera:=/camera
  4. 拿着棋盘在相机前移动 (左右/前后/倾斜) 直到四条进度条变绿
  5. 点 CALIBRATE -> 等 10-30 秒 -> COMMIT
  6. 标定结果自动存到 ~/.ros/camera_info/camera.yaml
"""
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    camera = Node(
        package="camera_ros",
        executable="camera_node",
        name="camera_node",
        output="screen",
        parameters=[{"width": 1280, "height": 960, "frame_rate": 10.0}],  # 高分辨率提高精度
    )
    return LaunchDescription([camera])
