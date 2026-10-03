#!/usr/bin/env python3
"""Assemble a PNG frame sequence (Godot --write-movie) into an animated GIF for reviews.

Usage: uv run tools/frames_to_gif.py <frame_dir> <out.gif> [first] [last] [step] [width]
"""

import sys
from pathlib import Path

from PIL import Image


def main() -> None:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    first, last, step, width = (int(a) for a in (sys.argv[3:7] + ["0", "100000", "1", "800"][len(sys.argv) - 3:]))
    files = sorted(src.glob("*.png"))[first:last:step]
    frames = []
    for f in files:
        img = Image.open(f).convert("RGB")
        img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
        frames.append(img.quantize(colors=128, method=Image.Quantize.MEDIANCUT))
    duration = round(1000 / 15 * step)
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=duration, loop=0, optimize=True)
    print(f"{out}: {len(frames)} frames, {out.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
