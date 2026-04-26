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
    LIFT_DWELL_SEC = 1.5       # 升降机构伺服到位时间
    SCAN_TIMEOUT_SEC = 10.0    # 扫不到 QR 的超时
    MAX_SCAN_RETRIES = 2       # 单个货架最多重扫次数
    MISSION_BUDGET_SEC = 3 * 60  # 比赛 3 分钟硬上限 (2026-04-20 Group Project 规则最新版)

    # servo_s2 升降角度 (-90..20 度). 比赛前用 manual_mission_node 校准到实际机械位.
    LIFT_UP_DEG = -90    # 叉臂抬起 (托住货架, 实测: -90 → 升)
    LIFT_DOWN_DEG = 20   # 叉臂放下 (货架落地, 实测: +20 → 降, 钻 rack 用此位)

    def __init__(self):
        super().__init__("mission_fsm")

        # ROS interfaces. lift 走 /servo_s2 (工厂 FW), 原 /lifter_cmd 是团队 PIO 残留.
        self._nav = ActionClient(self, NavigateToPose, "navigate_to_pose")
        self.qr_sub = self.create_subscription(String, "/qr_result", self._qr_cb, 10)
        self.lift_pub = self.create_publisher(Int32, "/servo_s2", 10)

        # Nav2 ActionServer 预热 (一次性阻塞, 放 init 避免阻塞 timer callback)
        self.get_logger().info("Waiting for navigate_to_pose action server...")
        if not self._nav.wait_for_server(timeout_sec=30.0):
            self.get_logger().error("navigate_to_pose server not available after 30s")
        else:
            self.get_logger().info("Nav2 action server ready.")

        # FSM state
        self.state = State.IDLE
        self.state_t0 = time.time()       # 进入当前状态的时间 (用于非阻塞计时)
        self.rack_queue = list(DELIVERY_ORDER)
        self.current_rack = None
        self.qr_recv = None
        self.nav_done = False
        self._lift_cmd_sent = False       # 保证 lift 命令只发一次
        self._lift_t0 = 0.0               # 发 lift 后开始计时
        self._scan_retries = 0            # 当前货架扫描已重试次数

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

        # 比赛全局计时器 (8 分钟) — 在 SCAN_START 扫到 START QR 时开始
        self.mission_t0 = None

        # Main loop @ 10 Hz
        self.timer = self.create_timer(0.1, self._loop)
        self.get_logger().info("Mission FSM ready. Waiting for START QR...")

    def _enter(self, new_state):
        """集中切状态 + 重置计时 + 清理计时 flag."""
        self.state = new_state
        self.state_t0 = time.time()
        self._lift_cmd_sent = False

    def _in_state_for(self) -> float:
        return time.time() - self.state_t0

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
        # 不在此处 wait_for_server: init 里已预热, 这里阻塞会卡死 timer callback.
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = "map"
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = x
        goal.pose.pose.position.y = y
        goal.pose.pose.orientation.z = math.sin(yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(yaw / 2.0)
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

    def _lift(self, angle_deg: int):
        """发 /servo_s2 servo 角度 (-90..20). LIFT_UP_DEG = 托起, LIFT_DOWN_DEG = 落下."""
        msg = Int32()
        msg.data = int(angle_deg)
        self.lift_pub.publish(msg)

    def _loop(self):
        s = self.state

        # 全局 8 分钟硬上限 — 计时从扫到 START QR 开始
        if self.mission_t0 is not None and s not in (State.IDLE, State.SCAN_START, State.FINISHED):
            if time.time() - self.mission_t0 >= self.MISSION_BUDGET_SEC:
                self.get_logger().error(
                    f"⏰ MISSION BUDGET 8min EXCEEDED — forcing FINISHED (delivered={len(DELIVERY_ORDER)-len(self.rack_queue)})"
                )
                self._log_qr("TIMEOUT", f"remaining={self.rack_queue}")
                self._enter(State.FINISHED)
                return

        if s is State.IDLE:
            self._enter(State.SCAN_START)

        elif s is State.SCAN_START:
            if self.qr_recv == "START":
                self._log_qr("START", "START")
                self.mission_t0 = time.time()  # 8min 计时开始
                self.get_logger().info("⏱️ Mission timer started (8 min budget).")
                self.qr_recv = None
                self._enter(State.NAV_TO_RACK)

        elif s is State.NAV_TO_RACK:
            if not self.rack_queue:
                self._enter(State.FINISHED)
                return
            self.current_rack = self.rack_queue[0]
            self._scan_retries = 0
            pos = RACK_POSITIONS[self.current_rack]
            # 停在货架前 0.3m 扫描距离
            self._nav_to(pos["x"], pos["y"] - 0.30, yaw=math.pi / 2)
            self._enter(State.SCAN_RACK)

        elif s is State.SCAN_RACK:
            if not self.nav_done:
                return
            expected = rack_qr_content(self.current_rack)
            if self.qr_recv and self.qr_recv == expected:
                self._log_qr(f"RACK_{self.current_rack}", self.qr_recv)
                self.qr_recv = None
                self._enter(State.APPROACH_RACK)
                return
            if self.qr_recv:
                # QR 读到但不是期望的, 清除继续等
                self.qr_recv = None
            # 超时回退: 后退重试或跳过这个货架
            if self._in_state_for() >= self.SCAN_TIMEOUT_SEC:
                self._scan_retries += 1
                if self._scan_retries <= self.MAX_SCAN_RETRIES:
                    self.get_logger().warn(
                        f"SCAN_RACK timeout on {self.current_rack}, retry "
                        f"{self._scan_retries}/{self.MAX_SCAN_RETRIES} (backoff 0.15m)"
                    )
                    pos = RACK_POSITIONS[self.current_rack]
                    # 后退 0.15m 重新逼近重扫
                    self._nav_to(pos["x"], pos["y"] - 0.45, yaw=math.pi / 2)
                    # 继续停留 SCAN_RACK, 重置计时窗口
                    self.state_t0 = time.time()
                else:
                    self.get_logger().error(
                        f"SCAN_RACK failed on {self.current_rack} after retries — skipping"
                    )
                    self._log_qr(f"RACK_{self.current_rack}", "SKIPPED_TIMEOUT")
                    self.rack_queue.pop(0)
                    self._enter(State.NAV_TO_RACK)

        elif s is State.APPROACH_RACK:
            pos = RACK_POSITIONS[self.current_rack]
            # 贴近到 0.05m 准备插叉
            self._nav_to(pos["x"], pos["y"] - 0.05, yaw=math.pi / 2)
            self._enter(State.LIFT_UP)

        elif s is State.LIFT_UP:
            if not self.nav_done:
                return
            if not self._lift_cmd_sent:
                self._lift(self.LIFT_UP_DEG)
                self._lift_cmd_sent = True
                self._lift_t0 = time.time()
                return
            # 非阻塞等伺服到位
            if time.time() - self._lift_t0 >= self.LIFT_DWELL_SEC:
                self._enter(State.NAV_TO_DEST)

        elif s is State.NAV_TO_DEST:
            self._nav_to(DESTINATION["x"], DESTINATION["y"], yaw=DESTINATION["yaw"])
            self._enter(State.LIFT_DOWN)

        elif s is State.LIFT_DOWN:
            if not self.nav_done:
                return
            if not self._lift_cmd_sent:
                self._log_qr("DEST", "END")
                self._lift(self.LIFT_DOWN_DEG)
                self._lift_cmd_sent = True
                self._lift_t0 = time.time()
                return
            if time.time() - self._lift_t0 >= self.LIFT_DWELL_SEC:
                self._enter(State.WAIT_STABLE)

        elif s is State.WAIT_STABLE:
            # 后退一点脱离货架
            self._nav_to(DESTINATION["x"], DESTINATION["y"] - 0.40, yaw=DESTINATION["yaw"])
            self._enter(State.CHECK_DONE)

        elif s is State.CHECK_DONE:
            if not self.nav_done:
                return
            self.rack_queue.pop(0)
            self._enter(State.NAV_TO_RACK if self.rack_queue else State.FINISHED)

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
