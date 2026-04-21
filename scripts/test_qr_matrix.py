#!/usr/bin/env python3
"""
QR 识别距离 × 角度矩阵测试 (Full Plan C5 验收).

用法:
  # 1. Pi5 相机 + qr_scanner_node 运行中
  # 2. 准备卷尺 + 量角器 (或打印几个角度标记贴地上)
  # 3. 这个脚本会提示你把 QR 放到特定距离/角度, 然后采样 30 秒看识别成功率

  ros2 launch our_robot robot_full.launch.py &   # 或者单跑 camera + qr_scanner
  python3 scripts/test_qr_matrix.py

结果: 打印识别率矩阵到 stdout + 存 qr_matrix_<timestamp>.csv

标准: 0.3m 正面识别率 ≥ 95%.
"""
import csv
import os
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

DISTANCES = [0.10, 0.20, 0.30, 0.50]
ANGLES = [0, 15, 30, 45]
SAMPLE_SEC = 10       # 每组采样 10 秒
EXPECTED_INTERVAL = 0.1  # /qr_result 话题期望间隔 (= 相机 fps 倒数附近)


class QRMatrixTest(Node):
    def __init__(self):
        super().__init__("qr_matrix_test")
        self.sub = self.create_subscription(String, "/qr_result", self._cb, 10)
        self.detections = 0

    def _cb(self, msg: String):
        self.detections += 1

    def sample(self, sec: float) -> int:
        self.detections = 0
        t0 = time.time()
        while time.time() - t0 < sec and rclpy.ok():
            rclpy.spin_once(self, timeout_sec=0.05)
        return self.detections


def main():
    rclpy.init()
    node = QRMatrixTest()

    results = {}   # (distance, angle) -> detections_count
    print("\n=== QR 识别矩阵测试 ===")
    print(f"每组采样 {SAMPLE_SEC} 秒, 期望 /qr_result 约 {int(SAMPLE_SEC/EXPECTED_INTERVAL)} 次")
    print(f"({len(DISTANCES)*len(ANGLES)} 组 × {SAMPLE_SEC}s = 总共 {len(DISTANCES)*len(ANGLES)*SAMPLE_SEC//60} 分钟)\n")
    input("准备好 QR 卡片, 按 Enter 开始...")

    for d in DISTANCES:
        for a in ANGLES:
            print(f"\n--- 距离 {d:.2f}m, 角度 {a}° ---")
            input(f"把 QR 卡片放到距离相机 {d:.2f}m, 偏转 {a}°, 按 Enter 开始采样")
            cnt = node.sample(SAMPLE_SEC)
            results[(d, a)] = cnt
            print(f"  识别 {cnt} 次")

    # 打印矩阵
    print("\n=== 结果矩阵 ===")
    header = "距离\\角度  " + "  ".join(f"{a}°".rjust(6) for a in ANGLES)
    print(header)
    print("-" * len(header))
    for d in DISTANCES:
        row = f"{d:.2f}m    "
        for a in ANGLES:
            row += f" {results[(d,a)]:6d}"
        print(row)

    # 存 CSV
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.expanduser(f"~/qr_logs/qr_matrix_{stamp}.csv")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["distance_m", "angle_deg", "detections", "sample_sec"])
        for (d, a), c in results.items():
            w.writerow([d, a, c, SAMPLE_SEC])
    print(f"\n保存: {path}")

    # 0.3m 正面达标?
    ref = results.get((0.30, 0))
    if ref is not None:
        expected = SAMPLE_SEC / EXPECTED_INTERVAL * 0.95
        print(f"\n0.3m 正面: {ref} 次, {'✓ 达标 ≥95%' if ref >= expected else '✗ 未达标, 调 CLAHE / 分辨率 / 焦距'}")

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
