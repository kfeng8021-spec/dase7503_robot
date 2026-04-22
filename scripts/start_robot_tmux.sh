#!/usr/bin/env bash
# 一键 tmux 起所有节点 (调试用, 生产直接 systemctl start robot).
# 会开 6 个 pane:
#   0: agent     1: lidar       2: camera+qr
#   3: nav2_loc  4: nav2_nav    5: mission_fsm

set -e
SESSION="robot"

if tmux has-session -t $SESSION 2>/dev/null; then
  echo "Session $SESSION 已存在, 接上去: tmux attach -t $SESSION"
  exit 0
fi

MAP="${MAP:-$HOME/maps/gamefield_map.yaml}"
ESP_DEV="${ESP_DEV:-/dev/esp32}"   # udev 未装时 override: ESP_DEV=/dev/ttyUSB0 bash start_robot_tmux.sh

tmux new-session -d -s $SESSION -x 220 -y 50

# Pane 0: agent
tmux send-keys -t $SESSION "echo '=== micro-ROS Agent ===' && source /opt/ros/jazzy/setup.bash && \
  ros2 run micro_ros_agent micro_ros_agent serial --dev $ESP_DEV -b 115200" C-m

# Pane 1: lidar
tmux split-window -h -t $SESSION
tmux send-keys -t $SESSION 'echo "=== LiDAR ===" && source /opt/ros/jazzy/setup.bash && \
  source ~/ros2_ws/install/setup.bash && \
  ros2 launch oradar_lidar ms200_scan.launch.py' C-m

# Pane 2: camera + qr
tmux split-window -v -t $SESSION
tmux send-keys -t $SESSION 'echo "=== Camera + QR ===" && source /opt/ros/jazzy/setup.bash && \
  source ~/ros2_ws/install/setup.bash && \
  ros2 run camera_ros camera_node & \
  sleep 2; ros2 run our_robot qr_scanner_node' C-m

# Pane 3: nav2 localization
tmux select-pane -t $SESSION.0
tmux split-window -v -t $SESSION
tmux send-keys -t $SESSION "echo '=== Nav2 Localization ===' && source /opt/ros/jazzy/setup.bash && \
  source ~/ros2_ws/install/setup.bash && \
  ros2 launch nav2_bringup localization_launch.py map:=$MAP use_sim_time:=false" C-m

# Pane 4: nav2 navigation
tmux split-window -h -t $SESSION
tmux send-keys -t $SESSION 'echo "=== Nav2 Navigation ===" && source /opt/ros/jazzy/setup.bash && \
  source ~/ros2_ws/install/setup.bash && \
  ros2 launch nav2_bringup navigation_launch.py use_sim_time:=false' C-m

# Pane 5: mission FSM
tmux split-window -v -t $SESSION
tmux send-keys -t $SESSION 'echo "=== Mission FSM ===" && source /opt/ros/jazzy/setup.bash && \
  source ~/ros2_ws/install/setup.bash && \
  sleep 10 && \
  ros2 run our_robot mission_fsm_node' C-m

tmux select-layout -t $SESSION tiled
tmux attach -t $SESSION
