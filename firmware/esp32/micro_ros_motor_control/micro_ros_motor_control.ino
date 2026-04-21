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

#include <micro_ros_arduino.h>
#include <rcl/rcl.h>
#include <rcl/error_handling.h>
#include <rclc/rclc.h>
#include <rclc/executor.h>
#include <geometry_msgs/msg/twist.h>
#include <nav_msgs/msg/odometry.h>
#include <std_msgs/msg/int32.h>
#include <ESP32Servo.h>

// ==================== 物理常量 ====================
#define WHEEL_RADIUS   0.0325f   // m
#define WHEEL_BASE_X   0.110f    // m, 左右轴距 / 2
#define WHEEL_BASE_Y   0.110f    // m, 前后轴距 / 2
#define PPR            13
#define GEAR_RATIO     20
#define ENC_CPR        (PPR * GEAR_RATIO * 4)   // = 1040
#define M_TO_ENC       (ENC_CPR / (2 * PI * WHEEL_RADIUS))

// ==================== GPIO 分配 ====================
const int PWM_PIN[4] = {4,  15, 9,  13};
const int DIR_PIN[4] = {5,  16, 10, 14};
const int ENC_A[4]   = {6,  47, 11, 1};
const int ENC_B[4]   = {7,  48, 12, 2};
#define SERVO_PIN 8

// ==================== 状态 ====================
volatile long enc_count[4] = {0, 0, 0, 0};
float cmd_vx = 0, cmd_vy = 0, cmd_wz = 0;   // 目标
float target_rpm[4] = {0};                    // 四轮目标转速
long prev_enc[4] = {0};
unsigned long last_loop_ms = 0;

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
rcl_subscription_t sub_cmd_vel, sub_lifter;
rcl_publisher_t pub_odom;
geometry_msgs__msg__Twist msg_cmd_vel;
std_msgs__msg__Int32 msg_lifter;
nav_msgs__msg__Odometry msg_odom;
rclc_executor_t executor;
rclc_support_t support;
rcl_allocator_t allocator;
rcl_node_t node;
rcl_timer_t odom_timer;

#define RCCHECK(fn) { rcl_ret_t rc = fn; if (rc != RCL_RET_OK) { error_loop(); } }
#define RCSOFTCHECK(fn) { rcl_ret_t rc = fn; (void)rc; }

void error_loop() {
  while (1) { digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN)); delay(100); }
}

// ==================== 编码器中断 ====================
void IRAM_ATTR enc_isr_0() { enc_count[0] += (digitalRead(ENC_B[0]) ? 1 : -1); }
void IRAM_ATTR enc_isr_1() { enc_count[1] += (digitalRead(ENC_B[1]) ? 1 : -1); }
void IRAM_ATTR enc_isr_2() { enc_count[2] += (digitalRead(ENC_B[2]) ? 1 : -1); }
void IRAM_ATTR enc_isr_3() { enc_count[3] += (digitalRead(ENC_B[3]) ? 1 : -1); }

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

// ==================== 电机驱动 ====================
void set_motor_pwm(int i, float pwm_val) {
  // pwm_val -255..255
  bool forward = pwm_val >= 0;
  digitalWrite(DIR_PIN[i], forward ? HIGH : LOW);
  int duty = constrain((int)fabs(pwm_val), 0, 255);
  analogWrite(PWM_PIN[i], duty);
}

// ==================== 回调 ====================
void cmd_vel_cb(const void *msgin) {
  const geometry_msgs__msg__Twist *m = (const geometry_msgs__msg__Twist *) msgin;
  cmd_vx = m->linear.x;
  cmd_vy = m->linear.y;
  cmd_wz = m->angular.z;
  float w[4];
  mecanum_ik(cmd_vx, cmd_vy, cmd_wz, w);
  // 转 rad/s -> RPM 作为 PID setpoint
  for (int i = 0; i < 4; i++) target_rpm[i] = w[i] * 60.0f / (2 * PI);
}

void lifter_cb(const void *msgin) {
  const std_msgs__msg__Int32 *m = (const std_msgs__msg__Int32 *) msgin;
  lifter_state = m->data;
  lifter.write(lifter_state == 1 ? 180 : 0);  // 180°=抬起, 0°=放下
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

  // 闭环: PID 输出 PWM
  for (int i = 0; i < 4; i++) {
    float rpm = w_meas[i] * 60.0f / (2 * PI);
    float u = pid[i].compute(target_rpm[i], rpm, dt);
    set_motor_pwm(i, u);
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
  Serial.begin(115200);      // 必须跟 micro-ros-agent -b 一致!
  set_microros_serial_transports(Serial);

  pinMode(LED_BUILTIN, OUTPUT);

  // GPIO
  for (int i = 0; i < 4; i++) {
    pinMode(PWM_PIN[i], OUTPUT);
    pinMode(DIR_PIN[i], OUTPUT);
    pinMode(ENC_A[i], INPUT_PULLUP);
    pinMode(ENC_B[i], INPUT_PULLUP);
  }
  attachInterrupt(digitalPinToInterrupt(ENC_A[0]), enc_isr_0, RISING);
  attachInterrupt(digitalPinToInterrupt(ENC_A[1]), enc_isr_1, RISING);
  attachInterrupt(digitalPinToInterrupt(ENC_A[2]), enc_isr_2, RISING);
  attachInterrupt(digitalPinToInterrupt(ENC_A[3]), enc_isr_3, RISING);

  lifter.attach(SERVO_PIN);
  lifter.write(0);

  delay(2000);  // 等 agent 就绪

  // micro-ROS init
  allocator = rcl_get_default_allocator();
  RCCHECK(rclc_support_init(&support, 0, NULL, &allocator));
  RCCHECK(rclc_node_init_default(&node, "micro_ros_node", "", &support));

  RCCHECK(rclc_subscription_init_default(
      &sub_cmd_vel, &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(geometry_msgs, msg, Twist), "/cmd_vel"));

  RCCHECK(rclc_subscription_init_default(
      &sub_lifter, &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Int32), "/lifter_cmd"));

  RCCHECK(rclc_publisher_init_default(
      &pub_odom, &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(nav_msgs, msg, Odometry), "/wheel_odom"));

  // header frame_id
  msg_odom.header.frame_id.data = (char *)"odom";
  msg_odom.header.frame_id.size = 4;
  msg_odom.header.frame_id.capacity = 5;
  msg_odom.child_frame_id.data = (char *)"base_link";
  msg_odom.child_frame_id.size = 9;
  msg_odom.child_frame_id.capacity = 10;

  RCCHECK(rclc_timer_init_default(&odom_timer, &support, RCL_MS_TO_NS(50), odom_timer_cb));

  RCCHECK(rclc_executor_init(&executor, &support.context, 3, &allocator));
  RCCHECK(rclc_executor_add_subscription(&executor, &sub_cmd_vel, &msg_cmd_vel, &cmd_vel_cb, ON_NEW_DATA));
  RCCHECK(rclc_executor_add_subscription(&executor, &sub_lifter, &msg_lifter, &lifter_cb, ON_NEW_DATA));
  RCCHECK(rclc_executor_add_timer(&executor, &odom_timer));

  last_loop_ms = millis();
}

void loop() {
  RCSOFTCHECK(rclc_executor_spin_some(&executor, RCL_MS_TO_NS(10)));
}
