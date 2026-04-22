#!/usr/bin/env python3
"""
YOLO v8 ONNX Detector (Tutorial 7 第 4 节教的加分项).

订阅 /camera/image_raw/compressed, onnxruntime 跑 yolov8n.onnx 推理,
标注后发布到 /yolo/detections/compressed.

模型: yolov8n.onnx (存 ros_pkg/our_robot/models/yolov8n.onnx)
类别: COCO 80 类.

用途:
  - 识别赛场静态障碍 (chair, bottle 等)
  - 识别起点/终点标志 (如果用 person 或特定物体做 landmark)
  - 演讲加分项: "我们用 YOLO 增强场景感知"

依赖: pip install onnxruntime opencv-python numpy==1.26.4
"""
import os

import cv2
import numpy as np
import rclpy
from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from sensor_msgs.msg import CompressedImage

try:
    import onnxruntime as ort
except ImportError:
    ort = None

# COCO 80 类
COCO_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep",
    "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
    "sports ball", "kite", "baseball bat", "baseball glove", "skateboard",
    "surfboard", "tennis racket", "bottle", "wine glass", "cup", "fork",
    "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv",
    "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave",
    "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
    "scissors", "teddy bear", "hair drier", "toothbrush"
]


def _find_model():
    """按 Tutorial 7 第 9 页 fallback 逻辑找模型."""
    candidates = [
        os.path.expanduser("~/ros2_ws/src/our_robot/models/yolov8n.onnx"),
        os.path.expanduser("~/dase7503_robot/ros_pkg/our_robot/models/yolov8n.onnx"),
    ]
    try:
        share_dir = get_package_share_directory("our_robot")
        candidates.insert(0, os.path.join(share_dir, "models", "yolov8n.onnx"))
    except Exception:
        pass
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


class YOLOONNXDetector(Node):
    def __init__(self):
        super().__init__("yolo_detector")
        self.declare_parameter("confidence_threshold", 0.5)
        self.declare_parameter("iou_threshold", 0.45)
        self.declare_parameter("show_window", False)
        self.declare_parameter("input_size", 640)

        self.conf_th = self.get_parameter("confidence_threshold").value
        self.iou_th = self.get_parameter("iou_threshold").value
        self.show = self.get_parameter("show_window").value
        self.input_size = self.get_parameter("input_size").value

        if ort is None:
            self.get_logger().error("onnxruntime not installed. pip install onnxruntime")
            raise RuntimeError("onnxruntime missing")

        model_path = _find_model()
        if not model_path:
            self.get_logger().error(
                "yolov8n.onnx not found. Put it at ros_pkg/our_robot/models/yolov8n.onnx"
            )
            raise FileNotFoundError("yolov8n.onnx")

        self.get_logger().info(f"Loading ONNX: {model_path}")
        self.session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [o.name for o in self.session.get_outputs()]

        qos = QoSProfile(
            depth=1,
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
        )
        self.sub = self.create_subscription(
            CompressedImage, "/camera/image_raw/compressed", self._cb, qos
        )
        self.pub = self.create_publisher(
            CompressedImage, "/yolo/detections/compressed", qos
        )
        self.get_logger().info("YOLO detector ready.")

    def _preprocess(self, img):
        x = cv2.resize(img, (self.input_size, self.input_size))
        x = cv2.cvtColor(x, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        x = np.transpose(x, (2, 0, 1))
        return np.expand_dims(x, 0)

    def _postprocess(self, outputs, orig_shape):
        preds = np.squeeze(outputs[0]).T  # (8400, 84) for YOLOv8
        boxes = preds[:, :4]
        scores = preds[:, 4:]
        cls_ids = np.argmax(scores, axis=1)
        conf = np.max(scores, axis=1)
        mask = conf > self.conf_th
        boxes, conf, cls_ids = boxes[mask], conf[mask], cls_ids[mask]

        orig_h, orig_w = orig_shape[:2]
        sx, sy = orig_w / self.input_size, orig_h / self.input_size
        xyxy = []
        for cx, cy, w, h in boxes:
            xyxy.append([
                int((cx - w / 2) * sx), int((cy - h / 2) * sy),
                int((cx + w / 2) * sx), int((cy + h / 2) * sy),
            ])
        if xyxy:
            idx = cv2.dnn.NMSBoxes(xyxy, conf.tolist(), self.conf_th, self.iou_th)
            if len(idx) > 0:
                idx = idx.flatten()
                return [xyxy[i] for i in idx], conf[idx], cls_ids[idx]
        return [], np.array([]), np.array([])

    def _draw(self, img, boxes, confs, cls_ids):
        for (x1, y1, x2, y2), c, k in zip(boxes, confs, cls_ids):
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f"{COCO_CLASSES[int(k)]}: {c:.2f}"
            cv2.putText(img, label, (x1, max(0, y1 - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
        return img

    def _cb(self, msg: CompressedImage):
        try:
            np_arr = np.frombuffer(msg.data, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if frame is None:
                return
            x = self._preprocess(frame)
            outs = self.session.run(self.output_names, {self.input_name: x})
            boxes, confs, cls_ids = self._postprocess(outs, frame.shape)
            annotated = self._draw(frame.copy(), boxes, confs, cls_ids)

            if len(boxes) > 0:
                labels = ", ".join(f"{COCO_CLASSES[int(k)]}: {c:.2f}"
                                    for c, k in zip(confs, cls_ids))
                self.get_logger().info(f"Detected: {labels}")

            out = CompressedImage()
            out.header = msg.header
            out.format = "jpeg"
            out.data = np.array(cv2.imencode(".jpg", annotated)[1]).tobytes()
            self.pub.publish(out)

            if self.show:
                cv2.imshow("YOLO ONNX Detection", annotated)
                cv2.waitKey(1)
        except Exception as e:
            self.get_logger().error(f"YOLO error: {e}")


def main(args=None):
    rclpy.init(args=args)
    try:
        node = YOLOONNXDetector()
        rclpy.spin(node)
    except (KeyboardInterrupt, FileNotFoundError, RuntimeError):
        pass
    finally:
        if "node" in locals():
            node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
