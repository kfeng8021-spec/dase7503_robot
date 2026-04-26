import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String
from cv_bridge import CvBridge
import cv2
from pyzbar import pyzbar
import datetime
import re 
class Group10VisionNode(Node):
    def __init__(self):
        super().__init__('group10_vision_node')
        
        self.subscription = self.create_subscription(Image, '/camera/image_raw', self.process_frame, 10)
        self.publisher_ = self.create_publisher(String, '/qr_result', 10)
        
        self.bridge = CvBridge()
        self.captured_list = []

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
            elif re.match(r"RACK[A-D]_.+", data):
                is_valid = True

            if is_valid:
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
        cv2.destroyAllWindows()

if __name__ == '__main__':
    main()