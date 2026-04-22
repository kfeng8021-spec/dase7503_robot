#!/usr/bin/env python3
"""
QR Scanner Node — 按 Tutorial 7 风格实现.

订阅 /camera/image_raw/compressed (sensor_msgs/CompressedImage),
用 cv2.QRCodeDetector 解码 (老师 Tutorial 7 第 5 页教的方法),
连续确认 CONFIRM_THRESHOLD 帧后发布到 /qr_result (std_msgs/String).

QoS: BEST_EFFORT + KEEP_LAST + depth=1 (Tutorial 7 标准 QoS, 适合图像流).

相机源: Pi Camera 3 via camera_ros. camera_ros 默认发布:
  - /camera/image_raw (Image 原图)
  - /camera/image_raw/compressed (CompressedImage, 需装 image_transport_plugins)
  如果 compressed 拿不到, 可以跑 scripts/image_republisher.py 转一下.
"""
import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String


class QRScannerNode(Node):
    CONFIRM_THRESHOLD = 3  # 连续 3 帧解出同一内容才发布 (抗误识别)

    def __init__(self):
        super().__init__("qr_scanner")

        qos = QoSProfile(
            depth=1,
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
        )

        self.sub = self.create_subscription(
            CompressedImage, "/camera/image_raw/compressed", self._cb, qos
        )
        self.pub = self.create_publisher(String, "/qr_result", 10)

        self.bridge = CvBridge()
        self.detector = cv2.QRCodeDetector()   # Tutorial 7 用的 OpenCV 自带解码器

        self.last_result = ""
        self.confirm_count = 0
        self.get_logger().info(
            "QR scanner ready. Sub: /camera/image_raw/compressed (BEST_EFFORT)"
        )

    def _cb(self, msg: CompressedImage):
        # 解压图像 (Tutorial 7 第 14 页的做法)
        np_arr = np.frombuffer(msg.data, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None:
            return

        # CLAHE 增强对比度, 对反光 / 低光照场景提升识别率
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)

        # cv2.QRCodeDetector (Tutorial 7 风格)
        data, bbox, _ = self.detector.detectAndDecode(gray)
        if not data:
            self.confirm_count = 0
            return

        data = data.strip()
        if data == self.last_result:
            self.confirm_count += 1
        else:
            self.last_result = data
            self.confirm_count = 1

        if self.confirm_count >= self.CONFIRM_THRESHOLD:
            out = String()
            out.data = data
            self.pub.publish(out)
            self.get_logger().info(f"QR Code detected: {data}")
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
