# 部署笔记

## 🗓️ 时间线 (今天 2026-04-20)

- **4/20-21**: 系统 + 网络 + ROS 栈全部装好
- **4/22**: ESP32 固件烧好, PID 调参, 四轮直线前进误差 < 5%
- **4/23**: Camera 标定 + QR 识别矩阵测试 (0.3m 识别率 ≥ 95%) + LiDAR `/scan` 正常
- **4/24**: 赛场 SLAM 建图保存 (`~/maps/gamefield_map.yaml`)
- **4/25**: Nav2 联调 + Mission FSM 单货架端到端跑通
- **4/26**: 全场 4 货架 3 分钟内连跑 + 压力测试
- **4/27 17:00**: 实物交 HW 103A; 23:59 Moodle

## 🌐 网络配置

### 场景 1: 实验室 WiFi / iPhone 热点
- Pi5 和 PC 在同一 WiFi, DDS 自动 discovery
- 需同 `ROS_DOMAIN_ID=0`
- PC 上 `ros2 topic list` 能看到 Pi5 的话题

### 场景 2: PC ↔ Pi5 直连 (网线)
- PC 网口 IP: `192.168.10.1/24`, Pi5 手动配 `192.168.10.2/24`
- 无需 WiFi, 延迟最低
- Pi5 上 `sudo nmtui` 配置静态 IP

### ProtonVPN 冲突绕过
PC 上加策略路由让本地子网绕过 VPN:
```bash
sudo ip rule add to 192.168.0.0/16 lookup main pref 100
sudo ip rule add to 172.20.0.0/16 lookup main pref 100
```

## 🔌 USB 设备分配

Pi5 同时插: Yahboom ESP32 + MS200 LiDAR 两个 USB Serial 设备.
默认 `/dev/ttyUSB0` 和 `/dev/ttyUSB1` 但**顺序不固定**, 重启后可能换.

解决方法: udev rule 按 USB VID/PID 绑定固定名字.

```bash
# /etc/udev/rules.d/99-robot.rules
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", SYMLINK+="esp32"
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", SYMLINK+="lidar"
```

然后代码里用 `/dev/esp32` 和 `/dev/lidar`, 不再怕 `/dev/ttyUSB*` 顺序乱.

先跑 `udevadm info -a -n /dev/ttyUSB0 | grep -E "idVendor|idProduct"` 确认 VID/PID.

## 🎥 相机标定

打印 `8x6` 棋盘格 (每格 30mm) 贴硬纸板:
```bash
ros2 run camera_ros camera_node &
ros2 run camera_calibration cameracalibrator \
  --size 8x6 --square 0.030 \
  image:=/camera/image_raw camera:=/camera
```
移动棋盘直到 x/y/size/skew 四条都亮绿 -> 点 CALIBRATE -> COMMIT.
结果存 `~/.ros/camera_info/camera.yaml`, camera_ros 下次启动自动加载.

## 🗺️ SLAM 建图 (赛场必做)

```bash
# 终端 1: 底盘节点
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/esp32 -b 115200

# 终端 2: LiDAR
ros2 launch ydlidar_ros2_driver ydlidar_launch.py

# 终端 3: SLAM
ros2 launch slam_toolbox online_async_launch.py use_sim_time:=false

# 终端 4: 遥控走
ros2 run teleop_twist_keyboard teleop_twist_keyboard

# 覆盖全场一遍后保存
ros2 run nav2_map_server map_saver_cli -f ~/maps/gamefield_map
# 生成 gamefield_map.yaml + gamefield_map.pgm
```

## 🧪 模块独立验收标准

| 模块 | 验收指标 |
|---|---|
| B (ESP32) | `vx=0.1` 机器人直线前进 15cm (实测尺), 偏差 < 5% |
| C (Camera) | 30cm 距离正面识别率 ≥ 95% (10 次 9 成功) |
| D (LiDAR) | `ros2 topic hz /scan` 10-15 Hz, 静止时 drift < 2cm/分钟 |
| Nav2 | 点到点 (0,0) → (1,1) 导航误差 < 5cm |
| 整机 | 单货架 START→pick→deliver 完整流程 90 秒内 |

## 🚨 比赛日 SOP

**赛前 30 分钟**:
1. 到场 → Pi5 上电 → tmux 开 6 窗口
2. 开 agent + LiDAR + camera + Nav2 + FSM
3. RViz2 看 AMCL 粒子云是否收敛 (几秒内粒子聚拢到一点)
4. 空载手动推一把, 看里程计是否累积正确
5. QR 扫一遍所有工位, 看 `/qr_result` 正常

**起跑前**:
- 电池电压 ≥ 7.4V (充电灯绿色)
- 场地坐标 vs `rack_positions.py` 对齐
- 升降机构到位 (叉臂水平, 垂直行程 15-20mm)

**跑完马上**:
- `cp ~/qr_logs/qr_scan_log_*.csv /media/usb/` 导出记录给老师
