"""
Rack + Start + Destination 坐标 (单位: m).

坐标系 (按 0420 CAD 直觉视图, x 横 y 纵):
  (0, 0, 0) = 场地**左下角**
  +x → 沿短边 (水平, 0 → 2.0m)
  +y → 沿长边 (垂直, 0 → 3.02m)
  yaw 弧度 (0 = +x 朝右, π/2 = +y 朝上 朝destination, π = -x 朝左, -π/2 = -y 朝下 朝start)

数据来源:
  CAD: Materials-20260420/DASE7503 Group Project_QR Code and Gamefield.pdf 图 2 (mm)
  + 用户提供的 Game Field Map.png 图 (黄色矩形中心 = rack 中心)

CAD 图读数置信度:
  HIGH — 尺寸线两端能对上 + 图位置一致
  MED  — 从图 + 部分 CAD 标注估算 (±5cm 误差)
  LOW  — 必须现场卷尺核
"""

# === Zone 中心 (CAD HIGH) ===
# destination_zone: 1400(x) × 800(y), 距图左 300, 距图顶 0
#   x ∈ [0.30, 1.70], y ∈ [2.22, 3.02], 中心 (1.00, 2.62)
# start_zone: 800(x) × 600(y), 距图左 600, 距图底 0
#   x ∈ [0.60, 1.40], y ∈ [0, 0.60], 中心 (1.00, 0.30)
# start_zone 右半 x ∈ [1.00, 1.40], 右半中点 (1.20, 0.30)

# 起点 (START): 用户指定 = "初始 lift 点在 start 区域右半部分的中心" = (1.20, 0.30)
# yaw=π/2 朝 +y (朝 destination_zone 方向)
# ⚠️ 注: 这是 lift 中心位置. 若 base_link != lifter, 还要扣 lifter_offset_x
#   (URDF 假设 lifter 在 base_link 前方 0.18m, 但 base_l 是 placeholder, 待实测)
START_POINT = {"x": 1.20, "y": 0.30, "yaw": 1.5708}

# 目的区 (DESTINATION): destination_zone 中心. mission_fsm 导航到此点 + lift_down 即可.
DESTINATION = {"x": 1.00, "y": 2.62, "yaw": 1.5708}

# === 4 个 Rack ===
# 来源: 用户 Game Field Map.png 图肉眼估 + 0420 CAD 标注 (130/210/350/440/450/650 mm)
# ⚠️ ±5cm 误差. 比赛前卷尺逐个核, 然后把 confidence 升级到 HIGH.
# yaw=π/2 假设 rack QR 朝 +y, 机器人从 -y 方向逼近抬起.
RACK_POSITIONS = {
    "A": {"x": 0.30, "y": 1.87, "yaw": 1.5708, "confidence": "MED"},  # 左上
    "B": {"x": 1.00, "y": 0.97, "yaw": 1.5708, "confidence": "MED"},  # 中下
    "C": {"x": 1.56, "y": 1.51, "yaw": 1.5708, "confidence": "MED"},  # 右中
    "D": {"x": 0.26, "y": 0.91, "yaw": 1.5708, "confidence": "MED"},  # 左下
}

# 搬运顺序 — 比赛前按实际跑速优化.
# 当前 [D,C,A,B] 是初始猜测, 跟 mission_fsm_node 内的常量保持一致.
# 距离参考 (m):
#   start→A=1.81  start→B=0.71  start→C=1.26  start→D=1.13
#   dest→A=1.05   dest→B=1.65   dest→C=1.18   dest→D=1.97
DELIVERY_ORDER = ["D", "C", "A", "B"]

# 比赛队伍随机串, 必须跟 scripts/qr_codes/ 的 PNG 内容一致
TEAM_CODE = "TM10"


def rack_qr_content(rack_id: str) -> str:
    """扫描货架时期望读到的 QR 内容."""
    return f"RACK{rack_id}_{TEAM_CODE}"
