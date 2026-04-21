#!/usr/bin/env bash
# SLAM 建图完成后保存地图到 ~/maps/gamefield_map.{yaml,pgm}.
# 前提: slam_mapping.launch.py 正在运行且地图已完整.

set -e
MAP_DIR="${MAP_DIR:-$HOME/maps}"
MAP_NAME="${MAP_NAME:-gamefield_map}"

mkdir -p "$MAP_DIR"
cd "$MAP_DIR"

source /opt/ros/jazzy/setup.bash
echo "保存地图到 $MAP_DIR/$MAP_NAME.{yaml,pgm}"
ros2 run nav2_map_server map_saver_cli -f "$MAP_NAME" --ros-args -p save_map_timeout:=10000.0

echo "完成:"
ls -l "$MAP_DIR"

echo
echo "下一步: 赛前把这两个文件备份到 U 盘, 万一 SD 挂了能恢复"
