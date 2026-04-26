#!/usr/bin/env python3
"""
Manual Mission Node - B range 手动模式下也要记 QR 时间戳.

当队员用 teleop_twist_keyboard 手动驾驶机器人时, 这个节点在后台:
  - 监听 /qr_result, 每次确认扫到新 QR 就写到 CSV
  - 监听键盘命令发布 /servo_s2 (u=up 角度 20, d=down 角度 -90, 工厂 FW)

用法:
  ros2 launch our_robot teleop_mode.launch.py
  # 另一终端
  ros2 run teleop_twist_keyboard teleop_twist_keyboard
  # 第三终端 (按 u/d 控制升降)
  ros2 run our_robot manual_mission_node
"""
import csv
import os
import sys
import termios
import threading
import time
import tty

import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32, String


LIFT_UP_DEG = -90     # servo_s2 抬起位 (实测: -90 → 叉臂上升)
LIFT_DOWN_DEG = 20    # servo_s2 落下位 (实测: +20 → 叉臂下降, 钻 rack 用此位)

HELP = f"""
Manual Mission - QR 时间戳记录 + 升降控制
  u : 叉臂抬起 (/servo_s2 = {LIFT_UP_DEG})
  d : 叉臂放下 (/servo_s2 = {LIFT_DOWN_DEG})
  s : 打印当前日志路径
  q : 退出
(运动由另一个终端的 teleop_twist_keyboard 控制)
"""


class ManualMissionNode(Node):
    def __init__(self):
        super().__init__("manual_mission")
        self.qr_sub = self.create_subscription(String, "/qr_result", self._qr_cb, 10)
        self.lift_pub = self.create_publisher(Int32, "/servo_s2", 10)

        log_dir = os.path.expanduser("~/qr_logs")
        os.makedirs(log_dir, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.log_path = os.path.join(log_dir, f"manual_qr_log_{stamp}.csv")
        self._log_file = open(self.log_path, "w", newline="")
        self._log_writer = csv.writer(self._log_file)
        self._log_writer.writerow(["qr_content", "unix_timestamp", "iso_time"])
        self._log_file.flush()

        self.seen = set()
        self.get_logger().info(HELP.strip())
        self.get_logger().info(f"Log -> {self.log_path}")

    def _qr_cb(self, msg: String):
        content = msg.data
        # 去重: 同一 QR 短时间重复扫到只记第一次
        key = (content, int(time.time() / 5))  # 5 秒窗口
        if key in self.seen:
            return
        self.seen.add(key)
        now = time.time()
        self._log_writer.writerow([
            content, f"{now:.3f}",
            time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)),
        ])
        self._log_file.flush()
        self.get_logger().info(f"[LOGGED] {content} @ {now:.3f}")

    def lift(self, angle_deg: int):
        m = Int32()
        m.data = int(angle_deg)
        self.lift_pub.publish(m)
        label = "UP" if angle_deg > 0 else "DOWN"
        self.get_logger().info(f"/servo_s2 = {angle_deg} ({label})")

    def destroy_node(self):
        try:
            self._log_file.close()
        except Exception:
            pass
        super().destroy_node()


def _getch() -> str:
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _key_thread(node: ManualMissionNode):
    while rclpy.ok():
        try:
            c = _getch()
        except Exception:
            break
        if c == "u":
            node.lift(LIFT_UP_DEG)
        elif c == "d":
            node.lift(LIFT_DOWN_DEG)
        elif c == "s":
            node.get_logger().info(f"Log path: {node.log_path}")
        elif c in ("q", "\x03"):   # q or Ctrl-C
            rclpy.shutdown()
            break


def main(args=None):
    rclpy.init(args=args)
    node = ManualMissionNode()
    t = threading.Thread(target=_key_thread, args=(node,), daemon=True)
    t.start()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
