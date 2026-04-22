#!/usr/bin/env bash
# colcon build + setuptools 68/colcon-ros 0.5 workaround (symlink bin/ -> lib/our_robot/).
# 在 Ubuntu 24.04 上 ament_python 的 console_scripts 会装到 install/<pkg>/bin/
# 而 ros2 run 查找 install/<pkg>/lib/<pkg>/, 导致 "No executable found".
#
# 用法: 在 ~/ros2_ws 目录下运行 bash ~/dase7503_robot/scripts/build.sh

set -e
WS="${WS:-$HOME/ros2_ws}"
PKG="our_robot"

[ -d "$WS/src" ] || { echo "[BUILD] 找不到 $WS/src, 用 WS=/path/to/ws 覆盖"; exit 1; }

source /opt/ros/jazzy/setup.bash
cd "$WS"
colcon build --symlink-install --packages-select "$PKG"

# Patch: 把 install/$PKG/bin/ 里的脚本 symlink 到 install/$PKG/lib/$PKG/
BIN="$WS/install/$PKG/bin"
LIB="$WS/install/$PKG/lib/$PKG"
if [ -d "$BIN" ]; then
  mkdir -p "$LIB"
  for f in "$BIN"/*; do
    [ -e "$f" ] || continue
    ln -sf "../../bin/$(basename "$f")" "$LIB/$(basename "$f")"
  done
  echo "[BUILD] Patched $LIB -> $BIN ($(ls "$LIB" | wc -l) scripts)"
fi

echo "[BUILD] done. source install/setup.bash && ros2 pkg executables $PKG"
