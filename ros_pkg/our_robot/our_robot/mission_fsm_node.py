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

from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped
from nav2_msgs.action import NavigateToPose
from std_msgs.msg import Int32, String

from our_robot.rack_positions import (
    DELIVERY_ORDER,
    DESTINATION,
    RACK_POSITIONS,
    START_POINT,
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
    SCAN_END = auto()    # 4 个 rack 搬完后, 在 destination 扫 END QR
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

        # 状态变量必须在 create_subscription 之前 init — 否则 _qr_cb 收到第一条消息时
        # _qr_seen 等还不存在 (我们 init 里有 spin_once 等 AMCL discovery, 期间 callback 会跑).
        self.qr_recv = None
        self._qr_seen = set()

        # ROS interfaces. lift 走 /servo_s2 (工厂 FW), 原 /lifter_cmd 是团队 PIO 残留.
        self._nav = ActionClient(self, NavigateToPose, "navigate_to_pose")
        self.qr_sub = self.create_subscription(String, "/qr_result", self._qr_cb, 10)
        self.lift_pub = self.create_publisher(Int32, "/servo_s2", 10)
        # AMCL 初始位姿注入. 必须在 wait_for_server 之前 publish — 否则:
        #   controller_server.activate() 等 map frame → map frame 来自 AMCL → AMCL 等 /initialpose
        #   → mission_fsm wait_for_server (60s) 内 controller_server 超时 abort
        # 所以 init 一启动就 publish, 不等扫到 START QR.
        self.init_pose_pub = self.create_publisher(PoseWithCovarianceStamped, "/initialpose", 10)
        self._init_pose_sent = False

        # spin_once 让 publisher 跟 AMCL discovery 一下, 再 publish (确保不丢)
        self.get_logger().info("Publishing initial pose to AMCL (pre-Nav2-activate)...")
        for _ in range(20):
            rclpy.spin_once(self, timeout_sec=0.1)
            if self.init_pose_pub.get_subscription_count() > 0:
                break
        self._publish_initial_pose()
        self._init_pose_sent = True

        # Nav2 ActionServer 预热 (一次性阻塞, 放 init 避免阻塞 timer callback)
        self.get_logger().info("Waiting for navigate_to_pose action server...")
        if not self._nav.wait_for_server(timeout_sec=30.0):
            self.get_logger().error("navigate_to_pose server not available after 30s")
        else:
            self.get_logger().info("Nav2 action server ready.")

        # FSM state (qr_recv / _qr_seen 已在 init 早期 set)
        self.state = State.IDLE
        self.state_t0 = time.time()       # 进入当前状态的时间 (用于非阻塞计时)
        self.rack_queue = list(DELIVERY_ORDER)
        self.current_rack = None
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
        # 路上扫到任何 QR 都立即写 CSV (5s 窗口去重, 跟 manual_mission_node 一致),
        # 满足比赛 "扫到的 QR 必须记时间戳" 要求. 状态机另外的 _log_qr 调用会
        # 加 workstation 上下文 (START/RACK_X/END), 跟 DETECT 行可共存.
        key = (msg.data, int(time.time() / 5))
        if key not in self._qr_seen:
            self._qr_seen.add(key)
            self._log_qr("DETECT", msg.data)

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

    def _publish_initial_pose(self):
        """SCAN_START 时 publish 一次 /initialpose 把 START_POINT 注入 AMCL."""
        msg = PoseWithCovarianceStamped()
        msg.header.frame_id = "map"
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.pose.pose.position.x = float(START_POINT["x"])
        msg.pose.pose.position.y = float(START_POINT["y"])
        yaw = float(START_POINT["yaw"])
        msg.pose.pose.orientation.z = math.sin(yaw / 2.0)
        msg.pose.pose.orientation.w = math.cos(yaw / 2.0)
        # 协方差: 位置 ±5cm 信任, yaw ±5° 信任 (AMCL 期望 6x6 row-major, 下标 [0]=xx, [7]=yy, [35]=yaw)
        msg.pose.covariance[0] = 0.0025   # x var = (0.05m)^2
        msg.pose.covariance[7] = 0.0025   # y var
        msg.pose.covariance[35] = 0.00762  # yaw var = (5°)^2 in rad^2
        self.init_pose_pub.publish(msg)
        self.get_logger().info(
            f"📍 Sent /initialpose to AMCL: ({START_POINT['x']}, {START_POINT['y']}, yaw={yaw:.3f})"
        )

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
            # 启动时升降机可能在 UP 位置 (上次任务残留 / 测试残留),
            # 先发 LIFT_DOWN 让叉臂落到 +20 位置, 否则钻 rack 会撞顶板.
            if not self._lift_cmd_sent:
                self._lift(self.LIFT_DOWN_DEG)
                self._lift_cmd_sent = True
                self._lift_t0 = time.time()
                self.get_logger().info("🔧 Initial LIFT_DOWN — clearing fork to +20°")
                return
            if time.time() - self._lift_t0 >= self.LIFT_DWELL_SEC:
                self._enter(State.SCAN_START)

        elif s is State.SCAN_START:
            if self.qr_recv == "START":
                self._log_qr("START", "START")
                self.mission_t0 = time.time()  # 3min 计时开始
                self.get_logger().info("⏱️ Mission timer started (3 min budget).")
                # 注入初始位姿到 AMCL — 让 Nav2 知道我在 START_POINT
                if not self._init_pose_sent:
                    self._publish_initial_pose()
                    self._init_pose_sent = True
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
                # 删假 END log: 真扫 END 在 SCAN_END 状态. _qr_cb 路上扫到 END
                # 时也会自动 log (DETECT, END).
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
            if self.rack_queue:
                self._enter(State.NAV_TO_RACK)
            else:
                # 4 个 rack 都搬完, 去 destination 扫 END QR (0420 spec 要求)
                self.qr_recv = None
                self._enter(State.SCAN_END)

        elif s is State.SCAN_END:
            # 已经在 destination 区域 (CHECK_DONE 是 WAIT_STABLE 后退的位置)
            # 等 END QR. _qr_cb 路上扫到也会 auto-log, 这里的 log 是状态机事件.
            if self.qr_recv == "END":
                self._log_qr("END", "END")
                self.qr_recv = None
                self._enter(State.FINISHED)
                return
            # 10s 没扫到 END 强制 finish + warn (mission 不能卡死)
            if self._in_state_for() >= self.SCAN_TIMEOUT_SEC:
                self.get_logger().warn(
                    "SCAN_END timeout — END QR not detected, forcing FINISHED"
                )
                self._log_qr("END", "TIMEOUT_NO_QR")
                self._enter(State.FINISHED)

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
