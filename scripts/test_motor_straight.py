#!/usr/bin/env python3
"""
模块 B 电机验收: 发 vx=0.1m/s 5 秒, 看里程计 pos_x 是否 ≈ 0.5m.

标准 (Full Plan Week 1):
  - pos_x 在 0.45-0.55m 之间 (±10%)
  - pos_y 在 -0.05-0.05m 之间 (横向漂移 ≤5cm)
  - theta 在 -0.1~0.1 rad (方向偏 ≤5.7°)

用法 (Pi5 上):
  ros2 run our_robot qr_scanner_node &   # 可选
  python3 scripts/test_motor_straight.py
"""
import math
import time

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry


class MotorStraightTest(Node):
    def __init__(self):
        super().__init__("motor_straight_test")
        self.cmd_pub = self.create_publisher(Twist, "/cmd_vel", 10)
        self.odom_sub = self.create_subscription(
            Odometry, "/wheel_odom", self._odom_cb, 10
        )
        self.start_odom = None
        self.last_odom = None

    def _odom_cb(self, msg: Odometry):
        if self.start_odom is None:
            self.start_odom = msg
        self.last_odom = msg

    def run(self):
        # 等 odom 就位
        self.get_logger().info("等待 /wheel_odom 第一帧...")
        while rclpy.ok() and self.start_odom is None:
            rclpy.spin_once(self, timeout_sec=0.1)

        self.get_logger().info("发 vx=0.1m/s, 5秒...")
        twist = Twist()
        twist.linear.x = 0.1
        t0 = time.time()
        while time.time() - t0 < 5.0 and rclpy.ok():
            self.cmd_pub.publish(twist)
            rclpy.spin_once(self, timeout_sec=0.05)

        self.get_logger().info("停止")
        stop = Twist()
        for _ in range(20):
            self.cmd_pub.publish(stop)
            rclpy.spin_once(self, timeout_sec=0.05)

        # 评估
        s = self.start_odom.pose.pose.position
        e = self.last_odom.pose.pose.position
        dx = e.x - s.x
        dy = e.y - s.y

        # yaw from quaternion
        q_s = self.start_odom.pose.pose.orientation
        q_e = self.last_odom.pose.pose.orientation
        yaw_s = 2 * math.atan2(q_s.z, q_s.w)
        yaw_e = 2 * math.atan2(q_e.z, q_e.w)
        dtheta = yaw_e - yaw_s

        print("\n=== 测试结果 ===")
        print(f"  前进距离 Δx = {dx:.3f} m  (目标 0.50±0.05, {'OK' if 0.45<=dx<=0.55 else 'FAIL'})")
        print(f"  侧向漂移 Δy = {dy:.3f} m  (目标 ±0.05, {'OK' if -0.05<=dy<=0.05 else 'FAIL'})")
        print(f"  转角漂移 Δθ = {math.degrees(dtheta):.1f}°  (目标 ±5.7°, {'OK' if abs(dtheta)<0.1 else 'FAIL'})")
        print()
        if abs(dtheta) > 0.1:
            print("⚠️ 转角漂移大, 检查四轮 PWM 方向 + 编码器极性")
        if abs(dy) > 0.05:
            print("⚠️ 侧向漂移, 可能 Mecanum 轮子装反 (X形辊子)")
        if not 0.45 <= dx <= 0.55:
            print("⚠️ 前进距离不对, 调 PID kp / 检查编码器 PPR 参数")


def main():
    rclpy.init()
    node = MotorStraightTest()
    try:
        node.run()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
