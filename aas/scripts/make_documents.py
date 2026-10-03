#!/usr/bin/env python3
"""Renders simple technical documents (data sheets, manuals, declarations) to PDF for Handover Documentation.

Input:  aas/data/documents/<id>.yaml  {title, subtitle, organization, version, date, language, sections: [
            {heading, text?, rows?: [[key, value], ...]}]}
Output: aas/files/docs/<id>.pdf (A4, rendered with Pillow; Git LFS)
Usage:  uv run aas/scripts/make_documents.py [ID ...]   (default: all documents)
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
W, H, M = 1240, 1754, 90  # A4 at 150 dpi
FONTS = ["/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
BLUE, GREY, BLACK = (25, 70, 140), (110, 115, 120), (20, 20, 22)


def font(size: int, bold: bool = False):
    for f in ([p.replace("Arial.ttf", "Arial Bold.ttf") for p in FONTS] if bold else []) + FONTS:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default(size=size)


def render(doc: dict) -> list[Image.Image]:
    pages, page, d, y = [], None, None, 0

    def new_page():
        nonlocal page, d, y
        page = Image.new("RGB", (W, H), "white")
        d = ImageDraw.Draw(page)
        d.rectangle([0, 0, W, 120], fill=BLUE)
        d.text((M, 38), doc.get("organization", "VF Pneumatics GmbH"), font=font(36, True), fill="white")
        d.text((W - M - 420, 48), f"{doc['id']}  ·  v{doc.get('version', '1.0')}", font=font(24), fill="white")
        d.text((M, H - 70), f"{doc.get('date', '')}  ·  page {len(pages) + 1}", font=font(20), fill=GREY)
        pages.append(page)
        y = 170

    new_page()
    d.text((M, y), doc["title"], font=font(48, True), fill=BLACK)
    y += 70
    if doc.get("subtitle"):
        d.text((M, y), doc["subtitle"], font=font(28), fill=GREY)
        y += 60
    for section in doc.get("sections", []):
        if y > H - 300:
            new_page()
        y += 20
        d.text((M, y), section["heading"], font=font(32, True), fill=BLUE)
        y += 50
        for line in textwrap.wrap(section.get("text", ""), 80):
            d.text((M, y), line, font=font(24), fill=BLACK)
            y += 34
        for key, value in section.get("rows", []):
            if y > H - 140:
                new_page()
            d.text((M, y), str(key), font=font(24), fill=GREY)
            d.text((M + 460, y), str(value), font=font(24), fill=BLACK)
            d.line([M, y + 36, W - M, y + 36], fill=(225, 228, 230), width=1)
            y += 44
    return pages


def main() -> None:
    out = ROOT / "files" / "docs"
    out.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[1:])
    for path in sorted((ROOT / "data" / "documents").glob("*.yaml")):
        if only and path.stem not in only:
            continue
        doc = yaml.safe_load(path.read_text())
        doc["id"] = path.stem
        pages = render(doc)
        pages[0].save(out / f"{path.stem}.pdf", save_all=True, append_images=pages[1:], resolution=150)
        print(f"{path.stem}.pdf ({len(pages)} page(s))")


if __name__ == "__main__":
    main()
