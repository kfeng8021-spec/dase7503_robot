"""
cmd_vel 中继: /cmd_vel_nav → /cmd_vel + deadband 放大.

绕过 nav2 default chain (velocity_smoother + collision_monitor).

关键 hack: ESP32 factory FW motor 死区 ~ 0.15 m/s linear, ~ 0.5 rad/s angular.
controller 输出常常在死区内 (linear=0, angular=0.16 等), motor 不响应车不动.
relay 把死区内的非零命令放大到死区以上, 保留方向.
"""
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist


# ESP32 motor 死区 (实测)
LINEAR_DEADBAND = 0.15   # |vx| < 0.15 motor 不响应
ANGULAR_DEADBAND = 0.5   # |wz| < 0.5 motor 不响应
EPS = 0.01               # 完全 0 不放大 (controller 想停)


class CmdVelRelay(Node):
    def __init__(self):
        super().__init__("cmd_vel_relay")
        self.pub = self.create_publisher(Twist, "/cmd_vel", 10)
        self.sub = self.create_subscription(Twist, "/cmd_vel_nav", self._cb, 10)
        self.get_logger().info(
            f"cmd_vel_relay: /cmd_vel_nav → /cmd_vel "
            f"(deadband boost: lin {LINEAR_DEADBAND}, ang {ANGULAR_DEADBAND})"
        )

    def _cb(self, msg: Twist):
        out = Twist()
        out.linear.x = msg.linear.x
        out.linear.y = msg.linear.y
        out.angular.z = msg.angular.z

        # Boost linear if in deadband
        if EPS < abs(out.linear.x) < LINEAR_DEADBAND:
            out.linear.x = LINEAR_DEADBAND if out.linear.x > 0 else -LINEAR_DEADBAND
        # Boost angular if in deadband
        if EPS < abs(out.angular.z) < ANGULAR_DEADBAND:
            out.angular.z = ANGULAR_DEADBAND if out.angular.z > 0 else -ANGULAR_DEADBAND

        self.pub.publish(out)


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
