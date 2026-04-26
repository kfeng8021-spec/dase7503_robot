"""
cmd_vel 中继: /cmd_vel_nav → /cmd_vel.

绕过 nav2 default chain (velocity_smoother + collision_monitor) — 实测它们之间
TF / odom topic 不通导致 cmd_vel 卡死, controller "Failed to make progress".
ESP32 工厂 FW 直接订阅 /cmd_vel, 我们直发即可.

跟 controller 的速度限制一致 — controller 内部已有 max_velocity 限制 (在
nav2_params.yaml controller_server.RegulatedPurePursuitController 里), 不需要
中继再 smooth/saturate.
"""
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist


class CmdVelRelay(Node):
    def __init__(self):
        super().__init__("cmd_vel_relay")
        self.pub = self.create_publisher(Twist, "/cmd_vel", 10)
        self.sub = self.create_subscription(Twist, "/cmd_vel_nav", self._cb, 10)
        self.get_logger().info("cmd_vel_relay: /cmd_vel_nav → /cmd_vel")

    def _cb(self, msg: Twist):
        self.pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = CmdVelRelay()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
