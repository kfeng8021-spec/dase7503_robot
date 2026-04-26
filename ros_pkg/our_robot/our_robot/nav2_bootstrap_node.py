"""
nav2_bootstrap_node — Nav2 启动后的"激活器".

为什么需要这个 (P0a/P0b 根因, 实测 2026-04-27 凌晨):
  1. AMCL 启动后等 /initialpose. 没收到 → 不发 map→odom TF.
  2. controller_server / planner_server configure 阶段需要 map→base_link
     transform, 拿不到 → configure 超时.
  3. lifecycle_manager_navigation 看到 configure 失败 → 整个 navigation
     链卡 inactive [2], 永远不 active.
  4. 没人调 manage_nodes(STARTUP) 重试 → costmap 不发 → RViz 红叉.

修法 (本 node 做的):
  1. 发 /initialpose 7x retry, BE+VOLATILE QoS (兼容 AMCL sub).
  2. 等 map→base_footprint TF 确认 AMCL 锁住.
  3. 调 /lifecycle_manager_navigation/manage_nodes(0=STARTUP) 重新激活
     planner_server / controller_server / bt_navigator / 等.

完成后保持 node alive (rclpy.spin), 避免 launch 误判进程退出 = fail.
"""
import math
import time

import rclpy
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy

from geometry_msgs.msg import PoseWithCovarianceStamped
from nav2_msgs.srv import ManageLifecycleNodes
from tf2_ros import Buffer, TransformException, TransformListener

from .rack_positions import START_POINT


class Nav2Bootstrap(Node):
    def __init__(self):
        super().__init__("nav2_bootstrap")
        amcl_qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )
        self.pub = self.create_publisher(PoseWithCovarianceStamped, "/initialpose", amcl_qos)
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.startup_client = self.create_client(
            ManageLifecycleNodes, "/lifecycle_manager_navigation/manage_nodes"
        )

    def run(self):
        self.get_logger().info(
            f"Bootstrap: publishing /initialpose 7x (start={START_POINT['x']:.3f}, "
            f"{START_POINT['y']:.3f}, yaw={START_POINT['yaw']:.3f})..."
        )
        msg = self._make_initialpose()
        for _ in range(7):
            msg.header.stamp = self.get_clock().now().to_msg()
            self.pub.publish(msg)
            time.sleep(0.7)

        self.get_logger().info("Bootstrap: waiting for map→base_footprint TF (15s)...")
        deadline = self.get_clock().now() + Duration(seconds=15)
        tf_ok = False
        while self.get_clock().now() < deadline:
            rclpy.spin_once(self, timeout_sec=0.2)
            try:
                self.tf_buffer.lookup_transform("map", "base_footprint", rclpy.time.Time())
                tf_ok = True
                break
            except TransformException:
                continue

        if not tf_ok:
            self.get_logger().warn("Bootstrap: TF never appeared, retry initialpose 3x...")
            for _ in range(3):
                msg.header.stamp = self.get_clock().now().to_msg()
                self.pub.publish(msg)
                time.sleep(0.5)
        else:
            self.get_logger().info("Bootstrap: AMCL locked ✓ map→base_footprint TF live")

        self.get_logger().info(
            "Bootstrap: waiting for /lifecycle_manager_navigation/manage_nodes service..."
        )
        if not self.startup_client.wait_for_service(timeout_sec=20.0):
            self.get_logger().error(
                "Bootstrap: manage_nodes service not available, giving up "
                "(navigation lifecycle 可能没起 — 检查 navigation_launch.py)"
            )
            return

        req = ManageLifecycleNodes.Request()
        req.command = 0  # STARTUP
        self.get_logger().info("Bootstrap: calling manage_nodes(STARTUP)...")
        future = self.startup_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=30.0)

        result = future.result()
        if result is not None and result.success:
            self.get_logger().info(
                "Bootstrap: ✓ nav2 navigation lifecycle ACTIVE — costmap / planner / controller ready"
            )
        else:
            self.get_logger().warn(f"Bootstrap: manage_nodes returned {result}")

    def _make_initialpose(self) -> PoseWithCovarianceStamped:
        msg = PoseWithCovarianceStamped()
        msg.header.frame_id = "map"
        msg.pose.pose.position.x = float(START_POINT["x"])
        msg.pose.pose.position.y = float(START_POINT["y"])
        yaw = float(START_POINT["yaw"])
        msg.pose.pose.orientation.z = math.sin(yaw / 2.0)
        msg.pose.pose.orientation.w = math.cos(yaw / 2.0)
        cov = [0.0] * 36
        cov[0] = 0.25     # x var
        cov[7] = 0.25     # y var
        cov[35] = 0.0685  # yaw var (~15°)
        msg.pose.covariance = cov
        return msg


def main(args=None):
    rclpy.init(args=args)
    node = Nav2Bootstrap()
    try:
        node.run()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
