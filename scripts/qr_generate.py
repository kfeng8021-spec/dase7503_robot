#!/usr/bin/env python3
"""
生成比赛用的所有 QR 码 PNG 图片.

Full Plan C3 规定的 QR 码内容格式:
  START        出发点
  RACKA_XXXX   货架 A (XXXX 是本队唯一 4 位随机串)
  RACKB_XXXX   货架 B
  RACKC_XXXX   货架 C
  RACKD_XXXX   货架 D
  END          目的区

用法:
  python3 qr_generate.py                    # 默认用 4X6M 做队伍串
  python3 qr_generate.py --team 7A2B        # 指定队伍串
  python3 qr_generate.py --out /tmp/qr      # 指定输出目录
"""
import argparse
import os
import sys

try:
    import qrcode
except ImportError:
    print("缺 qrcode 库, 装: pip3 install qrcode[pil]", file=sys.stderr)
    sys.exit(1)


def generate(team: str, out_dir: str, box_size: int = 20, border: int = 4):
    os.makedirs(out_dir, exist_ok=True)
    contents = [
        "START",
        f"RACKA_{team}",
        f"RACKB_{team}",
        f"RACKC_{team}",
        f"RACKD_{team}",
        "END",
    ]
    for content in contents:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size,
            border=border,
        )
        qr.add_data(content)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        path = os.path.join(out_dir, f"{content}.png")
        img.save(path)
        print(f"{content:20s} -> {path}")
    print(f"\n共生成 {len(contents)} 张, 建议打印 A4 大小 (约 8x8 cm 一张).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", default="4X6M", help="队伍 4 位随机串 (默认 4X6M)")
    ap.add_argument("--out", default="qr_codes", help="输出目录")
    ap.add_argument("--box-size", type=int, default=20, help="每格像素")
    args = ap.parse_args()
    generate(args.team, args.out, args.box_size)
