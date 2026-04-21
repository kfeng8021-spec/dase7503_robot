# 8 min Presentation 大纲 (新版必要内容)

Demo 后要 **8 min 演讲 + 2 min Q&A**, 内容新增市场 / 商业 / 财务部分.

## Slide 结构 (16:9, 建议 12-14 张)

### 1. 封面 (15s)
- Title: **"Smart Wheel-driven Robot for Logistics Applications"**
- 小组编号 + 队员
- 一张机器人渲染图

### 2. Introduction (1 min)
- 物流自动化痛点: 人力成本↑ + 24×7 需求 + 拣选精度
- 我方定位: 小型室内分拣 + 货架搬运 + QR 路径制导
- 一句话卖点: "**小于 30×30×18 cm, 3 分钟内搬 4 个货架, 完全自主**"

### 3. Market Study (1.5 min)  ⭐ 新版必要
- **市场规模**: 全球 AGV/AMR 2024 市场 ~$6.8B, CAGR ~16% (引用 Grand View Research / Markets and Markets)
- **细分场景**: 电商仓 (Amazon Kiva / Geek+) + 3PL + 制造内部物流 + 医院/酒店
- **竞品分析**:
  | 产品 | 场景 | 载重 | 价位 | 优缺点 |
  |---|---|---|---|---|
  | Kiva (Amazon) | 大型仓 | 350 kg | $20k+ | 专有系统封闭 |
  | Geek+ P 系列 | 中型仓 | 600 kg | $15k+ | 重 |
  | 本队 | 小型分拣 / 桌面演示 | 0.5 kg | ~$400 BOM | 轻便, ROS 开放 |
- **差异化**: 全向轮 + 小尺寸 + 开源 ROS 2 + QR 地标**低成本定位**

### 4. Business + Finance Plan (1.5 min)  ⭐ 新版必要
- **目标客户**: 教育机构 / 中小仓库 / 智慧零售店
- **收入模型**:
  - 硬件销售: 套件 $500-800
  - 软件订阅: ROS 2 调度系统 $50/月/台
  - 培训服务: 部署 + 调试一次性费用
- **成本结构** (BOM):
  | 件 | 单价 |
  |---|---|
  | RPi5 8GB | $80 |
  | ESP32-S3 Yahboom | $30 |
  | MS200 LiDAR | $50 |
  | Pi Camera 3 | $25 |
  | 电机 + 驱动 + Mecanum 轮 | $120 |
  | 结构件 + 3D 打印 + 亚克力 | $50 |
  | 电池 7.4V 9900mAh | $30 |
  | **总 BOM** | **≈ $385** |
- **盈亏平衡**: 售 $700, 毛利 $315, 研发成本 $50k 摊 -> 年销 160 台回本
- **融资计划**: 种子轮 $100k -> 开发 2 年 -> A 轮 $500k 放量

### 5. 机器人架构设计 (2 min)
- 双板架构图 (Pi5 上位机 + ESP32 下位机 + DDS-Xrce)
- 模块图: 感知 (LiDAR + Camera) -> 规划 (Nav2 + FSM) -> 执行 (ESP32)
- 创新点 (**关键打分项**):
  - **Mecanum 全向底盘 + OmniMotionModel AMCL**: 无需掉头即可侧移插货架
  - **QR 地标 + LiDAR SLAM 互补定位**: AMCL 漂移时 QR 硬校正
  - **时间戳日志**: 每次扫描 UNIX 时间戳写 CSV, 赛后可审计
  - **硬件冗余**: USB 设备用 udev 绑定, 拔插顺序不影响

### 6. 软件栈 (1 min)
- ROS 2 Jazzy 生态: Nav2 + slam_toolbox + camera_ros + micro-ROS
- 自研节点: `mission_fsm_node.py` (10 状态 FSM), `qr_scanner_node.py` (pyzbar + CLAHE 去噪)
- Python + Arduino C++ 混合开发

### 7. 实测结果 (30s)
- QR 识别矩阵表 (距离 × 角度 × 识别率)
- 导航误差测量
- Demo 时间记录

### 8. Conclusion + Future Work (30s)
- 达成: 尺寸合规 + 自主导航 + QR 定位 + 升降搬运
- 未来: IMU 融合, 多机协同, 更大载重

### 9. Q&A (2 min, 不算 slide)

---

## 分工建议

| Slide | 主讲人候选 |
|---|---|
| 1-2 | 队长 |
| 3-4 市场/商业 | **非技术队员 (MBA / 经济背景优先)** |
| 5-6 架构/软件 | 模块 C 或 D 负责人 |
| 7 结果 | 整机测试负责人 |
| 8 总结 | 队长 |

## 常见 Q&A 准备

- Q: 为什么选 Mecanum 不用差速? → A: 侧移直接插货架, 不用多阶段掉头
- Q: QR 码能被遮挡怎么办? → A: SLAM 持续定位 + AMCL 粒子云兜底
- Q: 掉电恢复? → A: 里程计累积丢失需重定位; `ros2 launch nav2 reinitialize_global_localization`
- Q: 3 分钟搬 4 个可行性? → A: 单次 35-40 秒 × 4 = 140-160 秒, 余 20-40 秒

---

## 演讲 tips

- **8 min 严格**: 排练 3 遍, 每张 slide < 1 min
- **视频替代 Live demo**: 事先录 30 秒无剪辑成功视频作为后备
- 硬件演示用 **A 范围** (全自动) 抢分; 失败立即切 **B 范围** (手动遥控)
