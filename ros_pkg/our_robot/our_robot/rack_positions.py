"""
Rack + Start + Destination 坐标 (单位: m).

坐标系跟 scripts/generate_static_map.py 生成的地图一致:
  (0, 0, 0) = 场地**左下角**
  +x → 沿长边 3.02m
  +y → 沿短边 2.0m
  yaw 弧度 (0 = +x, π/2 = +y, 即"朝北")

数据来源 (优先级): 课程 CAD 图 > Full Plan 估计 > 现场卷尺.
PDF: Materials-20260420/DASE7503 Group Project_QR Code and Gamefield.pdf 图 2
     (CAD 俯视图, 所有尺寸 mm)

CAD 图读数置信度:
  HIGH  — 尺寸线两端都能对上
  MED   — 推断 (例如用"中心间距" 650 推导另一货架 X)
  LOW   — 尺寸组合解释有多种可能, 需卷尺核
  CAD 没给 — START / DEST 纯粹按物理照片位置估计, 必须卷尺校
"""

# 4 个货架中心坐标, 朝向 (yaw) 指 QR 扫描时机器人相机应对准的方向.
# 这里假设所有货架 QR 朝 +y (即机器人从 -y 方向逼近, yaw=π/2).
# Rack 1 (上左中): CAD 400mm 水平 + 350mm 垂直 两尺寸直接给, HIGH
# Rack 2 (上右):   650mm 中心间距推导 X, 210mm 垂直直接给, Y HIGH X MED
# Rack 3 (中右):   650/440 组合, LOW
# Rack 4 (下中左): 450/350/130 组合, LOW
RACK_POSITIONS = {
    "A": {"x": 1.20, "y": 1.65, "yaw": 1.5708, "confidence": "HIGH"},  # 上左中
    "B": {"x": 1.85, "y": 1.79, "yaw": 1.5708, "confidence": "MED"},   # 上右
    "C": {"x": 1.85, "y": 0.44, "yaw": 1.5708, "confidence": "LOW"},   # 中右
    "D": {"x": 1.10, "y": 0.17, "yaw": 1.5708, "confidence": "LOW"},   # 下中左
}

# 目的区 (destination) — CAD 没画, 按物理照片估计蓝垫位置在右下角
# ⚠️ 必须卷尺实测
DESTINATION = {"x": 2.70, "y": 0.30, "yaw": 0.0}

# 起点 (START) — CAD 没画, 按物理照片估计绿垫位置在左下角
# ⚠️ 必须卷尺实测
START_POINT = {"x": 0.30, "y": 0.30, "yaw": 0.0}

# 搬运顺序 — 当前按距离估计 "先近后远" (D 最近, B 最远)
# 先跑起来后按实际时间优化
DELIVERY_ORDER = ["D", "C", "A", "B"]

# 比赛队伍随机串, 必须跟 scripts/qr_generate.py 生成时一致
# ⚠️ 队伍选定 4 位 code 后改成真值
TEAM_CODE = "4X6M"


def rack_qr_content(rack_id: str) -> str:
    """扫描货架时期望读到的 QR 内容."""
    return f"RACK{rack_id}_{TEAM_CODE}"
