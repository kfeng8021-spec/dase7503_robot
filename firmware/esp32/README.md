# ESP32-S3 micro-ROS 固件

## 烧录步骤

1. **装 Arduino IDE 2.x** (arduino.cc/en/software)
2. **装 ESP32 Arduino Core**
   - File → Preferences → Additional Board URLs:
     `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
   - Boards Manager → 搜索 `esp32` → 安装 ESP32 3.0+
3. **装 micro_ros_arduino 库 (Jazzy 分支)**
   - 下载 zip: https://github.com/micro-ROS/micro_ros_arduino/releases/tag/v2.0.7-jazzy
   - Arduino IDE: Sketch → Include Library → Add .ZIP Library → 选 zip
4. **装 ESP32Servo 库**
   - Library Manager → 搜 `ESP32Servo` by Kevin Harrington → 装
5. **连接板子**
   - Yahboom MicroROS-Board 的 Type-C → PC 或 Pi5 USB
   - Arduino IDE: Tools → Board → ESP32 Arduino → `ESP32S3 Dev Module`
   - Tools → Port → `/dev/ttyUSB0`（Linux）或 `COMx`（Windows）
6. **烧录**: 打开 `micro_ros_motor_control.ino` → Upload

## 验证

Pi5 上启动 agent:
```bash
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyUSB0 -b 115200
```

PC/Pi5 上:
```bash
ros2 node list         # 应该看到 /micro_ros_node
ros2 topic list        # 应该看到 /cmd_vel /lifter_cmd /wheel_odom
ros2 topic echo /wheel_odom    # 应该有数据流
```

## 初调 PID

打开 Serial Monitor @ 115200 baud.
手动发 `/cmd_vel`:
```bash
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.1}}"
```
观察机器人是否直线前进 (四轮速度误差 < 5%)。
不平稳就调 `PID::kp/ki/kd`, 先把 `kp` 调到接近临界震荡再加阻尼。

## 常见坑

- **编码器方向反了** → 交换 `ENC_A` / `ENC_B` 引脚, 或在 ISR 里翻转符号
- **发 vx=0.1 机器人向后** → 交换 `PWM` 和 `DIR`, 或在 `set_motor_pwm` 里翻转
- **Mecanum 移动方向错** → 检查 Full Plan A4 表, 四个轮的 roller 必须是 X 形
