#!/usr/bin/env python3
"""
Odom TF Broadcaster.

Yahboom factory FW 发 /odom_raw (nav_msgs/Odometry), 不发 TF.
这个节点订阅 /odom_raw 然后广播 odom -> base_footprint TF.
(Nav2 需要这条 TF 链条, 没它 AMCL 无法定位)

原来订的是 /wheel_odom — 那是团队 PIO 固件的命名, 现在切到工厂 FW 已废弃.
改订 /odom_raw 与工厂 FW 对齐.

TF 树完整链 (运行后):
  map --(AMCL)--> odom --(本节点)--> base_footprint --(URDF)--> base_link -> laser_link / camera_link
"""
import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from geometry_msgs.msg import TransformStamped
from tf2_ros import TransformBroadcaster


class OdomTFBroadcaster(Node):
    def __init__(self):
        super().__init__("odom_tf_broadcaster")
        self.br = TransformBroadcaster(self)
        self.sub = self.create_subscription(
            Odometry, "/odom_raw", self._cb, 50
        )
        self.get_logger().info("odom -> base_footprint TF broadcaster started (sub /odom_raw).")

    def _cb(self, msg: Odometry):
        t = TransformStamped()
        t.header.stamp = msg.header.stamp
        t.header.frame_id = "odom"
        t.child_frame_id = "base_footprint"
        t.transform.translation.x = msg.pose.pose.position.x
        t.transform.translation.y = msg.pose.pose.position.y
        t.transform.translation.z = 0.0
        t.transform.rotation = msg.pose.pose.orientation
        self.br.sendTransform(t)


def main(args=None):
    rclpy.init(args=args)
    node = OdomTFBroadcaster()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
