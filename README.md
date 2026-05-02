# Autonomous Logistics Robot

双板架构物流机器人: **Raspberry Pi 5 (ROS 2 Jazzy) + ESP32-S3 (micro-ROS)** + Mecanum 全向底盘 + 升降机构.

3 分钟内 (新版 8 分钟) 在 3m×2m 赛场扫 START → 扫货架 QR → 升叉 → 搬到目的区 → 放下 → 循环 4 次.

**Deadline**: 2026-04-27 (Mon) · [Game field spec](docs/game_field.md) · [Wiring](docs/wiring.md) · [PID tuning](docs/pid_tuning.md)

**Demo / Submission Materials**: [Google Drive folder](https://drive.google.com/drive/folders/1jJu_jJcTyburXDEJXnJ0v87mApNDu1qE?usp=sharing) · [Field.mp4](https://drive.google.com/file/d/1Um9JuQaaRrmgw0-fhiDYiSQS8zMbOaa8/view?usp=sharing) · [QRScan&Time.mp4](https://drive.google.com/file/d/18qLlR4JD5wtBqxEszsLlZKlroklsS2be/view?usp=sharing) · [Presentation](https://drive.google.com/file/d/1C4D9pZIuZg_dDBKVw3HzxvJLAhAreFF4/view?usp=sharing) · [CAD archive](https://drive.google.com/file/d/1k36CBbZSns01qzZIZNJbJJtI8B1uHejJ/view?usp=sharing)

---

## 快速开始

### Pi5 上首次部署 (Ubuntu 24.04)
```bash
cd ~
git clone https://github.com/kfeng8021-spec/autonomous-logistics-robot.git
cd autonomous-logistics-robot/rpi5_setup
sudo bash install.sh
sudo reboot   # 让 camera overlay 生效
```

### ESP32 烧录 (Yahboom 工厂固件)
2026-04-24 起切到 Yahboom 官方 **microROS_Robot V2.0.0** 二进制固件 (原来的 `firmware/esp32_pio/` 团队自编因 4/22 runaway 事故弃用). 刷法:
```bash
# 在 Pi5 上
sudo systemctl stop micro-ros-agent
python3 ~/.platformio/packages/tool-esptoolpy/esptool.py \
  --chip esp32s3 --port /dev/ttyUSB0 --baud 921600 \
  --before default_reset --after hard_reset \
  write_flash -z --flash_mode dio --flash_freq 80m --flash_size 4MB \
  0x0 ~/factory_fw/microROS_Robot_V2.0.0.bin
```
固件默认: `SERIAL_BAUDRATE=921600`, `ROS_DOMAIN_ID=20`, CAR_TYPE_RPI5(串口,非 WiFi). 刷完**必须** MCU 主电源 ON 才会起 micro-ROS.

### 验收测试 (按顺序)
```bash
# 1. 电机 PID 验收
python3 scripts/test_motor_straight.py

# 2. QR 识别矩阵 (0.3m 正面 ≥ 95%)
python3 scripts/test_qr_matrix.py

# 3. LiDAR 验收 (MS200 通过 Pi5 USB, /dev/lidar symlink)
ros2 launch oradar_lidar ms200_scan.launch.py
ros2 topic hz /scan   # ⚠️ 此处的 /scan 是 oradar 原生默认, 和 ESP32 的 /scan 冲突.
                      # 正式用我们的 launch 时 oradar 发 /scan_lidar (见下). 这里只是单独测驱动.

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
│   ├── yolo_detector_node.py        # YOLOv8n ONNX 检测 (Tutorial 7 加分项)
│   ├── laser_safety_node.py         # teleop 避障 gate (cmd_vel_raw + scan_lidar → cmd_vel)
│   └── odom_tf_broadcaster.py       # odom -> base_footprint TF (订 /odom_raw)
├── launch/
│   ├── robot_full.launch.py         # 比赛一键启动 (LiDAR + camera + QR + YOLO + Nav2 + FSM)
│   ├── robot_manual.launch.py       # B range 手动启动
│   ├── slam_mapping.launch.py       # 赛前 SLAM 建图
│   ├── teleop_avoid.launch.py       # 遥控 + LiDAR 避障 (第三种模式, 非原方案)
│   ├── teleop_mode.launch.py        # 简化手动模式 (裸遥控无避障)
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

切到 Yahboom 工厂固件后话题命名换了, 以下是**最新真实值**:

| 话题 | 类型 | 发布方 | 订阅方 |
|---|---|---|---|
| `/cmd_vel` | geometry_msgs/Twist | Nav2 / laser_safety_gate / FSM | ESP32 (factory FW) |
| `/cmd_vel_raw` | geometry_msgs/Twist | teleop_twist_keyboard (remap) | laser_safety_gate |
| `/odom_raw` | nav_msgs/Odometry | ESP32 (11 Hz) | odom_tf_broadcaster |
| `/servo_s2` | std_msgs/Int32 (-90..20) | Mission FSM | ESP32 (= 原 /lifter_cmd) |
| `/servo_s1` | std_msgs/Int32 (-90..90) | - (未用) | ESP32 |
| `/battery` | std_msgs/UInt16 (data÷10 = V) | ESP32 (1 Hz) | battery_monitor |
| `/imu` | sensor_msgs/Imu | ESP32 (25 Hz) | - |
| `/scan` | sensor_msgs/LaserScan | **ESP32 (空数据, 板上 LiDAR 口空)** | - 忽略 |
| `/scan_lidar` | sensor_msgs/LaserScan | oradar_lidar (10 Hz) | SLAM / Nav2 / laser_safety_gate |
| `/beep` | std_msgs/UInt16 | (未用) | ESP32 |
| `/camera/image_raw/compressed` | sensor_msgs/CompressedImage | camera_ros | qr_scanner + yolo_detector |
| `/qr_result` | std_msgs/String | qr_scanner | mission_fsm |
| `/yolo/detections/compressed` | sensor_msgs/CompressedImage | yolo_detector | (rqt_image_view 可视化) |
| `/map` | nav_msgs/OccupancyGrid | slam_toolbox | Nav2 |
| `/tf` | tf2_msgs/TFMessage | 各节点 | 全局 |

**重要**: `/scan` 和 `/scan_lidar` 是**两个不同的 topic**. ESP32 固件永远发 `/scan`, 板上 LiDAR 口没接则 ranges 全 0. 真 LiDAR 走 Pi5 USB → oradar_lidar → `/scan_lidar`. 下游一律订 `/scan_lidar`.

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

### 波特率 921600 必须一致 (工厂 FW 默认)
- ESP32 工厂 FW 硬编码 921600 (hardcoded, NVS erase 也改不了)
- `/etc/systemd/system/micro-ros-agent.service` 的 `-b 921600`
- `ROS_DOMAIN_ID=20` 也必须两边一致

如果重刷的是团队旧固件 (弃用) 则是 115200. 当前方案走工厂 FW.

### USB 端口 (udev 绑定强烈推荐)

`/dev/ttyUSB0/1` 顺序不固定, 重启可能互换导致 micro-ros-agent 打不开 ESP32. 装 udev 规则后, launch 文件默认用 `/dev/esp32` 固定路径.

**一次性安装流程**:
```bash
# 1. 插上 ESP32 + LiDAR, 查它们的 VID/PID
udevadm info -a -n /dev/ttyUSB0 | grep -E "idVendor|idProduct" | head -2
udevadm info -a -n /dev/ttyUSB1 | grep -E "idVendor|idProduct" | head -2

# 2. 按实际值改 rpi5_setup/udev/99-robot-devices.rules
#    (工厂 FW ESP32 = CP210x 10c4:ea60, MS200 LiDAR adapter = CH343 1a86:55d4)
#    ⚠️ 团队 PIO 固件用 CH340 1a86:7523, 但已弃用. 以工厂 FW 的 VID/PID 为准.

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

### YOLO 加分项 (已并入 robot_full)

2026-04-24 起 `robot_full.launch.py` **默认启动** `yolo_detector_node` (和 qr_scanner 共用 `/camera/image_raw/compressed`, 互不冲突). 检测结果发到 `/yolo/detections/compressed`.

单独测 YOLO (不起 Nav2):
```bash
ros2 run our_robot yolo_detector_node
# 可视化: ros2 run rqt_image_view rqt_image_view /yolo/detections/compressed
```

模型在 `ros_pkg/our_robot/models/yolov8n.onnx`. 依赖 `onnxruntime` + `opencv-python` (Pi5 已装, onnxruntime 1.24.4 验过).

如果不想跑 YOLO 省 CPU, 注释掉 `robot_full.launch.py` 里的 `yolo` Node 即可.

---

## Deadline

- **2026-04-27 Monday 17:00**: 实物机器人 → HW 103A (Mr. Derek Tong / Mr. Mark Wan)
- **2026-04-27 Monday 23:59**: CAD + 代码 → Moodle
