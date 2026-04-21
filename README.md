# DASE7503 Smart Logistics Robot

双板架构物流机器人，Pi5 (ROS 2 Jazzy) + ESP32-S3 (micro-ROS)，Mecanum 全向底盘 + 升降机构。

## 任务
3 分钟内（新版 8 分钟）在 3m×2m 赛场扫 START → 扫货架 QR → 升叉 → 搬到目的区 → 放下 → 循环 4 次。

## 硬件
| 组件 | 型号 | 接口 |
|---|---|---|
| 主控 | Raspberry Pi 5 (8GB) | - |
| MCU | Yahboom ESP32-S3 MicroROS-Board | USB-Serial |
| LiDAR | MS200 360° | USB (`/dev/ttyUSB1`) |
| Camera | Pi Camera Module 3 (IMX708) | CSI (CAM0) |
| 电机 | 310 DC 编码器电机 ×4 | ESP32 PWM + 编码器 |
| 舵机 | MG996 | ESP32 GPIO8 PWM |
| 电池 | 7.4V 9900mAh | - |

## 仓库结构
```
docs/              # 项目文档、PDF
firmware/esp32/    # Arduino micro-ROS 固件
ros_pkg/our_robot/ # Pi5 上的 ROS 2 包（FSM, QR scanner, launch）
scripts/           # QR 生成、本地测试脚本
rpi5_setup/        # Pi5 初始化脚本
```

## 快速开始

### Pi5 首次部署
```bash
cd ~ && git clone https://github.com/kfeng8021-spec/dase7503_robot.git
cd dase7503_robot/rpi5_setup && sudo bash install.sh
```

### 比赛当天启动
```bash
tmux new -s robot
ros2 launch our_robot robot_full.launch.py
```

## 团队分工（模块）
- **A 机械**：底盘、升降机构、Mecanum 装配
- **B ESP32**：`firmware/esp32/`
- **C 视觉**：`ros_pkg/our_robot/our_robot/qr_scanner_node.py` + 相机标定
- **D LiDAR/导航**：`ros_pkg/our_robot/config/nav2_params.yaml` + SLAM 建图
- **Mission FSM**：`ros_pkg/our_robot/our_robot/mission_fsm_node.py`
- **商业/演讲**：PPT

## Deadline: **2026-04-27 (Mon)**
- 17:00 实物 → HW 103A (Mr. Derek Tong / Mr. Mark Wan)
- 23:59 CAD + 代码 + PPT → Moodle
