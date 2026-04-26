#!/usr/bin/env bash
# 在 frank 本机启动 RViz 看 Pi5 实时 SLAM 建图.
# 用法: bash scripts/rviz_remote.sh
set -e

source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=20
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///home/frank/cyclonedds_frank.xml

CONFIG="/home/frank/桌面/dase7503_robot/ros_pkg/our_robot/config/robot_view.rviz"

# 重启 daemon 强制读新 cyclonedds 配置
ros2 daemon stop >/dev/null 2>&1 || true
sleep 1

echo "RViz 启动中... 订阅 /map /scan_lidar /tf 来自 Pi5 (172.20.10.9)"
exec rviz2 -d "$CONFIG"
