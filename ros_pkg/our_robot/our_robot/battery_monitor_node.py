#!/usr/bin/env python3
"""
Battery Monitor - 订阅 ESP32 发布的 /battery_voltage, 低电压报警.

7.4V 锂电池安全范围:
  充满: 8.4V
  正常工作: 7.0-8.0V
  报警: < 6.8V (单节 3.4V, 再低会损坏电池)
  紧急停机: < 6.4V

报警方式: rclpy logger WARN + ROS 话题 /battery_alert (std_msgs/String).
想接蜂鸣器的话在 ESP32 固件里加个 buzzer pin 根据 /battery_alert 响.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32, String


class BatteryMonitor(Node):
    VOLT_WARN = 6.8     # 低电量告警
    VOLT_CRIT = 6.4     # 紧急停机阈值
    VOLT_OK = 7.0       # 恢复正常阈值 (滞回, 防抖)

    def __init__(self):
        super().__init__("battery_monitor")
        self.sub = self.create_subscription(
            Float32, "/battery_voltage", self._cb, 10
        )
        self.pub = self.create_publisher(String, "/battery_alert", 10)
        self.state = "OK"
        self.last_voltage = None
        # 5 秒打印一次电压, 防止日志刷屏
        self.create_timer(5.0, self._periodic_log)
        self.get_logger().info("Battery monitor started.")

    def _cb(self, msg: Float32):
        v = msg.data
        self.last_voltage = v

        # 滞回: 只有低于 WARN 才进入 WARN, 只有高于 OK 才回到 OK
        new_state = self.state
        if v < self.VOLT_CRIT:
            new_state = "CRITICAL"
        elif v < self.VOLT_WARN and self.state == "OK":
            new_state = "WARN"
        elif v > self.VOLT_OK and self.state in ("WARN", "CRITICAL"):
            new_state = "OK"

        if new_state != self.state:
            self.state = new_state
            alert = String()
            alert.data = new_state
            self.pub.publish(alert)
            if new_state == "CRITICAL":
                self.get_logger().error(f"⚠️ BATTERY CRITICAL: {v:.2f}V — 立刻停机换电池")
            elif new_state == "WARN":
                self.get_logger().warn(f"⚠️ Battery LOW: {v:.2f}V")
            else:
                self.get_logger().info(f"Battery recovered: {v:.2f}V")

    def _periodic_log(self):
        if self.last_voltage is not None:
            self.get_logger().info(
                f"Battery: {self.last_voltage:.2f}V [{self.state}]"
            )


def main(args=None):
    rclpy.init(args=args)
    node = BatteryMonitor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
