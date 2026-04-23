/*
 * DASE7503 Robot - ESP32-S3 micro-ROS Motor + Lifter Control
 *
 * Yahboom MicroROS-Board (ESP32-S3) 固件:
 *   - 订阅 /cmd_vel   (geometry_msgs/Twist)       - 底盘运动
 *   - 订阅 /lifter_cmd (std_msgs/Int32)           - 0=下, 1=上
 *   - 发布 /wheel_odom (nav_msgs/Odometry @ 20Hz) - 编码器里程计
 *
 * 依赖 (Arduino 库管理器):
 *   - micro_ros_arduino (v2.0.7 jazzy 分支)
 *   - ESP32 Arduino Core 3.0+
 *
 * GPIO 分配 (来自 Yahboom 官方):
 *   Motor 1 FL: PWM=4,  DIR=5,  ENC_A=6,  ENC_B=7
 *   Motor 2 FR: PWM=15, DIR=16, ENC_A=47, ENC_B=48
 *   Motor 3 RL: PWM=9,  DIR=10, ENC_A=11, ENC_B=12
 *   Motor 4 RR: PWM=13, DIR=14, ENC_A=1,  ENC_B=2
 *   Lift Servo: GPIO8
 *
 * 物理参数 (Full Plan B3):
 *   轮径 65mm -> R=0.0325m
 *   左右轴距 220mm -> WB_X=0.110m
 *   前后轴距 220mm -> WB_Y=0.110m
 *   编码器 PPR=13, 减速比 1:20 -> 4倍频下 CPR=1040
 */

#include <Arduino.h>
#include <micro_ros_platformio.h>
#include <rcl/rcl.h>
#include <rcl/error_handling.h>
#include <rclc/rclc.h>
#include <rclc/executor.h>
#include <geometry_msgs/msg/twist.h>
#include <nav_msgs/msg/odometry.h>
#include <std_msgs/msg/int32.h>
#include <std_msgs/msg/float32.h>
#include <std_msgs/msg/float32_multi_array.h>
#include <std_msgs/msg/bool.h>
#include <ESP32Servo.h>

// ==================== 物理常量 ====================
#define WHEEL_RADIUS   0.0325f   // m
#define WHEEL_BASE_X   0.110f    // m, 左右轴距 / 2
#define WHEEL_BASE_Y   0.110f    // m, 前后轴距 / 2
#define PPR            13
#define GEAR_RATIO     20
// ENC_MULT: 编码器倍频
//   1 = 只在 A 的 RISING 触发中断 (代码当前做法, CPR=260) ← 默认, 省 CPU
//   2 = A 的 CHANGE (双边沿, CPR=520)
//   4 = A+B 都 CHANGE (正交解码, CPR=1040) ← 精度最高但中断频率高
#define ENC_MULT       2        // ISR 用 CHANGE 边沿 (Tutorial 5 风格) = 双边沿 × 1 引脚 = 2 倍频
#define ENC_CPR        (PPR * GEAR_RATIO * ENC_MULT)
#define M_TO_ENC       (ENC_CPR / (2 * PI * WHEEL_RADIUS))

// ==================== GPIO 分配 ====================
// 按 Yahboom MicroROS-Board (ESP32-S3) 官方引脚表.
// 注: 教学用的 ESP32 Dev Module 引脚不同 (Tutorial 5 用 AIN1=4/AIN2=15/STB=13/PWMA=5),
//     本项目直接按 Yahboom 实际板子走.
const int PWM_PIN[4] = {4,  15, 9,  13};
const int DIR_PIN[4] = {5,  16, 10, 14};
const int ENC_A[4]   = {6,  47, 11, 1};
const int ENC_B[4]   = {7,  48, 12, 2};
#define SERVO_PIN 8
// 电池电压采样: 7.4V 锂电池经 10k / 3.3k 分压到 ESP32 ADC 量程内
#define BATTERY_ADC_PIN 3      // GPIO3, ADC1_CH2 (避开 Motor4 ENC_A=GPIO1 冲突)
#define BATTERY_DIVIDER 4.03f  // (10k+3.3k)/3.3k 实测值, 需用万用表标定

// ==================== 状态 ====================
volatile long enc_count[4] = {0, 0, 0, 0};
float cmd_vx = 0, cmd_vy = 0, cmd_wz = 0;   // 目标
float target_rpm[4] = {0};                    // 四轮目标转速
long prev_enc[4] = {0};
unsigned long last_loop_ms = 0;

// cmd_vel watchdog + 启动宽限期保护机器不跑飞:
//   MOTOR_ARM_GRACE_MS: 启动后前 3s 强制 PWM=0, 让 encoder ISR 噪声稳定 + agent 建连
//   CMD_TIMEOUT_MS: 之后需持续收 cmd_vel (间隔 <500ms), 否则再次归零停车
// 事故教训 (2026-04-22): 旧版仅 "last_cmd_vel_ms > 0 且超时" 才归零, 启动时 watchdog
// 不生效, PID 对 encoder 噪声放大 → 电机失控. 新版默认=紧急停车, 必须显式 armed 才释放.
#define CMD_TIMEOUT_MS      500
#define MOTOR_ARM_GRACE_MS  3000
unsigned long last_cmd_vel_ms = 0;
unsigned long boot_time_ms = 0;

// ==================== 安全限幅 (bench test OK 后可放开) ====================
// 四层保护:
//   1. 输入层: cmd_vel 速度上限 (防止遥控/Nav2 发过大指令)
//   2. 运算层: target_rpm 上限 (防止 IK 计算出过大轮速)
//   3. 输出层: PWM 占空比上限 (防 PID 饱和冲过电机上限)
//   4. 急停: /emergency_stop Bool topic (pub true 立刻归零 + 锁)
// 实车调 PID 验收后可把 PWM_CAP 提到 255, MAX_TARGET_RPM 放宽.
#define MAX_LINEAR_VEL   0.20f   // m/s, 慢速 bench test 档 (Full Plan 目标 0.3, 先 2/3)
#define MAX_ANGULAR_VEL  1.0f    // rad/s
#define MAX_TARGET_RPM   80.0f   // 减速后输出端最大 80 RPM ≈ 0.27 m/s
#define PWM_CAP          180     // 0-255, 180 ≈ 70% duty

bool emergency_stop = false;

// 里程计累积
float pos_x = 0, pos_y = 0, theta = 0;

// Lifter
Servo lifter;
int lifter_state = 0;   // 0=down, 1=up

// ==================== PID ====================
struct PID {
  float kp = 8.0f, ki = 0.5f, kd = 0.1f;
  float integral = 0, prev_err = 0;
  float compute(float setpoint, float measured, float dt) {
    float e = setpoint - measured;
    integral += e * dt;
    integral = constrain(integral, -100.0f, 100.0f);
    float d = (e - prev_err) / dt;
    prev_err = e;
    return kp * e + ki * integral + kd * d;
  }
  void reset() { integral = 0; prev_err = 0; }
};
PID pid[4];

// ==================== micro-ROS 对象 ====================
rcl_subscription_t sub_cmd_vel, sub_lifter, sub_set_pid, sub_estop;
rcl_publisher_t pub_odom, pub_battery;
geometry_msgs__msg__Twist msg_cmd_vel;
std_msgs__msg__Int32 msg_lifter;
std_msgs__msg__Float32MultiArray msg_set_pid;
nav_msgs__msg__Odometry msg_odom;
std_msgs__msg__Float32 msg_battery;
rclc_executor_t executor;
rclc_support_t support;
rcl_allocator_t allocator;
rcl_node_t node;
rcl_timer_t odom_timer, battery_timer;

#define RCCHECK(fn) { rcl_ret_t rc = fn; if (rc != RCL_RET_OK) { error_loop(); } }
#define RCSOFTCHECK(fn) { rcl_ret_t rc = fn; (void)rc; }

void error_loop() {
  while (1) { digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN)); delay(100); }
}

// ==================== 编码器中断 ====================
// Tutorial 5 风格: CHANGE 边沿 + `A==B ? count++ : count--` 判向.
// 相比我之前的 RISING 边沿 ×1 倍频, CHANGE 边沿 ×2 倍频精度更高.
// 要对应把 ENC_MULT 改成 2.
void IRAM_ATTR enc_isr_0() {
  if (digitalRead(ENC_A[0]) == digitalRead(ENC_B[0])) enc_count[0]++; else enc_count[0]--;
}
void IRAM_ATTR enc_isr_1() {
  if (digitalRead(ENC_A[1]) == digitalRead(ENC_B[1])) enc_count[1]++; else enc_count[1]--;
}
void IRAM_ATTR enc_isr_2() {
  if (digitalRead(ENC_A[2]) == digitalRead(ENC_B[2])) enc_count[2]++; else enc_count[2]--;
}
void IRAM_ATTR enc_isr_3() {
  if (digitalRead(ENC_A[3]) == digitalRead(ENC_B[3])) enc_count[3]++; else enc_count[3]--;
}

// ==================== Mecanum 正/反运动学 ====================
// 正: (vx, vy, wz) -> (w_FL, w_FR, w_RL, w_RR) 单位 rad/s
void mecanum_ik(float vx, float vy, float wz, float *w) {
  float L = WHEEL_BASE_X + WHEEL_BASE_Y;
  w[0] = (vx - vy - L * wz) / WHEEL_RADIUS;   // FL
  w[1] = (vx + vy + L * wz) / WHEEL_RADIUS;   // FR
  w[2] = (vx + vy - L * wz) / WHEEL_RADIUS;   // RL
  w[3] = (vx - vy + L * wz) / WHEEL_RADIUS;   // RR
}
// 反: (w[4]) -> (vx, vy, wz)
void mecanum_fk(float *w, float &vx, float &vy, float &wz) {
  float R = WHEEL_RADIUS;
  float L = WHEEL_BASE_X + WHEEL_BASE_Y;
  vx = R / 4.0f * (w[0] + w[1] + w[2] + w[3]);
  vy = R / 4.0f * (-w[0] + w[1] + w[2] - w[3]);
  wz = R / (4.0f * L) * (-w[0] + w[1] - w[2] + w[3]);
}

// ==================== 电机驱动 (LEDC, 兼容 ESP32 Core 2.0.17 和 3.x) ====================
// 用 LEDC 硬件 PWM 而不是 analogWrite, 可配频率/分辨率, 消除 5kHz 嘶叫.
// 老师 Tutorial 3/4 明确指定 ESP32 Core v2.0.17, 所以这里用 v2.x API
// (ledcSetup + ledcAttachPin + ledcWrite(channel, duty)),
// 这组 API 在 v3.x 上仍然兼容 (只有 deprecation warning), 两版都能编.
#define PWM_FREQ   20000   // 20kHz, 超出人耳范围
#define PWM_RES    8       // 8-bit -> 0-255
#define LEDC_CH(i) (i)     // 四个电机各占一个 LEDC channel 0-3

void pwm_setup() {
  for (int i = 0; i < 4; i++) {
    ledcSetup(LEDC_CH(i), PWM_FREQ, PWM_RES);     // channel, freq, resolution
    ledcAttachPin(PWM_PIN[i], LEDC_CH(i));        // pin → channel
  }
}

void set_motor_pwm(int i, float pwm_val) {
  bool forward = pwm_val >= 0;
  digitalWrite(DIR_PIN[i], forward ? HIGH : LOW);
  int duty = constrain((int)fabs(pwm_val), 0, PWM_CAP);  // PWM 输出层硬限幅
  ledcWrite(LEDC_CH(i), duty);   // 写 channel 而不是 pin (v2.x API)
}

// ==================== 回调 ====================
void cmd_vel_cb(const void *msgin) {
  const geometry_msgs__msg__Twist *m = (const geometry_msgs__msg__Twist *) msgin;
  // 输入层 1: cmd_vel 速度硬限幅 (无视遥控/Nav2 可能发的大值)
  cmd_vx = constrain((float)m->linear.x,  -MAX_LINEAR_VEL,  MAX_LINEAR_VEL);
  cmd_vy = constrain((float)m->linear.y,  -MAX_LINEAR_VEL,  MAX_LINEAR_VEL);
  cmd_wz = constrain((float)m->angular.z, -MAX_ANGULAR_VEL, MAX_ANGULAR_VEL);
  float w[4];
  mecanum_ik(cmd_vx, cmd_vy, cmd_wz, w);
  // 运算层 2: target_rpm 硬限幅 (防 IK 算出的轮速超限)
  for (int i = 0; i < 4; i++) {
    float rpm = w[i] * 60.0f / (2 * PI);
    target_rpm[i] = constrain(rpm, -MAX_TARGET_RPM, MAX_TARGET_RPM);
  }
  last_cmd_vel_ms = millis();   // 喂 watchdog
}

// 急停订阅: pub true 立刻停车 + 锁死, pub false 解除
//   ros2 topic pub --once /emergency_stop std_msgs/msg/Bool "{data: true}"
void estop_cb(const void *msgin) {
  const std_msgs__msg__Bool *m = (const std_msgs__msg__Bool *) msgin;
  emergency_stop = m->data;
  if (emergency_stop) {
    for (int i = 0; i < 4; i++) {
      target_rpm[i] = 0;
      pid[i].reset();
      set_motor_pwm(i, 0);
    }
  }
}

void lifter_cb(const void *msgin) {
  const std_msgs__msg__Int32 *m = (const std_msgs__msg__Int32 *) msgin;
  lifter_state = m->data;
  lifter.write(lifter_state == 1 ? 180 : 0);  // 180°=抬起, 0°=放下
}

// /set_pid 订阅: 运行时调 Kp/Ki/Kd (Tutorial 5 教的, 实用!)
//   ros2 topic pub --once /set_pid std_msgs/msg/Float32MultiArray "{data: [8.0, 0.5, 0.1]}"
// 四个电机共用同一组 PID 参数 (简单够用)
void set_pid_cb(const void *msgin) {
  const std_msgs__msg__Float32MultiArray *m = (const std_msgs__msg__Float32MultiArray *) msgin;
  if (m->data.size >= 3) {
    for (int i = 0; i < 4; i++) {
      pid[i].kp = m->data.data[0];
      pid[i].ki = m->data.data[1];
      pid[i].kd = m->data.data[2];
      pid[i].reset();
    }
  }
}

void battery_timer_cb(rcl_timer_t *, int64_t) {
  // 每秒发一次电池电压
  int raw = analogRead(BATTERY_ADC_PIN);   // 0-4095 对应 0-3.3V
  float v_adc = raw * (3.3f / 4095.0f);
  float v_batt = v_adc * BATTERY_DIVIDER;
  msg_battery.data = v_batt;
  RCSOFTCHECK(rcl_publish(&pub_battery, &msg_battery, NULL));
}

void odom_timer_cb(rcl_timer_t *, int64_t) {
  // 每 50ms (20Hz) 计算并发布里程计
  unsigned long now = millis();
  float dt = (now - last_loop_ms) / 1000.0f;
  if (dt <= 0) return;
  last_loop_ms = now;

  float w_meas[4];  // 实测角速度 rad/s
  for (int i = 0; i < 4; i++) {
    long c = enc_count[i];
    long dc = c - prev_enc[i];
    prev_enc[i] = c;
    float rev = (float)dc / ENC_CPR;
    w_meas[i] = rev * 2 * PI / dt;
  }

  // SAFETY (启动宽限期 + cmd 新鲜度 + 急停三重保险, 任一不满足 → PWM=0 不跑 PID):
  //   ① 启动后 MOTOR_ARM_GRACE_MS 内强制停车 (等 encoder 稳定 + agent 建连)
  //   ② 从未收 cmd_vel 或上次 >CMD_TIMEOUT_MS 前 → 停车
  //   ③ /emergency_stop 话题 pub true → 停车 + 锁死 (直到 pub false)
  // 三项全满足才 armed, 跑闭环 PID.
  bool in_grace = (now - boot_time_ms) < MOTOR_ARM_GRACE_MS;
  bool cmd_fresh = (last_cmd_vel_ms > 0) && (now - last_cmd_vel_ms) <= CMD_TIMEOUT_MS;
  bool motor_armed = !in_grace && cmd_fresh && !emergency_stop;

  if (!motor_armed) {
    for (int i = 0; i < 4; i++) {
      target_rpm[i] = 0.0f;
      pid[i].reset();
      set_motor_pwm(i, 0.0f);   // 绕过 PID 直接写 0, 避免 PID integral 漏下去
    }
  } else {
    // 闭环: PID 输出 PWM (仅 armed 时)
    for (int i = 0; i < 4; i++) {
      float rpm = w_meas[i] * 60.0f / (2 * PI);
      float u = pid[i].compute(target_rpm[i], rpm, dt);
      set_motor_pwm(i, u);
    }
  }

  // 里程计累积
  float vx, vy, wz;
  mecanum_fk(w_meas, vx, vy, wz);
  theta += wz * dt;
  pos_x += (vx * cosf(theta) - vy * sinf(theta)) * dt;
  pos_y += (vx * sinf(theta) + vy * cosf(theta)) * dt;

  msg_odom.header.stamp.sec = now / 1000;
  msg_odom.header.stamp.nanosec = (now % 1000) * 1000000L;
  msg_odom.pose.pose.position.x = pos_x;
  msg_odom.pose.pose.position.y = pos_y;
  msg_odom.pose.pose.orientation.z = sinf(theta / 2);
  msg_odom.pose.pose.orientation.w = cosf(theta / 2);
  msg_odom.twist.twist.linear.x = vx;
  msg_odom.twist.twist.linear.y = vy;
  msg_odom.twist.twist.angular.z = wz;
  RCSOFTCHECK(rcl_publish(&pub_odom, &msg_odom, NULL));
}

// ==================== 初始化 ====================
void setup() {
  // PlatformIO + micro_ros_platformio: 显式 Serial.begin + transport bind.
  // (micro_ros_platformio 的 API 保持 v2.0.7 风格, 要传 Serial 参数)
  Serial.begin(115200);
  set_microros_serial_transports(Serial);

  pinMode(LED_BUILTIN, OUTPUT);

  // GPIO + LEDC PWM — 启动立刻写 DIR=LOW 和 PWM=0, 任何时候上电不会失控
  for (int i = 0; i < 4; i++) {
    pinMode(DIR_PIN[i], OUTPUT);
    digitalWrite(DIR_PIN[i], LOW);
    pinMode(ENC_A[i], INPUT_PULLUP);
    pinMode(ENC_B[i], INPUT_PULLUP);
  }
  pwm_setup();
  for (int i = 0; i < 4; i++) set_motor_pwm(i, 0.0f);   // PWM 紧急归零
  boot_time_ms = millis();                               // ARM GRACE 起算点

  // ADC (电池电压)
  analogReadResolution(12);           // 0-4095
  analogSetAttenuation(ADC_11db);     // 0-3.3V 量程
  // CHANGE 边沿跟 ISR 里 `A==B` 判向配套 (Tutorial 5 教的方法)
  attachInterrupt(digitalPinToInterrupt(ENC_A[0]), enc_isr_0, CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENC_A[1]), enc_isr_1, CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENC_A[2]), enc_isr_2, CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENC_A[3]), enc_isr_3, CHANGE);

  lifter.attach(SERVO_PIN);
  lifter.write(0);

  delay(2000);  // 等 agent 就绪

  // micro-ROS init
  allocator = rcl_get_default_allocator();
  RCCHECK(rclc_support_init(&support, 0, NULL, &allocator));
  // 节点名跟 Tutorial 5 对齐: 老师课程要求的命名
  RCCHECK(rclc_node_init_default(&node, "hku_dase_micro_ros_node", "", &support));

  RCCHECK(rclc_subscription_init_default(
      &sub_cmd_vel, &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(geometry_msgs, msg, Twist), "/cmd_vel"));

  RCCHECK(rclc_subscription_init_default(
      &sub_lifter, &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Int32), "/lifter_cmd"));

  RCCHECK(rclc_subscription_init_default(
      &sub_set_pid, &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Float32MultiArray), "/set_pid"));
  // 给 msg_set_pid 预分配内存 (Tutorial 5 用 micro_ros_utilities, 这里手动简单分配)
  static float _pid_buf[8];
  msg_set_pid.data.data = _pid_buf;
  msg_set_pid.data.capacity = 8;
  msg_set_pid.data.size = 0;

  RCCHECK(rclc_publisher_init_default(
      &pub_odom, &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(nav_msgs, msg, Odometry), "/wheel_odom"));

  RCCHECK(rclc_publisher_init_default(
      &pub_battery, &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Float32), "/battery_voltage"));

  // /emergency_stop 急停订阅 (安全层 ③)
  RCCHECK(rclc_subscription_init_default(
      &sub_estop, &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Bool), "/emergency_stop"));

  // header frame_id (与 odom_tf_broadcaster 广播的 odom -> base_footprint 对齐,
  // 以及 URDF 里 base_footprint -> base_link 的静态 TF 链一致)
  msg_odom.header.frame_id.data = (char *)"odom";
  msg_odom.header.frame_id.size = 4;
  msg_odom.header.frame_id.capacity = 5;
  msg_odom.child_frame_id.data = (char *)"base_footprint";
  msg_odom.child_frame_id.size = 14;
  msg_odom.child_frame_id.capacity = 15;

  RCCHECK(rclc_timer_init_default(&odom_timer, &support, RCL_MS_TO_NS(50), odom_timer_cb));
  RCCHECK(rclc_timer_init_default(&battery_timer, &support, RCL_MS_TO_NS(1000), battery_timer_cb));

  RCCHECK(rclc_executor_init(&executor, &support.context, 6, &allocator));
  RCCHECK(rclc_executor_add_subscription(&executor, &sub_cmd_vel, &msg_cmd_vel, &cmd_vel_cb, ON_NEW_DATA));
  RCCHECK(rclc_executor_add_subscription(&executor, &sub_lifter, &msg_lifter, &lifter_cb, ON_NEW_DATA));
  RCCHECK(rclc_executor_add_subscription(&executor, &sub_set_pid, &msg_set_pid, &set_pid_cb, ON_NEW_DATA));

  static std_msgs__msg__Bool msg_estop;
  RCCHECK(rclc_executor_add_subscription(&executor, &sub_estop, &msg_estop, &estop_cb, ON_NEW_DATA));
  RCCHECK(rclc_executor_add_timer(&executor, &odom_timer));
  RCCHECK(rclc_executor_add_timer(&executor, &battery_timer));

  last_loop_ms = millis();
}

void loop() {
  RCSOFTCHECK(rclc_executor_spin_some(&executor, RCL_MS_TO_NS(10)));
}
