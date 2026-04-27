#!/usr/bin/env python3
"""
把 scripts/qr_codes/ 里的 6 张 QR PNG 排到一张 A4 纸上, 输出 PDF + PNG.

A4 竖版 (210×297 mm @ 300 DPI = 2480×3508 px):
  2 列 × 3 行, 每张 QR 约 85×85 mm (够大, 手机 / 机器人相机都能扫到).
  每张下面有文字标签, 方便剪下来贴对应位置.

用法:
  python3 scripts/qr_print_layout.py
  # 输出: scripts/qr_codes/print_sheet.pdf + .png
"""
import os
import sys

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("pip3 install --user pillow", file=sys.stderr)
    sys.exit(1)

DPI = 300
A4_W_MM, A4_H_MM = 210, 297
A4_W_PX = int(A4_W_MM / 25.4 * DPI)  # 2480
A4_H_PX = int(A4_H_MM / 25.4 * DPI)  # 3508

QR_CELL_W_MM = 65     # 每格宽
QR_CELL_H_MM = 70     # 每格高 (含标签)
QR_SIZE_MM = 55       # QR 正方形边长
LABEL_H_MM = 12       # 标签高度

def mm_to_px(mm):
    return int(mm / 25.4 * DPI)

ORDER = [
    ("START",        "起点垫 (绿色)"),
    ("END",          "终点垫 (蓝色)"),
    ("RACKA_TM10",   "货架 A"),
    ("RACKB_TM10",   "货架 B"),
    ("RACKC_TM10",   "货架 C"),
    ("RACKD_TM10",   "货架 D"),
]

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    qr_dir = os.path.join(script_dir, "qr_codes")
    out_pdf = os.path.join(qr_dir, "print_sheet.pdf")
    out_png = os.path.join(qr_dir, "print_sheet.png")

    sheet = Image.new("RGB", (A4_W_PX, A4_H_PX), "white")
    draw = ImageDraw.Draw(sheet)

    # 字体: CJK 优先 (ASCII 标签 + 中文位置说明都要支持)
    font_size = mm_to_px(6)
    font = None
    for fp in [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # fallback, 中文会显示方块
    ]:
        if os.path.exists(fp):
            font = ImageFont.truetype(fp, font_size)
            break
    if font is None:
        font = ImageFont.load_default()

    # 布局: 2 列 × 3 行, 居中
    grid_cols, grid_rows = 2, 3
    cell_w_px = mm_to_px(QR_CELL_W_MM)
    cell_h_px = mm_to_px(QR_CELL_H_MM)
    total_grid_w = cell_w_px * grid_cols
    total_grid_h = cell_h_px * grid_rows
    grid_x0 = (A4_W_PX - total_grid_w) // 2
    grid_y0 = (A4_H_PX - total_grid_h) // 2

    qr_size_px = mm_to_px(QR_SIZE_MM)
    label_h_px = mm_to_px(LABEL_H_MM)

    for i, (content, place) in enumerate(ORDER):
        row = i // grid_cols
        col = i % grid_cols
        cell_x = grid_x0 + col * cell_w_px
        cell_y = grid_y0 + row * cell_h_px

        # 加载 QR 并缩放
        qr_path = os.path.join(qr_dir, f"{content}.png")
        if not os.path.exists(qr_path):
            print(f"WARN: missing {qr_path}", file=sys.stderr)
            continue
        qr_img = Image.open(qr_path).convert("RGB")
        qr_img = qr_img.resize((qr_size_px, qr_size_px), Image.NEAREST)

        # QR 居中放入 cell
        qr_x = cell_x + (cell_w_px - qr_size_px) // 2
        qr_y = cell_y
        sheet.paste(qr_img, (qr_x, qr_y))

        # 下面写标签: content + 贴哪里
        label_y = qr_y + qr_size_px + mm_to_px(2)
        draw.text((cell_x + cell_w_px // 2, label_y),
                  content, fill="black", font=font, anchor="mt")
        draw.text((cell_x + cell_w_px // 2, label_y + font_size + mm_to_px(1)),
                  place, fill="gray", font=font, anchor="mt")

        # 剪切虚线 (cell 边界)
        draw.rectangle(
            [cell_x, cell_y, cell_x + cell_w_px, cell_y + cell_h_px],
            outline="lightgray", width=2,
        )

    # 保存
    sheet.save(out_png, dpi=(DPI, DPI))
    sheet.save(out_pdf, "PDF", resolution=DPI)
    print(f"{out_png}")
    print(f"{out_pdf}")
    print(f"A4 {A4_W_MM}x{A4_H_MM}mm, 2x3 grid, QR={QR_SIZE_MM}mm, 剪切线辅助")


if __name__ == "__main__":
    main()
