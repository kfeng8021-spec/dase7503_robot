import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String
from cv_bridge import CvBridge
import cv2
from pyzbar import pyzbar
import datetime
import os
import re
import time

# 启动时一次性检测 GUI 环境: 有 X11 (DISPLAY) 或 Qt offscreen 平台时才跑 cv2.imshow,
# 否则 SSH 远程启会因 Qt xcb 找不到 display 直接 abort (exit -6)
_HAS_GUI = bool(os.environ.get('DISPLAY')) or os.environ.get('QT_QPA_PLATFORM') == 'offscreen'


class Group10VisionNode(Node):
    def __init__(self):
        super().__init__('group10_vision_node')

        self.subscription = self.create_subscription(Image, '/camera/image_raw', self.process_frame, 10)
        self.publisher_ = self.create_publisher(String, '/qr_result', 10)

        self.bridge = CvBridge()
        self.captured_list = []
        self.seen = set()  # 5 秒窗口去重 (data, int(time/5)), 跟 manual_mission_node 一致

        self.get_logger().info('--- Group 10 Flexible Vision Node Started ---')

    def process_frame(self, msg):
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, "bgr8")
        except Exception as e:
            self.get_logger().error(f"Image conversion failed: {e}")
            return

        barcodes = pyzbar.decode(frame)

        for barcode in barcodes:
            data = barcode.data.decode("utf-8")
    
            is_valid = False
            if data in ["START", "END"]:
                is_valid = True
            elif re.match(r"RACK[A-D]_.+", data):  # 老师赛事 QR 格式: RACK[A-D]_<老师分配的随机代码>, 不限定具体代码
                is_valid = True

            if is_valid:
                # 5 秒窗口去重: 同一个 QR 在 5 秒内只 publish 一次, 避免 30 fps 刷屏 mission_fsm
                key = (data, int(time.time() / 5))
                if key in self.seen:
                    continue
                self.seen.add(key)

                (x, y, w, h) = barcode.rect
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(frame, data, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)


                result_msg = String()
                result_msg.data = data
                self.publisher_.publish(result_msg)
                self.get_logger().info(f'Detected: {data}')


                if data not in self.captured_list:
                    timestamp = datetime.datetime.now().strftime("%H%M%S")
                    filename = f"G10_Evidence_{data}_{timestamp}.png"
                    cv2.imwrite(filename, frame)
                    self.get_logger().info(f'Saved Evidence: {filename}')
                    self.captured_list.append(data)

        if _HAS_GUI:
            cv2.imshow("Group 10 Debug", frame)
            cv2.waitKey(1)

def main(args=None):
    rclpy.init(args=args)
    node = Group10VisionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
        if _HAS_GUI:
            cv2.destroyAllWindows()

if __name__ == '__main__':
    main()