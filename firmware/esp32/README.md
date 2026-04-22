# ESP32-S3 micro-ROS 固件

## 烧录步骤

1. **装 Arduino IDE 2.x** (arduino.cc/en/software)
2. **装 ESP32 Arduino Core v2.0.17** (Tutorial 3/4 老师指定)
   - File → Preferences → Additional Board URLs:
     `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
   - Boards Manager → 搜索 `esp32` → 安装 **`2.0.17`** (不是最新!)
   - 本固件的 LEDC API 用 v2.x 风格 (ledcSetup + ledcAttachPin + ledcWrite(channel, duty)),
     在 v2.0.17 和 v3.x 上都能编译
3. **装 micro_ros_arduino 库 (Jazzy 分支)**
   - 下载 zip: https://github.com/micro-ROS/micro_ros_arduino/releases/tag/v2.0.8-jazzy
     (注: v2.0.7 没发 jazzy 分支, 直接用 v2.0.8)
   - Arduino IDE: Sketch → Include Library → Add .ZIP Library → 选 zip
4. **装 ESP32Servo 库**
   - Library Manager → 搜 `ESP32Servo` by Kevin Harrington → 装
5. **连接板子**
   - Yahboom MicroROS-Board 的 Type-C → PC 或 Pi5 USB
   - Arduino IDE: Tools → Board → ESP32 Arduino → `ESP32S3 Dev Module`
   - Tools → Port → `/dev/ttyUSB0`（Linux）或 `COMx`（Windows）
6. **烧录**: 打开 `micro_ros_motor_control.ino` → Upload

## 验证

Pi5 上启动 agent (两种方式, 二选一):

**方式 A — 源码编译** (rpi5_setup/install.sh 做的, Jazzy apt 源没 agent 包):
```bash
# 在 ros2_ws 里 clone + colcon build 好了以后:
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/esp32 -b 115200
```

**方式 B — Docker** (省心, 不用 superbuild):
```bash
sudo usermod -aG dialout $USER   # 首次
docker run -it --rm -v /dev:/dev --privileged --net=host \
  microros/micro-ros-agent:jazzy serial --dev /dev/esp32 -v6
```

PC/Pi5 上验证:
```bash
ros2 node list         # 应该看到 /hku_dase_micro_ros_node (Tutorial 5 节点名)
ros2 topic list        # 应该看到 /cmd_vel /lifter_cmd /wheel_odom /battery_voltage /set_pid
ros2 topic echo /wheel_odom    # 应该有数据流
```

## 运行时调 PID (Tutorial 5 风格)

不用重新烧固件就能调参数:
```bash
# Kp=5.0, Ki=0.3, Kd=0.05
ros2 topic pub --once /set_pid std_msgs/msg/Float32MultiArray "{data: [5.0, 0.3, 0.05]}"

# 同时看 /wheel_odom 的 twist.linear.x 回响 (rqt_plot 可视化)
rqt_plot /wheel_odom/twist/twist/linear/x
```
四个电机共用同一组 PID 参数 (简单版).

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
