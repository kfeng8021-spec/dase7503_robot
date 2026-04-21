#!/usr/bin/env bash
# 从 PC 同步代码到 Pi5 的便捷脚本.
# 比 git pull 快, 开发迭代用.
#
# 用法:
#   scripts/deploy_to_pi5.sh                    # 默认 dase@dase-rpi5.local
#   scripts/deploy_to_pi5.sh dase@192.168.1.42  # 指定 user@host
#   PI=dase@192.168.1.42 scripts/deploy_to_pi5.sh

set -e
TARGET="${1:-${PI:-dase@dase-rpi5.local}}"
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "[DEPLOY] $SRC_DIR -> $TARGET:~/dase7503_robot/"
rsync -avz --delete \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'build' \
  --exclude 'install' \
  --exclude 'log' \
  --exclude 'scripts/qr_scan_log_*.csv' \
  "$SRC_DIR/" "$TARGET:~/dase7503_robot/"

echo
echo "[DEPLOY] done. 在 Pi5 上:"
echo "  cd ~/ros2_ws && colcon build --packages-select our_robot"
echo "  source install/setup.bash"
echo "  ros2 launch our_robot robot_full.launch.py"
