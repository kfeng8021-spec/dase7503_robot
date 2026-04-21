# 布线 / 接线图

## 总体示意
```
┌─ 7.4V 9900mAh 锂电池
│
├──► 电源开关 (钥匙拨轮)
│
├──► 降压模块 5V 5A ──► Raspberry Pi 5 USB-C (27W)
│
├──► 降压模块 6V 3A ──► MG996 Servo (GPIO 控制线单独走)
│
└──► 直通 7.4V ──► 310 电机 ×4 (通过 ESP32 板上 H 桥)

ESP32-S3 板 (Yahboom MicroROS-Board):
├── USB Type-C ──► Pi5 USB (电源 + 串口)
├── GPIO (4,5,15,16,9,10,13,14)  PWM + DIR → 电机驱动
├── GPIO (6,47,7,48,11,12,1,2)   编码器 A/B 信号回读
├── GPIO 8  ──► MG996 Servo PWM 信号线
└── ADC 某脚 ──► 分压电阻 ──► 电池正极 (监控电压)

Pi5:
├── USB 口 1 ──► ESP32 Type-C
├── USB 口 2 ──► MS200 LiDAR (USB-Serial)
├── CAM0 CSI ──► Pi Camera Module 3
├── GPIO 40 pin (大多不用) -- 可选 蜂鸣器 / 急停按钮
└── HDMI ──► (比赛不插, 调试时接显示器)
```

## ESP32 GPIO 详细表

来自 Yahboom MicroROS-Board 官方文档.

| 功能 | 引脚 |
|---|---|
| **Motor 1 (FL)** | PWM=GPIO4, DIR=GPIO5, ENC_A=GPIO6, ENC_B=GPIO7 |
| **Motor 2 (FR)** | PWM=GPIO15, DIR=GPIO16, ENC_A=GPIO47, ENC_B=GPIO48 |
| **Motor 3 (RL)** | PWM=GPIO9, DIR=GPIO10, ENC_A=GPIO11, ENC_B=GPIO12 |
| **Motor 4 (RR)** | PWM=GPIO13, DIR=GPIO14, ENC_A=GPIO1, ENC_B=GPIO2 |
| **Servo S1** (升降叉) | GPIO8 PWM |
| **Servo S2** (备用) | GPIO21 |
| 电池电压采样 | ADC1_CH0 = GPIO1 (跟 Motor4 ENC_A 冲突, 用 GPIO3 替换) |

⚠️ **GPIO1 冲突警告**: Yahboom 官方把 Motor4 ENC_A 分到 GPIO1, 但 GPIO1 在 ESP32-S3 也是 ADC1_CH0. 如果要读电压得挪到 GPIO3 或其他 ADC 引脚, 固件代码里对应修改.

## 电机驱动线缆 (⚠️ 别接反)

每个 310 电机有 **6 根线** (编码器集成):
- 红线: +6-12V 电源 (黑线是 GND)
- **白色接头插控制板电机接口** (M1-M4)
- **黑色接头插电机本体**
- 接反会烧控制板!

编码器 4 根信号线接到 ENC_A, ENC_B, VCC(3.3V), GND.

## Mecanum 轮装配方向

四轮辊子必须成 **X 形**, 否则 y 轴移动方向反:

```
      前 (forward)
      │
  FL ╱ │ ╲ FR      # 左前 /, 右前 \
     │ │ │
  RL ╲ │ ╱ RR      # 左后 \, 右后 /
      │
      后
```

验证: 发 `vx=0.1, vy=0, wz=0` → 机器人前进
发 `vx=0, vy=0.1, wz=0` → 机器人向左平移
方向反立即停掉重新检查.

## USB 口固定绑定

RPi5 有 4 个 USB 口 (2×USB 3.0 蓝, 2×USB 2.0 黑). 推荐接法:

| USB 口 | 设备 | udev 别名 |
|---|---|---|
| USB 3.0 (1) | **MS200 LiDAR** (要带宽) | /dev/lidar |
| USB 3.0 (2) | U 盘 (导出日志用) | - |
| USB 2.0 (1) | **ESP32** (串口够用) | /dev/esp32 |
| USB 2.0 (2) | 键盘 / 备用 | - |

用 `99-robot-devices.rules` (见 `rpi5_setup/udev/`) 绑定别名, 不受插入顺序影响.

## 急停按钮 (可选, 推荐)

2 线按钮接 GPIO 某脚 + GND, 开启 INPUT_PULLUP, 按下 = LOW → 触发:
1. Pi5 上 `ros2 topic pub /cmd_vel Twist "{}"` 发零速
2. ESP32 上监听 GPIO 中断立即 `analogWrite(PWM_PIN[*], 0)`

## 电池管理 tips

- **充电**: 专用平衡充, 不能快充. 充满 8.4V, 指示灯变绿.
- **存放**: 长期不用放电到 7.4V 存放 (满电存放会涨肚)
- **短路保护**: 电池正负极之间串 15A 保险丝
- **发热**: 电机堵转瞬间可能拉几安培, 如果线径 < 18AWG 会烫, 建议 16AWG

## 走线美观 (评分项: Aesthetics)

- 电源线 + 信号线**分层走** (电源下, 信号上)
- 用扎带 + 线槽, 不要胶带
- USB 线多余的部分盘起来, 不要悬空挂着
- 标签机标出每根线 (M1-PWM / M1-DIR / ENC ...)
