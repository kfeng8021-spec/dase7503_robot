#!/usr/bin/env python3
"""
舵机实时微调工具 — 用于校准升降台 (servo_s2) 和 servo_s1 实际机械极限位.

用法 (在 Pi5 上, micro_ros_agent 必须 active + MCU 主电源 ON):
  source /opt/ros/jazzy/setup.bash
  export ROS_DOMAIN_ID=20
  python3 servo_tune.py            # 默认调 servo_s2 (lifter), 起始 0 度
  python3 servo_tune.py -t /servo_s1
  python3 servo_tune.py -a -45     # 起始角度 -45

按键:
  j / k   : 减 1° / 加 1°
  u / i   : 减 5° / 加 5°
  h / l   : 减 10° / 加 10°
  0       : 归零 (0°)
  t       : 跳到 +20  (servo_s2 实测=落下 DOWN / servo_s1 +20)
  b       : 跳到 -90  (servo_s2 实测=抬起 UP   / servo_s1 极左)
  m       : 跳到 +90  (s1 极右, s2 自动 clip 到 +20)
  1 / 2   : 切换 /servo_s1 ↔ /servo_s2
  r       : 重新发当前角度 (有时丢包)
  q / Ctrl+C : 退出

注意: servo_s2 物理范围 -90..+20 (升降臂), servo_s1 -90..+90 (相机/通用).
脚本会按当前 topic 自动 clip 到合法范围.
"""
import argparse
import sys
import termios
import threading
import time
import tty

import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32


SERVO_RANGE = {
    "/servo_s1": (-90, 90),
    "/servo_s2": (-90, 20),
}


class ServoTuner(Node):
    def __init__(self, topic: str, init_angle: int):
        super().__init__("servo_tune")
        self.topic = topic
        self.angle = self._clip(init_angle)
        self._pub = self.create_publisher(Int32, topic, 10)
        # 给 DDS 一点时间建发现
        time.sleep(0.3)
        self._publish()

    def _clip(self, deg: int) -> int:
        lo, hi = SERVO_RANGE.get(self.topic, (-90, 90))
        return max(lo, min(hi, int(deg)))

    def set_topic(self, topic: str):
        if topic == self.topic:
            return
        self.topic = topic
        self._pub.destroy()
        self._pub = self.create_publisher(Int32, topic, 10)
        time.sleep(0.2)
        self.angle = self._clip(self.angle)
        self._publish()

    def adjust(self, delta: int):
        self.angle = self._clip(self.angle + delta)
        self._publish()

    def jump(self, deg: int):
        self.angle = self._clip(deg)
        self._publish()

    def _publish(self):
        m = Int32()
        m.data = self.angle
        self._pub.publish(m)
        lo, hi = SERVO_RANGE.get(self.topic, (-90, 90))
        # 在终端覆盖式打印, 不滚屏
        sys.stdout.write(
            f"\r[{self.topic}]  angle = {self.angle:+4d}°   "
            f"(range {lo:+d} .. {hi:+d})       "
        )
        sys.stdout.flush()


def _getch() -> str:
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _key_loop(node: ServoTuner):
    while rclpy.ok():
        try:
            c = _getch()
        except Exception:
            break
        if c in ("q", "\x03"):
            rclpy.shutdown()
            break
        elif c == "j":
            node.adjust(-1)
        elif c == "k":
            node.adjust(+1)
        elif c == "u":
            node.adjust(-5)
        elif c == "i":
            node.adjust(+5)
        elif c == "h":
            node.adjust(-10)
        elif c == "l":
            node.adjust(+10)
        elif c == "0":
            node.jump(0)
        elif c == "t":
            node.jump(20)
        elif c == "b":
            node.jump(-90)
        elif c == "m":
            node.jump(90)
        elif c == "r":
            node._publish()
        elif c == "1":
            node.set_topic("/servo_s1")
        elif c == "2":
            node.set_topic("/servo_s2")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-t", "--topic", default="/servo_s2", choices=list(SERVO_RANGE.keys()))
    p.add_argument("-a", "--angle", type=int, default=0, help="起始角度, 默认 0")
    args = p.parse_args()

    rclpy.init()
    node = ServoTuner(args.topic, args.angle)
    sys.stdout.write("\nKeys: j/k ±1  u/i ±5  h/l ±10  0=zero  t=+20  b=-90  m=+90  1/2=switch  r=resend  q=quit\n")
    sys.stdout.flush()

    t = threading.Thread(target=_key_loop, args=(node,), daemon=True)
    t.start()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\n")
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
