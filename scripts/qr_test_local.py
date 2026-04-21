#!/usr/bin/env python3
"""
本地摄像头 QR 识别测试 (不依赖 ROS, PC 直接能跑).

用途: 验证 QR PNG 打印出来后能否被 pyzbar 识别, 测距离/角度矩阵.

用法:
  python3 qr_test_local.py                     # 用 /dev/video0 (PC 自带摄像头)
  python3 qr_test_local.py --device 2          # 指定摄像头索引
  python3 qr_test_local.py --image test.png    # 测单张图片

按 q 退出.
"""
import argparse
import sys
import time

try:
    import cv2
    from pyzbar import pyzbar
except ImportError:
    print("装依赖: pip3 install opencv-python pyzbar", file=sys.stderr)
    print("系统包也要: sudo apt install libzbar0", file=sys.stderr)
    sys.exit(1)


def detect_and_draw(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    decoded = pyzbar.decode(gray)
    for obj in decoded:
        x, y, w, h = obj.rect
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        text = obj.data.decode("utf-8")
        cv2.putText(frame, text, (x, y - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    return frame, [o.data.decode("utf-8") for o in decoded]


def run_camera(device: int):
    cap = cv2.VideoCapture(device)
    if not cap.isOpened():
        print(f"打不开摄像头 {device}", file=sys.stderr)
        sys.exit(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    last_log = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame, codes = detect_and_draw(frame)
        if codes and time.time() - last_log > 0.5:
            print("识别到:", codes)
            last_log = time.time()
        cv2.imshow("QR test (press q)", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()


def run_image(path: str):
    img = cv2.imread(path)
    if img is None:
        print(f"读不了 {path}", file=sys.stderr)
        sys.exit(1)
    img, codes = detect_and_draw(img)
    print("识别到:", codes)
    cv2.imshow("QR test", img)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", type=int, default=0)
    ap.add_argument("--image", type=str, default=None)
    args = ap.parse_args()
    if args.image:
        run_image(args.image)
    else:
        run_camera(args.device)
