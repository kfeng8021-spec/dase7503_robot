#!/usr/bin/env bash
# RPi5 Ubuntu 24.04 一键部署 ROS 2 Jazzy + micro-ros-agent + camera_ros + lidar + nav2
# 按 Full Plan + Camera setup PDF + Yahboom 官方文档整合.
#
# 用法 (Pi5 上):
#   cd ~/dase7503_robot/rpi5_setup
#   sudo bash install.sh

set -e
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
WS="$REAL_HOME/ros2_ws"

log() { echo -e "\n\e[32m[INSTALL]\e[0m $*"; }
die() { echo -e "\n\e[31m[ERROR]\e[0m $*"; exit 1; }

[ "$(id -u)" -eq 0 ] || die "sudo 跑: sudo bash install.sh"
grep -q "Ubuntu 24.04" /etc/os-release || die "只支持 Ubuntu 24.04"

# ---------- 1. Camera Module 3 overlay ----------
log "配置 Camera Module 3 overlay (需要重启)"
CFG=/boot/firmware/config.txt
cp -a "$CFG" "${CFG}.bak.$(date +%s)"
if grep -q "^camera_auto_detect" "$CFG"; then
  sed -i 's/^camera_auto_detect=.*/camera_auto_detect=0/' "$CFG"
else
  echo "camera_auto_detect=0" >> "$CFG"
fi
grep -q "^dtoverlay=imx708" "$CFG" || echo "dtoverlay=imx708,cam0" >> "$CFG"

# ---------- 2. 基础 apt 包 ----------
log "apt update + 基础工具"
apt update
apt install -y curl gnupg lsb-release software-properties-common \
  git python3-pip python3-colcon-common-extensions python3-colcon-meson \
  python3-ply python3-rosdep python3-pyzbar python3-opencv \
  libzbar0 libcamera-dev libcamera-tools build-essential tmux \
  ros-dev-tools 2>/dev/null || true

# ---------- 3. ROS 2 Jazzy apt 源 ----------
if ! dpkg -l ros-jazzy-ros-base >/dev/null 2>&1; then
  log "添加 ROS 2 apt 源 (Tutorial 1 教的新版 ros-apt-source 方法)"
  add-apt-repository -y universe

  # 新方法: 装 ros-apt-source .deb 包, 自动维护 GPG key 和 source list
  # 老方法 (curl ros.key + 手写 sources.list.d) 仍可用但被 ROS infra 淘汰
  ROS_APT_SOURCE_VERSION=$(curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest | grep -F "tag_name" | awk -F\" '{print $4}')
  UBUNTU_CODENAME=$(. /etc/os-release && echo $VERSION_CODENAME)
  curl -L -o /tmp/ros2-apt-source.deb \
    "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.${UBUNTU_CODENAME}_all.deb"
  apt install -y /tmp/ros2-apt-source.deb
  apt update

  log "装 ROS 2 Jazzy desktop (有 RViz/rqt GUI, Tutorial 1/6 都用 desktop 版)"
  apt install -y ros-jazzy-desktop ros-jazzy-ros-base ros-jazzy-rmw-cyclonedds-cpp
fi

# ---------- 4. micro-ros-agent + nav2 + slam-toolbox ----------
log "装 micro-ros-agent + nav2 + slam-toolbox + image_transport (tutorial 7 要的压缩图)"
apt install -y \
  ros-jazzy-micro-ros-agent \
  ros-jazzy-nav2-bringup \
  ros-jazzy-slam-toolbox \
  ros-jazzy-teleop-twist-keyboard \
  ros-jazzy-rqt-image-view \
  ros-jazzy-cv-bridge \
  ros-jazzy-vision-opencv \
  ros-jazzy-image-transport \
  ros-jazzy-image-transport-plugins \
  ros-jazzy-compressed-image-transport \
  ros-jazzy-xacro

# ---------- 5. 权限 ----------
log "加入 dialout (串口) + video (摄像头) 组"
usermod -aG dialout,video "$REAL_USER"

# ---------- 6. rosdep ----------
if [ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]; then
  log "rosdep init"
  rosdep init
fi
sudo -u "$REAL_USER" rosdep update

# ---------- 7. 用户 bashrc ----------
log "写 ~/.bashrc"
sudo -u "$REAL_USER" bash -c "
  grep -q 'source /opt/ros/jazzy/setup.bash' $REAL_HOME/.bashrc || \
    echo 'source /opt/ros/jazzy/setup.bash' >> $REAL_HOME/.bashrc
  grep -q 'RMW_IMPLEMENTATION' $REAL_HOME/.bashrc || \
    echo 'export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp' >> $REAL_HOME/.bashrc
  grep -q 'ROS_DOMAIN_ID' $REAL_HOME/.bashrc || \
    echo 'export ROS_DOMAIN_ID=0' >> $REAL_HOME/.bashrc
"

# ---------- 8. 工作区 + 源码编译包 ----------
log "创建 ros2_ws 并 clone libcamera + camera_ros + ydlidar_ros2_driver"
sudo -u "$REAL_USER" mkdir -p "$WS/src"
cd "$WS/src"
[ ! -d libcamera ] && sudo -u "$REAL_USER" git clone --depth 1 https://github.com/raspberrypi/libcamera.git
[ ! -d camera_ros ] && sudo -u "$REAL_USER" git clone --depth 1 https://github.com/christianrauch/camera_ros.git
[ ! -d ydlidar_ros2_driver ] && sudo -u "$REAL_USER" git clone --depth 1 https://github.com/YDLIDAR/ydlidar_ros2_driver.git

# 符号链接我们自己的 our_robot 包
if [ -d "$REAL_HOME/dase7503_robot/ros_pkg/our_robot" ] && [ ! -L "$WS/src/our_robot" ]; then
  sudo -u "$REAL_USER" ln -s "$REAL_HOME/dase7503_robot/ros_pkg/our_robot" "$WS/src/our_robot"
fi

log "编译 (30+ 分钟, Pi5 上限 2 核并行防过热)"
sudo -u "$REAL_USER" bash -c "
  source /opt/ros/jazzy/setup.bash
  cd '$WS'
  rosdep install -y --from-paths src --ignore-src --rosdistro jazzy --skip-keys=libcamera
  MAKEFLAGS='-j2' colcon build --parallel-workers 2 --event-handlers console_direct+
"

# Workaround: setuptools 68 + colcon-ros 0.5 在 Ubuntu 24.04 上把 ament_python
# 的 console_scripts 装到 install/our_robot/bin/ 而非 lib/our_robot/,
# 导致 ros2 run 找不到节点. symlink 补回来.
log "修补 our_robot 节点位置 (bin -> lib/our_robot)"
sudo -u "$REAL_USER" bash -c "
  BIN='$WS/install/our_robot/bin'
  LIB='$WS/install/our_robot/lib/our_robot'
  if [ -d \"\$BIN\" ]; then
    mkdir -p \"\$LIB\"
    for f in \"\$BIN\"/*; do
      [ -e \"\$f\" ] || continue
      ln -sf \"../../bin/\$(basename \"\$f\")\" \"\$LIB/\$(basename \"\$f\")\"
    done
  fi
"

# ---------- 9. workspace setup in bashrc ----------
sudo -u "$REAL_USER" bash -c "
  grep -q 'source $WS/install/setup.bash' $REAL_HOME/.bashrc || \
    echo 'source $WS/install/setup.bash' >> $REAL_HOME/.bashrc
"

# ---------- 10. systemd + udev (可选, 比赛前开启开机自启) ----------
log "安装 systemd 服务 + udev 规则 (不启用, 调试完后 systemctl enable)"
if [ -f "$(dirname "$0")/install_systemd.sh" ]; then
  bash "$(dirname "$0")/install_systemd.sh" || true
fi

# ---------- 11. Python 工具包 + YOLO onnxruntime (tutorial 7 加分项) ----------
log "pip 装 qrcode / pillow / onnxruntime / numpy (tutorial 7 指定版本)"
sudo -u "$REAL_USER" pip3 install --break-system-packages --user \
  qrcode pillow onnxruntime "numpy==1.26.4" || true

log "完成!  重启让 camera overlay 生效: sudo reboot"
log ""
log "重启后验证步骤:"
log "  1) ros2 topic list                    # 应看到基础话题"
log "  2) ros2 run camera_ros camera_node    # 应看到 /camera/image_raw"
log "  3) ros2 launch ydlidar_ros2_driver ydlidar_launch.py  # 应看到 /scan"
log "  4) 烧 ESP32 固件 (firmware/esp32/) 后: ros2 topic echo /wheel_odom"
log "  5) scripts/test_motor_straight.py     # 验证电机方向 + PID"
log "  6) 赛前 SLAM 建图: ros2 launch our_robot slam_mapping.launch.py"
log "  7) 比赛启动: ros2 launch our_robot robot_full.launch.py"
log ""
log "B range 手动模式: ros2 launch our_robot robot_manual.launch.py"
