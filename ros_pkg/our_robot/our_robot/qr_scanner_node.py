#!/usr/bin/env python3
"""
QR Scanner Node — 按 Tutorial 7 风格实现 + pyzbar fallback + 多尺度尝试.

订阅 /camera/image_raw/compressed (sensor_msgs/CompressedImage),
依次尝试: cv2.QRCodeDetector(原图/CLAHE) → pyzbar(原图/CLAHE/2x/3x).
连续确认 CONFIRM_THRESHOLD 帧后发布到 /qr_result (std_msgs/String).

QoS: BEST_EFFORT + KEEP_LAST + depth=1 (适合图像流).

相机源: Pi Camera 3 via camera_ros. 默认发布:
  /camera/image_raw (Image), /camera/image_raw/compressed (CompressedImage).

为什么加 pyzbar + 多尺度:
  机器人到货架 ~30cm 时 QR 在 800x600 画面里 ~80x80 像素, cv2.QRCodeDetector
  在小 QR 上识别率低. 实测 (2026-04-25) 同一帧 cv2 detect 失败 → pyzbar
  原图也失败 → 2x upscale 后 pyzbar 成功. 所以加多尺度 fallback chain.
"""
import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String

try:
    from pyzbar.pyzbar import decode as pyzbar_decode
except ImportError:
    pyzbar_decode = None


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

    def _try_decode(self, gray):
        """多策略解码. 返回字符串或 ''."""
        # 1. cv2.QRCodeDetector (Tutorial 7 教的方法, 大 QR 时快)
        data, _, _ = self.detector.detectAndDecode(gray)
        if data: return data
        # 2. pyzbar 原图 (cv2 失败时常 work)
        if pyzbar_decode is not None:
            r = pyzbar_decode(gray)
            if r: return r[0].data.decode("utf-8", errors="ignore")
            # 3. pyzbar 2x upscale (远距离小 QR 兜底, 实测有效)
            big2 = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
            r = pyzbar_decode(big2)
            if r: return r[0].data.decode("utf-8", errors="ignore")
            # 4. pyzbar 3x upscale (极远距离, 罕用)
            big3 = cv2.resize(gray, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
            r = pyzbar_decode(big3)
            if r: return r[0].data.decode("utf-8", errors="ignore")
        return ""

    def _cb(self, msg: CompressedImage):
        # 解压图像 (空 buffer 直接 skip, 防 cv2.imdecode assertion)
        if not msg.data:
            return
        np_arr = np.frombuffer(msg.data, np.uint8)
        if np_arr.size == 0:
            return
        try:
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        except cv2.error:
            return
        if frame is None:
            return

        # CLAHE 增强对比度, 对反光 / 低光照场景提升识别率
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)

        data = self._try_decode(gray)
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
