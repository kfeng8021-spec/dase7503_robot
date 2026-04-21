# PID 调参指南

ESP32 固件中四个电机独立 PID, 默认 `kp=8.0, ki=0.5, kd=0.1`. 实车可能需要微调.

## 调参顺序 (Ziegler-Nichols 简化版)

1. **I, D 归零** (`ki=0, kd=0`), 只调 P
2. 从 `kp=1.0` 开始, 逐步×2 (`1, 2, 4, 8, 16...`)
3. 发 `ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.1}}"`
4. 听电机声音 + 看 `ros2 topic echo /wheel_odom`:
   - 转速**爬不上** → kp 太小
   - 转速**震荡** → kp 太大 (临界 `Ku`)
   - 转速**平稳跟随** → 接近 `Ku/2`
5. 记下临界 `Ku` 和震荡周期 `Tu`
6. 经典 ZN 表:
   - P 控制: `kp = 0.5 * Ku`
   - PI 控制: `kp = 0.45 * Ku`, `ki = 1.2 * kp / Tu`
   - PID: `kp = 0.6 * Ku`, `ki = 2 * kp / Tu`, `kd = kp * Tu / 8`

## 典型症状 + 对策

| 症状 | 原因 | 调法 |
|---|---|---|
| 前进偏左/右 | 左右轮速不对称 | 两侧 `kp` 分别调, 误差 < 5% |
| 启停时震荡 | `kp` 太高 | `kp` ÷ 2, 加 `kd` |
| 目标速度追不上 | `kp` 或 `ki` 太小 | 先加 `kp`, 还不够加 `ki` |
| 低速抖动 | `ki` 积分饱和 | 缩小 `integral` 限幅 (当前 ±100) |
| 电机嘶嘶响 | PWM 频率不对 | ESP32 默认 `analogWrite` 5kHz, 改成 20kHz 可消噪 |

## 进阶: 前馈 + 反馈

仅 PID 反馈对摩擦 / 死区不敏感, 可加静态前馈:

```cpp
float ffwd = 0.3f * fabs(setpoint);  // 静摩擦补偿
float u = pid.compute(setpoint, measured, dt) + copysign(ffwd, setpoint);
```

## 单轮台架调参 (最佳实践, 但没时间可跳过)

理想流程:
1. 机器人翻过来, 轮子悬空
2. 单独启动一个电机, 固定 PWM 测稳态转速 (建 setpoint→RPM 映射表)
3. 从表中选几个工作点测响应曲线, 拟合一阶模型
4. 在 MATLAB/Python `scipy.signal.place_poles` 算 PID 参数
5. 烧回 ESP32 微调

## 验收标准 (Full Plan Week 1)

- 四轮速度误差 < 5% (发 1m/s, 每轮转速 RPM 差 < 5%)
- `scripts/test_motor_straight.py` 三个 OK 全通过
