# -*- coding: utf-8 -*-
"""生成 RC2 搞机工具箱的图标（.ico + .png）"""
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = r"E:\我的项目\RC2-DeviceToolbox"
ICON_ICO = os.path.join(ROOT, "app.ico")
ICON_PNG = os.path.join(ROOT, "app.png")


def find_font(size):
    cands = [
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\seguisb.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
    ]
    for p in cands:
        if os.path.isfile(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def draw_icon(size):
    pad = max(1, size // 32)
    r = int(size * 0.235)

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [pad, pad, size - pad, size - pad], radius=r, fill=255)

    img = Image.new("RGBA", (size, size), (13, 16, 28, 255))

    grad = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for i in range(size):
        t = i / max(1, size - 1)
        c = (int(10 + 60 * (1 - t)), int(90 + 40 * (1 - t)),
             int(220 - 30 * t), int(205 * (1 - t) ** 1.3))
        gd.line([(0, i), (size, i)], fill=c)
    img = Image.alpha_composite(img, grad)

    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd2 = ImageDraw.Draw(glow)
    cx, cy = int(size * 0.78), int(size * 0.80)
    rad = int(size * 0.42)
    for i in range(rad, 0, -1):
        a = int(75 * (1 - i / rad) ** 2)
        gd2.ellipse([cx - i, cy - i, cx + i, cy + i], fill=(191, 90, 242, a))
    img = Image.alpha_composite(img, glow)

    d = ImageDraw.Draw(img)
    font = find_font(int(size * 0.40))
    text = "RC2"
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size - tw) / 2 - bbox[0],
            (size - th) / 2 - bbox[1] - size * 0.045),
           text, font=font, fill=(255, 255, 255, 255))

    ly = int(size * 0.775)
    lw = int(size * 0.30)
    lx = (size - lw) // 2
    d.rounded_rectangle([lx, ly, lx + lw, ly + max(2, size // 90)],
                        radius=max(1, size // 180), fill=(100, 210, 255, 235))

    final = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    final.paste(img, (0, 0), mask)
    return final


def main():
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [draw_icon(s) for s in sizes]
    draw_icon(256).save(ICON_PNG)
    imgs[-1].save(ICON_ICO, format="ICO", sizes=[(s, s) for s in sizes])
    print("ico ->", ICON_ICO, os.path.getsize(ICON_ICO), "bytes")
    print("png ->", ICON_PNG, os.path.getsize(ICON_PNG), "bytes")


if __name__ == "__main__":
    main()
