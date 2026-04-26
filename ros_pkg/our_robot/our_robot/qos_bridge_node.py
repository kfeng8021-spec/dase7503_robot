"""
QoS bridge: 把 ESP32 micro-ros publish (BEST_EFFORT) 转发成 RELIABLE topic.

ESP32 factory FW publish /odom_raw + /imu 用 BE QoS, 但 robot_localization EKF
默认 RELIABLE 订阅, 不兼容 → EKF 收不到 → 不发 /odometry/filtered.

这个节点 BE 订阅 + RELIABLE republish 一份给 EKF 用.
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu


class QosBridge(Node):
    def __init__(self):
        super().__init__("qos_bridge")
        be = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT, depth=10)
        rel = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, depth=10)

        self.odom_pub = self.create_publisher(Odometry, "/odom_raw_rel", rel)
        self.odom_sub = self.create_subscription(
            Odometry, "/odom_raw", self.odom_pub.publish, be
        )

        self.imu_pub = self.create_publisher(Imu, "/imu_rel", rel)
        self.imu_sub = self.create_subscription(
            Imu, "/imu", self.imu_pub.publish, be
        )

        self.get_logger().info("qos_bridge: /odom_raw → /odom_raw_rel, /imu → /imu_rel (BE→RELIABLE)")


def main(args=None):
    rclpy.init(args=args)
    node = QosBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
