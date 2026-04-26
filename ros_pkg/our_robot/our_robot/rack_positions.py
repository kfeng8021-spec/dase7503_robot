"""
Rack + Start + Destination 坐标 (单位: m).

坐标系 (按 0420 CAD 直觉视图, x 横 y 纵):
  (0, 0, 0) = 场地**左下角**
  +x → 沿短边 (水平, 0 → 2.000m)
  +y → 沿长边 (垂直, 0 → 3.020m)
  yaw 弧度 (0 = +x 朝右, π/2 = +y 朝上 朝destination, π = -x 朝左, -π/2 = -y 朝下 朝start)

数据来源: 用户从示意图精确测量 (2026-04-26), ±20mm 容差.
"""

# === 场地尺寸 ===
FIELD_WIDTH = 2.000   # x 方向 (mm: 2000)
FIELD_HEIGHT = 3.020  # y 方向 (mm: 3020)

# === Zone (用户实测) ===
# START zone:        中心 (1.000, 0.295), 800×600 mm, 角点 (0.601, 0)~(1.399, 0.595)
# DESTINATION zone:  中心 (1.000, 2.626), 1410×800 mm, 角点 (0.294, 2.224)~(1.706, 3.020)

# 起点 (START): 用户实测 — 小车中心放在 start_zone 几何中心,
# 朝向沿 zone 对角线 (中心朝右上角立柱) = atan2(0.300, 0.400) ≈ 0.6435 rad
# zone 范围 x[0.601, 1.399] y[0, 0.595], 中心 (1.000, 0.295)
START_POINT = {"x": 1.000, "y": 0.295, "yaw": 0.6435}

# 目的区 (DESTINATION): destination_zone 中心
DESTINATION = {"x": 1.000, "y": 2.626, "yaw": 1.5708}

# === 4 个 Rack (用户实测精确值, ±20mm) ===
# Rack 物理尺寸 (顶视投影): 364×144 mm
# yaw=π/2 假设 rack 长边 364mm 沿 x, QR 朝 +y, 机器人从 -y 方向逼近抬起.
RACK_POSITIONS = {
    "A": {"x": 0.530, "y": 1.890, "yaw": 1.5708, "confidence": "HIGH"},  # 左上
    "B": {"x": 1.389, "y": 1.180, "yaw": 1.5708, "confidence": "HIGH"},  # 中下
    "C": {"x": 1.693, "y": 1.688, "yaw": 1.5708, "confidence": "HIGH"},  # 右中
    "D": {"x": 0.378, "y": 1.081, "yaw": 1.5708, "confidence": "HIGH"},  # 左下
}

# Rack 物理尺寸 (用于 costmap 软避让 + 接近半径估算).
RACK_SIZE_X = 0.364
RACK_SIZE_Y = 0.144

# 搬运顺序 — 比赛前按实际跑速优化.
# 当前 [D,C,A,B] 是初始猜测, 跟 mission_fsm_node 内的常量保持一致.
DELIVERY_ORDER = ["D", "C", "A", "B"]

# 比赛队伍随机串, 必须跟 scripts/qr_codes/ 的 PNG 内容一致
TEAM_CODE = "TM10"


def rack_qr_content(rack_id: str) -> str:
    """扫描货架时期望读到的 QR 内容."""
    return f"RACK{rack_id}_{TEAM_CODE}"
