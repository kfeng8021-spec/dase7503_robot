#!/usr/bin/env bash
# 安装 systemd 服务 + udev 规则, 使 Pi5 开机自动拉起机器人栈.
#
# 前提: install.sh 已经跑完, ros2_ws 已编译.
# 用法: sudo bash install_systemd.sh

set -e
[ "$(id -u)" -eq 0 ] || { echo "sudo 跑"; exit 1; }
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "[systemd] 复制服务文件到 /etc/systemd/system/"
cp "$SCRIPT_DIR/systemd/micro-ros-agent.service" /etc/systemd/system/
cp "$SCRIPT_DIR/systemd/robot.service" /etc/systemd/system/

echo "[udev] 复制规则到 /etc/udev/rules.d/"
cp "$SCRIPT_DIR/udev/99-robot-devices.rules" /etc/udev/rules.d/
udevadm control --reload-rules
udevadm trigger

echo "[systemd] 重新加载 + 启用"
systemctl daemon-reload
systemctl enable micro-ros-agent.service
# robot.service 暂时不默认启用, 调试阶段手动拉:
#   sudo systemctl start robot.service
#   sudo systemctl enable robot.service   # 比赛当天前开

echo
echo "完成. 管理命令:"
echo "  sudo systemctl status micro-ros-agent    # 看状态"
echo "  sudo systemctl start robot               # 手动拉起整机"
echo "  sudo systemctl enable robot              # 开机自启"
echo "  sudo journalctl -u micro-ros-agent -f    # 看日志"
echo
echo "拔 ESP32 和 LiDAR 重插后验证固定路径:"
echo "  ls -l /dev/esp32 /dev/lidar"
