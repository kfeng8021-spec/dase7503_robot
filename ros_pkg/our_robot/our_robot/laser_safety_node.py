#!/usr/bin/env python3
"""
Laser Safety Gate — teleop 前置避障.

订阅:
  /cmd_vel_raw  geometry_msgs/Twist    <- teleop_twist_keyboard (用 `-r /cmd_vel:=/cmd_vel_raw`)
  /scan         sensor_msgs/LaserScan  <- MS200 LiDAR

发布:
  /cmd_vel      geometry_msgs/Twist    -> ESP32 micro-ROS

Mecanum 三轴独立 (vx, vy, wz). 每次收到 cmd_vel_raw:
  - 按运动方向在 /scan 里查对应扇区 (±30°) 最近距离
  - 距离 > slow_down: 全速通过
  - hard_stop < d < slow_down: 线性缩放速度
  - d <= hard_stop: 该轴置零
  - wz 仅在机器人 footprint 内无障碍 (min全周 > hard_stop) 时允许
  - watchdog: 0.5s 没新 cmd_vel_raw -> 发零 Twist

扇区约定 (laser_link = base_link, 0 rad 指前):
  前进 vx>0  -> sector θ=0
  后退 vx<0  -> sector θ=π
  左平移 vy>0 -> sector θ=+π/2
  右平移 vy<0 -> sector θ=-π/2
"""
import math

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from sensor_msgs.msg import LaserScan


def _wrap(a: float) -> float:
    while a > math.pi:
        a -= 2.0 * math.pi
    while a < -math.pi:
        a += 2.0 * math.pi
    return a


def _sector_min(scan: LaserScan, center: float, half_width: float) -> float:
    """扇区 [center-half, center+half] (rad) 内的最小有效距离. 跨 ±π 自动处理."""
    n = len(scan.ranges)
    if n == 0:
        return float("inf")
    ainc = scan.angle_increment if scan.angle_increment > 1e-9 else 1e-9
    rmin_valid = max(scan.range_min, 1e-3)
    rmax_valid = scan.range_max if scan.range_max > 0 else float("inf")

    low = _wrap(center - half_width)
    high = _wrap(center + half_width)
    crosses = low > high  # 扇区跨 ±π

    best = float("inf")
    for i, r in enumerate(scan.ranges):
        if (r is None) or math.isinf(r) or math.isnan(r):
            continue
        if r < rmin_valid or r > rmax_valid:
            continue
        a = _wrap(scan.angle_min + i * ainc)
        inside = (a >= low or a <= high) if crosses else (low <= a <= high)
        if inside and r < best:
            best = r
    return best


class LaserSafetyGate(Node):
    def __init__(self):
        super().__init__("laser_safety_gate")

        p = self.declare_parameter
        self.hard_stop = float(p("hard_stop_dist", 0.25).value)
        self.slow_down = float(p("slow_down_dist", 0.50).value)
        self.sector_half = float(p("sector_half_rad", math.radians(30.0)).value)
        self.scan_topic = str(p("scan_topic", "scan").value)
        self.cmd_in = str(p("cmd_in_topic", "cmd_vel_raw").value)
        self.cmd_out = str(p("cmd_out_topic", "cmd_vel").value)
        self.watchdog_sec = float(p("watchdog_sec", 0.5).value)

        self._last_scan = None
        self._last_cmd = Twist()
        self._last_cmd_t = 0.0
        self._warned_no_scan = False

        self.pub = self.create_publisher(Twist, self.cmd_out, 10)
        self.create_subscription(LaserScan, self.scan_topic, self._on_scan, 10)
        self.create_subscription(Twist, self.cmd_in, self._on_cmd, 10)
        self.create_timer(0.05, self._tick)  # 20 Hz

        self.get_logger().info(
            f"laser_safety_gate up: {self.cmd_in} + {self.scan_topic} -> {self.cmd_out} | "
            f"hard={self.hard_stop:.2f}m slow={self.slow_down:.2f}m sector=±{math.degrees(self.sector_half):.0f}°"
        )

    def _on_scan(self, msg: LaserScan):
        self._last_scan = msg
        if self._warned_no_scan:
            self.get_logger().info("scan received, gate active")
            self._warned_no_scan = False

    def _on_cmd(self, msg: Twist):
        self._last_cmd = msg
        self._last_cmd_t = self.get_clock().now().nanoseconds * 1e-9

    def _scale(self, d: float) -> float:
        if d >= self.slow_down:
            return 1.0
        if d <= self.hard_stop:
            return 0.0
        return (d - self.hard_stop) / (self.slow_down - self.hard_stop)

    def _tick(self):
        now = self.get_clock().now().nanoseconds * 1e-9
        if now - self._last_cmd_t > self.watchdog_sec:
            self.pub.publish(Twist())
            return

        scan = self._last_scan
        if scan is None:
            if not self._warned_no_scan:
                self.get_logger().warn("no /scan yet — cmd_vel held at zero")
                self._warned_no_scan = True
            self.pub.publish(Twist())
            return

        cmd = self._last_cmd
        out = Twist()

        if cmd.linear.x > 0.0:
            out.linear.x = cmd.linear.x * self._scale(_sector_min(scan, 0.0, self.sector_half))
        elif cmd.linear.x < 0.0:
            out.linear.x = cmd.linear.x * self._scale(_sector_min(scan, math.pi, self.sector_half))

        if cmd.linear.y > 0.0:
            out.linear.y = cmd.linear.y * self._scale(_sector_min(scan, math.pi / 2.0, self.sector_half))
        elif cmd.linear.y < 0.0:
            out.linear.y = cmd.linear.y * self._scale(_sector_min(scan, -math.pi / 2.0, self.sector_half))

        closest_any = _sector_min(scan, 0.0, math.pi)
        if closest_any > self.hard_stop:
            out.angular.z = cmd.angular.z
        # else 旋转时 footprint 内有障碍 -> angular.z 保持 0

        self.pub.publish(out)


def main(args=None):
    rclpy.init(args=args)
    node = LaserSafetyGate()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
