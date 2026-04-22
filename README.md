# DASE7503 Smart Logistics Robot

双板架构物流机器人: **Raspberry Pi 5 (ROS 2 Jazzy) + ESP32-S3 (micro-ROS)** + Mecanum 全向底盘 + 升降机构.

3 分钟内 (新版 8 分钟) 在 3m×2m 赛场扫 START → 扫货架 QR → 升叉 → 搬到目的区 → 放下 → 循环 4 次.

**Deadline**: 2026-04-27 (Mon) · [Game field spec](docs/game_field.md) · [Wiring](docs/wiring.md) · [PID tuning](docs/pid_tuning.md)

---

## 快速开始

### Pi5 上首次部署 (Ubuntu 24.04)
```bash
cd ~
git clone https://github.com/kfeng8021-spec/dase7503_robot.git
cd dase7503_robot/rpi5_setup
sudo bash install.sh
sudo reboot   # 让 camera overlay 生效
```

### ESP32 烧录
用 Arduino IDE 打开 `firmware/esp32/micro_ros_motor_control/micro_ros_motor_control.ino`,
按 [`firmware/esp32/README.md`](firmware/esp32/README.md) 步骤烧录.

### 验收测试 (按顺序)
```bash
# 1. 电机 PID 验收
python3 scripts/test_motor_straight.py

# 2. QR 识别矩阵 (0.3m 正面 ≥ 95%)
python3 scripts/test_qr_matrix.py

# 3. LiDAR 验收
ros2 launch oradar_lidar ms200_scan.launch.py
ros2 topic hz /scan   # 应 10-15 Hz

# 4. 相机标定
ros2 launch our_robot calibration.launch.py
ros2 run camera_calibration cameracalibrator --size 8x6 --square 0.030 image:=/camera/image_raw camera:=/camera

# 5. SLAM 建图 (赛场必做)
ros2 launch our_robot slam_mapping.launch.py
# 另一终端: ros2 run teleop_twist_keyboard teleop_twist_keyboard
bash scripts/save_map.sh

# 6. 比赛启动
ros2 launch our_robot robot_full.launch.py
```

---

## 仓库结构

```
docs/
├── game_field.md                    # 赛场尺寸 + QR 布置
├── wiring.md                        # 电路 / GPIO / 布线
├── pid_tuning.md                    # PID 调参流程
├── deployment_notes.md              # 时间线 + SOP + 测试验收标准
└── *.pdf                            # 官方项目文档归档

firmware/esp32/
├── README.md                        # Arduino 烧录教程
└── micro_ros_motor_control/
    └── micro_ros_motor_control.ino  # Mecanum + PID + 编码器 + 电池监控

ros_pkg/our_robot/                   # Pi5 主 ROS 包
├── package.xml, setup.py
├── urdf/
│   └── robot.urdf.xacro             # TF 树
├── our_robot/
│   ├── mission_fsm_node.py          # 主 FSM + QR 时间戳 CSV
│   ├── qr_scanner_node.py           # pyzbar + CLAHE
│   ├── manual_mission_node.py       # B range 手动模式 FSM
│   ├── battery_monitor_node.py      # 低电量告警
│   └── odom_tf_broadcaster.py       # odom -> base_footprint TF
├── launch/
│   ├── robot_full.launch.py         # 比赛一键启动
│   ├── robot_manual.launch.py       # B range 手动启动
│   ├── slam_mapping.launch.py       # 赛前 SLAM 建图
│   ├── teleop_mode.launch.py        # 简化手动模式
│   └── calibration.launch.py        # 相机标定
└── config/
    ├── nav2_params.yaml             # Nav2 调参 (OmniMotionModel)
    ├── slam_toolbox_params.yaml     # SLAM 参数
    └── robot_view.rviz              # RViz2 预设视图

rpi5_setup/
├── install.sh                       # ROS 2 Jazzy 全栈一键装
├── install_systemd.sh               # systemd 服务 + udev 规则
├── systemd/
│   ├── micro-ros-agent.service      # 开机拉 agent
│   └── robot.service                # 开机拉整机
└── udev/
    └── 99-robot-devices.rules       # /dev/esp32, /dev/lidar 绑定

scripts/
├── qr_generate.py                   # QR 码生成器
├── qr_codes/                        # ⭐ 6 张 PNG (队伍串 4X6M, 可打印)
├── qr_test_local.py                 # PC 本地摄像头 QR 测试
├── test_motor_straight.py           # 电机 PID 验收
├── test_qr_matrix.py                # QR 识别率矩阵
├── start_robot_tmux.sh              # tmux 6 窗口调试模式
├── save_map.sh                      # SLAM 地图保存
└── deploy_to_pi5.sh                 # PC → Pi5 rsync
```

---

## ROS 2 话题通信

| 话题 | 类型 | 发布方 | 订阅方 |
|---|---|---|---|
| `/cmd_vel` | geometry_msgs/Twist | Nav2 / teleop / FSM | ESP32 |
| `/lifter_cmd` | std_msgs/Int32 | Mission FSM | ESP32 |
| `/wheel_odom` | nav_msgs/Odometry | ESP32 | tf2 → Nav2 |
| `/battery_voltage` | std_msgs/Float32 | ESP32 | battery_monitor |
| `/battery_alert` | std_msgs/String | battery_monitor | - |
| `/scan` | sensor_msgs/LaserScan | LiDAR driver | SLAM / Nav2 |
| `/camera/image_raw` | sensor_msgs/Image | camera_ros | qr_scanner |
| `/qr_result` | std_msgs/String | qr_scanner | mission_fsm |
| `/map` | nav_msgs/OccupancyGrid | SLAM / map_server | Nav2 |
| `/tf` | tf2_msgs/TFMessage | 各节点 | 全局 |

---

## 团队分工

| 模块 | 负责内容 | 关键文件 |
|---|---|---|
| **A — 机械** | 底盘 / 升降 / Mecanum 装配 | SolidWorks CAD |
| **B — ESP32** | micro-ROS 固件 / PID | `firmware/esp32/` |
| **C — 视觉** | 相机标定 / QR | `ros_pkg/.../qr_scanner_node.py` |
| **D — LiDAR/导航** | SLAM / Nav2 参数 / 地图 | `config/nav2_params.yaml`, `slam_toolbox_params.yaml` |
| **集成/FSM** | 状态机 / 联调 | `mission_fsm_node.py` |

---

## 重要提醒

### 队伍 QR 串改名
当前用 **`4X6M`** 是占位符. 队伍选定 4 位串后:
```bash
# 1. 改 ros_pkg/our_robot/our_robot/rack_positions.py 的 TEAM_CODE = "XXXX"
# 2. 清掉旧 PNG 避免混淆
rm -f scripts/qr_codes/RACK*.png
# 3. 重新生成 + 打印
python3 scripts/qr_generate.py --team XXXX --out scripts/qr_codes
git add -A && git commit -m "Update team code to XXXX" && git push
```

### 货架坐标必须校验
`rack_positions.py` 的 `RACK_POSITIONS` 是 Full Plan 给的估计值. **SLAM 建图后用卷尺量实际位置修正**, 误差 > 5cm 导航会找不到货架.

### 波特率 115200 必须一致
- ESP32 `Serial.begin(115200)`
- micro-ros-agent `-b 115200`
- 改了一边另一边必跟

### USB 端口 (udev 绑定强烈推荐)

`/dev/ttyUSB0/1` 顺序不固定, 重启可能互换导致 micro-ros-agent 打不开 ESP32. 装 udev 规则后, launch 文件默认用 `/dev/esp32` 固定路径.

**一次性安装流程**:
```bash
# 1. 插上 ESP32 + LiDAR, 查它们的 VID/PID
udevadm info -a -n /dev/ttyUSB0 | grep -E "idVendor|idProduct" | head -2
udevadm info -a -n /dev/ttyUSB1 | grep -E "idVendor|idProduct" | head -2

# 2. 按实际值改 rpi5_setup/udev/99-robot-devices.rules
#    (Yahboom ESP32-S3 默认 CH340 = 1a86:7523, MS200 LiDAR 默认 CP210x = 10c4:ea60)

# 3. 装规则 (rpi5_setup/install_systemd.sh 会自动做这步)
sudo cp rpi5_setup/udev/99-robot-devices.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger

# 4. 拔插验证
ls -l /dev/esp32 /dev/lidar   # 应看到 -> ttyUSB0/1 的 symlink
```

**如果没装 udev** (回退到 `/dev/ttyUSB0`):
```bash
ros2 launch our_robot robot_full.launch.py esp_dev:=/dev/ttyUSB0
```

### QR 时间戳 CSV 交付物 (新版赛规)

FSM 每次扫到 QR 记录到:
```
~/qr_logs/qr_scan_log_<YYYYMMDD_HHMMSS>.csv   # 自动模式 (mission_fsm_node)
~/qr_logs/manual_qr_log_<YYYYMMDD_HHMMSS>.csv # B-range 手动模式 (manual_mission_node)
```

比赛结束 **立刻** 从 Pi5 拷出来备份:
```bash
# 从另一台电脑
scp pi@<pi5-ip>:~/qr_logs/qr_scan_log_*.csv ./submission/
```

### YOLO 可选加分项 (不上比赛)

`robot_full.launch.py` **默认不启动** `yolo_detector_node`. YOLO 是演讲加分项, 需要时手动起:
```bash
ros2 run our_robot yolo_detector_node
# 看检测结果: ros2 topic echo /yolo/detections/compressed (用 rqt_image_view)
```

模型已在 `ros_pkg/our_robot/models/yolov8n.onnx`. `install.sh` 会自动 pip 装 `onnxruntime` + `numpy==1.26.4`, 或手动:
```bash
pip3 install --break-system-packages --user -r requirements.txt
```

---

## Deadline

- **2026-04-27 Monday 17:00**: 实物机器人 → HW 103A (Mr. Derek Tong / Mr. Mark Wan)
- **2026-04-27 Monday 23:59**: CAD + 代码 → Moodle
