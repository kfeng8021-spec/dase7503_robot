"""
货架 + 目的区坐标 (单位: m, 以 START 为原点, +x 向前, +y 向左).
Full Plan D4 预定义值, 建图完成后需用卷尺校验 (误差 >5cm 必须修正).
"""

# 货架中心坐标
RACK_POSITIONS = {
    "A": {"x": -0.75, "y":  0.60},
    "B": {"x":  0.15, "y": -0.15},
    "C": {"x":  0.60, "y":  0.65},
    "D": {"x": -0.15, "y": -0.15},
}

# 目的区坐标 + 朝向 (yaw 弧度, 1.5708 = 90°)
DESTINATION = {"x": -0.80, "y": 1.10, "yaw": 1.5708}

# 出发点
START_POINT = {"x": 0.00, "y": 0.00, "yaw": 0.0}

# 搬运顺序 (可按距离优化, 当前按 D->B->A->C 先就近后远)
DELIVERY_ORDER = ["D", "B", "A", "C"]

# 比赛队伍随机串, 必须跟 scripts/qr_generate.py 生成时一致
TEAM_CODE = "4X6M"


def rack_qr_content(rack_id: str) -> str:
    """扫描货架时期望读到的 QR 内容."""
    return f"RACK{rack_id}_{TEAM_CODE}"
