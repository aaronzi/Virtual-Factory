#!/usr/bin/env python3
"""Generates the simple decal images used by the Blender assets (labels, type plates, signs).

Run from the repo root (outside Blender):  uv run blender/scripts/make_decals.py
Output: blender/decals/*.png (Git LFS). No logos of real companies are reproduced.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[1] / "decals"
WHITE, BLACK = (245, 246, 244, 255), (20, 20, 22, 255)
YELLOW, RED = (247, 190, 0, 255), (200, 20, 25, 255)
GREY, BLUE = (120, 125, 130, 255), (25, 70, 140, 255)


FONT_CANDIDATES = ["/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                   "C:/Windows/Fonts/arial.ttf"]


def font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def canvas(w: int, h: int, bg=WHITE) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (w, h), bg)
    return img, ImageDraw.Draw(img)


def datamatrix(draw: ImageDraw.ImageDraw, x: int, y: int, cells: int, cell: int, seed: int) -> None:
    rng = random.Random(seed)
    for i in range(cells):
        for j in range(cells):
            on = i == 0 or j == cells - 1 or (j == 0 and i % 2 == 0) or (i == cells - 1 and j % 2 == 1) \
                or (0 < i < cells - 1 and 0 < j < cells - 1 and rng.random() < 0.5)
            if on:
                draw.rectangle([x + i * cell, y + j * cell, x + (i + 1) * cell - 1, y + (j + 1) * cell - 1], BLACK)


def type_plate(name: str, lines: list[str], w: int = 512, h: int = 256, seed: int = 1,
               company: str = "VF Pneumatics GmbH") -> None:
    img, d = canvas(w, h, (225, 227, 228, 255))
    d.rectangle([4, 4, w - 5, h - 5], outline=GREY, width=4)
    d.rectangle([4, 4, w - 5, 56], fill=BLUE)
    d.text((18, 12), company, font=font(30), fill=WHITE)
    for i, line in enumerate(lines):
        d.text((18, 70 + i * 34), line, font=font(24), fill=BLACK)
    datamatrix(d, w - 130, h - 130, 14, 8, seed)
    img.save(OUT / f"{name}.png")


def warning(name: str, symbol: str) -> None:
    img, d = canvas(256, 230, (0, 0, 0, 0))
    tri = [(128, 8), (248, 222), (8, 222)]
    d.polygon(tri, fill=YELLOW, outline=BLACK, width=14)
    if symbol == "!":
        d.rectangle([116, 70, 140, 160], fill=BLACK)
        d.ellipse([114, 174, 142, 202], fill=BLACK)
    elif symbol == "bolt":
        d.polygon([(140, 60), (96, 140), (126, 140), (110, 205), (162, 115), (130, 115), (150, 60)], fill=BLACK)
    elif symbol == "robot":
        d.line([(80, 200), (110, 120), (160, 100), (175, 140)], fill=BLACK, width=14)
        d.ellipse([98, 108, 122, 132], fill=BLACK)
        d.rectangle([60, 196, 120, 210], fill=BLACK)
    img.save(OUT / f"{name}.png")


def label(name: str, title: str, subtitle: str, color, w: int = 512, h: int = 256) -> None:
    img, d = canvas(w, h)
    d.rectangle([0, 0, w - 1, h - 1], outline=BLACK, width=6)
    d.rectangle([0, 0, 120, h], fill=color)
    d.text((34, 70), title[0], font=font(110), fill=WHITE)
    d.text((150, 50), title[2:], font=font(64), fill=BLACK)
    d.text((150, 150), subtitle, font=font(34), fill=GREY)
    img.save(OUT / f"{name}.png")


def arrow(name: str) -> None:
    img, d = canvas(256, 128, (0, 0, 0, 0))
    d.polygon([(10, 44), (170, 44), (170, 14), (246, 64), (170, 114), (170, 84), (10, 84)], fill=YELLOW,
              outline=BLACK, width=4)
    img.save(OUT / f"{name}.png")


def hmi(name: str, title: str) -> None:
    img, d = canvas(512, 320, (18, 24, 32, 255))
    d.rectangle([0, 0, 511, 40], fill=(38, 70, 110, 255))
    d.text((12, 8), title, font=font(24), fill=WHITE)
    for i, (txt, col) in enumerate((("RUN", (40, 170, 70, 255)), ("AUTO", (40, 110, 190, 255)),
                                    ("OEE 87%", (70, 80, 90, 255)))):
        d.rounded_rectangle([12 + i * 166, 56, 160 + i * 166, 120], 8, fill=col)
        d.text((30 + i * 166, 74), txt, font=font(26), fill=WHITE)
    pts = [(20 + k * 12, 260 - 50 * math.sin(k / 5) - k) for k in range(40)]
    d.line(pts, fill=(90, 200, 255, 255), width=3)
    d.rectangle([12, 140, 499, 300], outline=(70, 80, 90, 255), width=2)
    img.save(OUT / f"{name}.png")


def ce_marking(name: str) -> None:
    """CE marking (Regulation (EC) No 765/2008 proportions approximated) for Nameplate markings."""
    img, d = canvas(256, 180, WHITE)
    d.arc([20, 30, 140, 150], 90, 270, fill=BLACK, width=18)
    d.arc([130, 30, 250, 150], 90, 270, fill=BLACK, width=18)
    d.rectangle([168, 81, 225, 99], fill=BLACK)
    img.save(OUT / f"{name}.png")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    type_plate("typeplate_cylinder", ["PC-32-80-DA-M", "ISO 15552  Ø32 × 80", "1–10 bar  −20…80 °C"], seed=3)
    type_plate("typeplate_cell", ["Assembly cell AC-200", "S/N AC200-2025-0042", "400 V 3~ 50 Hz  16 A",
                                  "Air 6 bar"], seed=5, company="VF Automation Systems GmbH")
    type_plate("typeplate_line", ["Line controller LC-10", "S/N LC10-2508-00042", "24 V DC  10 A"], seed=7,
               company="VF Automation Systems GmbH")
    warning("warning_general", "!")
    warning("warning_electric", "bolt")
    warning("warning_robot", "robot")
    label("klt_label_a", "A OK", "i.O. / good parts", (30, 140, 60, 255))
    label("klt_label_b", "B NOK", "n.i.O. / rejects", RED)
    arrow("arrow_flow")
    hmi("hmi_cell", "AC-200  Cylinder assembly")
    hmi("hmi_line", "LINE01  Inspection & sorting")
    ce_marking("marking_ce")
    print("decals written to", OUT)


if __name__ == "__main__":
    main()
