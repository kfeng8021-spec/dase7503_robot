#!/usr/bin/env python3
"""
Mission FSM - 任务调度主节点.

状态流:
  IDLE -> SCAN_START -> NAV_TO_RACK -> SCAN_RACK -> APPROACH_RACK
    -> LIFT_UP -> NAV_TO_DEST -> LIFT_DOWN -> WAIT_STABLE
    -> CHECK_DONE -> (NAV_TO_RACK | FINISHED)

** 新版比赛要求 (2026-04-20 更新) **:
  每次扫到 QR 必须记录 (工位名, UNIX 时间戳), 比赛结束立即提交 CSV.
  本节点写到 qr_scan_log_<timestamp>.csv.
"""
import csv
import math
import os
import time
from enum import Enum, auto

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node

from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from std_msgs.msg import Int32, String

from our_robot.rack_positions import (
    DELIVERY_ORDER,
    DESTINATION,
    RACK_POSITIONS,
    rack_qr_content,
)


class State(Enum):
    IDLE = auto()
    SCAN_START = auto()
    NAV_TO_RACK = auto()
    SCAN_RACK = auto()
    APPROACH_RACK = auto()
    LIFT_UP = auto()
    NAV_TO_DEST = auto()
    LIFT_DOWN = auto()
    WAIT_STABLE = auto()
    CHECK_DONE = auto()
    FINISHED = auto()


class MissionFSM(Node):
    def __init__(self):
        super().__init__("mission_fsm")

        # ROS interfaces
        self._nav = ActionClient(self, NavigateToPose, "navigate_to_pose")
        self.qr_sub = self.create_subscription(String, "/qr_result", self._qr_cb, 10)
        self.lift_pub = self.create_publisher(Int32, "/lifter_cmd", 10)

        # FSM state
        self.state = State.IDLE
        self.rack_queue = list(DELIVERY_ORDER)
        self.current_rack = None
        self.qr_recv = None
        self.nav_done = False

        # QR timestamp log (新版要求)
        log_dir = os.path.expanduser("~/qr_logs")
        os.makedirs(log_dir, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.log_path = os.path.join(log_dir, f"qr_scan_log_{stamp}.csv")
        self._log_file = open(self.log_path, "w", newline="")
        self._log_writer = csv.writer(self._log_file)
        self._log_writer.writerow(["workstation", "qr_content", "unix_timestamp", "iso_time"])
        self._log_file.flush()
        self.get_logger().info(f"QR scan log -> {self.log_path}")

        # Main loop @ 10 Hz
        self.timer = self.create_timer(0.1, self._loop)
        self.get_logger().info("Mission FSM ready. Waiting for START QR...")

    def _qr_cb(self, msg):
        self.qr_recv = msg.data

    def _log_qr(self, workstation: str, qr_content: str):
        """记录工位扫描时间戳到 CSV."""
        now = time.time()
        self._log_writer.writerow([
            workstation,
            qr_content,
            f"{now:.3f}",
            time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)),
        ])
        self._log_file.flush()
        self.get_logger().info(f"[QR LOG] {workstation}={qr_content} @ {now:.3f}")

    def _nav_to(self, x: float, y: float, yaw: float = 0.0):
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = "map"
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = x
        goal.pose.pose.position.y = y
        goal.pose.pose.orientation.z = math.sin(yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(yaw / 2.0)
        self._nav.wait_for_server()
        fut = self._nav.send_goal_async(goal)
        fut.add_done_callback(self._goal_resp_cb)
        self.nav_done = False

    def _goal_resp_cb(self, fut):
        handle = fut.result()
        if not handle.accepted:
            self.get_logger().error("Nav goal REJECTED")
            self.nav_done = True
            return
        handle.get_result_async().add_done_callback(
            lambda _: setattr(self, "nav_done", True)
        )

    def _lift(self, cmd: int):
        """0 = down, 1 = up."""
        msg = Int32()
        msg.data = cmd
        self.lift_pub.publish(msg)

    def _loop(self):
        s = self.state

        if s is State.IDLE:
            self.state = State.SCAN_START

        elif s is State.SCAN_START:
            if self.qr_recv == "START":
                self._log_qr("START", "START")
                self.qr_recv = None
                self.state = State.NAV_TO_RACK

        elif s is State.NAV_TO_RACK:
            if not self.rack_queue:
                self.state = State.FINISHED
                return
            self.current_rack = self.rack_queue[0]
            pos = RACK_POSITIONS[self.current_rack]
            # 停在货架前 0.3m 扫描距离
            self._nav_to(pos["x"], pos["y"] - 0.30, yaw=math.pi / 2)
            self.state = State.SCAN_RACK

        elif s is State.SCAN_RACK:
            if not self.nav_done:
                return
            expected = rack_qr_content(self.current_rack)
            if self.qr_recv and self.qr_recv == expected:
                self._log_qr(f"RACK_{self.current_rack}", self.qr_recv)
                self.qr_recv = None
                self.state = State.APPROACH_RACK
            elif self.qr_recv:
                # QR 读到但不是期望的, 清除继续等
                self.qr_recv = None

        elif s is State.APPROACH_RACK:
            pos = RACK_POSITIONS[self.current_rack]
            # 贴近到 0.05m 准备插叉
            self._nav_to(pos["x"], pos["y"] - 0.05, yaw=math.pi / 2)
            self.state = State.LIFT_UP

        elif s is State.LIFT_UP:
            if not self.nav_done:
                return
            self._lift(1)
            time.sleep(1.5)  # 伺服到位
            self.state = State.NAV_TO_DEST

        elif s is State.NAV_TO_DEST:
            self._nav_to(DESTINATION["x"], DESTINATION["y"], yaw=DESTINATION["yaw"])
            self.state = State.LIFT_DOWN

        elif s is State.LIFT_DOWN:
            if not self.nav_done:
                return
            self._log_qr("DEST", "END")
            self._lift(0)
            time.sleep(1.5)
            self.state = State.WAIT_STABLE

        elif s is State.WAIT_STABLE:
            # 后退一点脱离货架
            self._nav_to(DESTINATION["x"], DESTINATION["y"] - 0.40, yaw=DESTINATION["yaw"])
            self.state = State.CHECK_DONE

        elif s is State.CHECK_DONE:
            if not self.nav_done:
                return
            self.rack_queue.pop(0)
            self.state = State.NAV_TO_RACK if self.rack_queue else State.FINISHED

        elif s is State.FINISHED:
            self.get_logger().info(
                f"ALL RACKS DELIVERED. Log at {self.log_path}"
            )
            self.timer.cancel()

    def destroy_node(self):
        try:
            self._log_file.close()
        except Exception:
            pass
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = MissionFSM()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
