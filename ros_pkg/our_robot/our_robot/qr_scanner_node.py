#!/usr/bin/env python3
"""
QR Scanner Node.

订阅 /camera/image_raw (sensor_msgs/Image),
用 pyzbar 解码, 连续确认 CONFIRM_THRESHOLD 帧后发布到 /qr_result (std_msgs/String).

依赖: cv_bridge, opencv-python, pyzbar (sudo apt install python3-pyzbar python3-opencv)
"""
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String
from cv_bridge import CvBridge
import cv2
from pyzbar import pyzbar


class QRScannerNode(Node):
    CONFIRM_THRESHOLD = 3  # 连续 3 帧解出同一内容才算稳定, 抗误识别

    def __init__(self):
        super().__init__("qr_scanner")
        self.bridge = CvBridge()
        self.sub = self.create_subscription(
            Image, "/camera/image_raw", self._cb, 10
        )
        self.pub = self.create_publisher(String, "/qr_result", 10)
        self.last_result = ""
        self.confirm_count = 0
        self.get_logger().info("QR scanner ready.")

    def _cb(self, msg: Image):
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, "bgr8")
        except Exception as e:
            self.get_logger().warn(f"cv_bridge fail: {e}")
            return

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # CLAHE 增强对比度, 对暗光 / 反光场景有效
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)

        decoded = pyzbar.decode(gray)
        if not decoded:
            self.confirm_count = 0
            return

        raw = decoded[0].data.decode("utf-8").strip()
        if raw == self.last_result:
            self.confirm_count += 1
        else:
            self.last_result = raw
            self.confirm_count = 1

        if self.confirm_count >= self.CONFIRM_THRESHOLD:
            out = String()
            out.data = raw
            self.pub.publish(out)
            self.get_logger().info(f"QR confirmed: {raw}")
            self.confirm_count = 0


def main(args=None):
    rclpy.init(args=args)
    node = QRScannerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
