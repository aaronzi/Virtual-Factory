#!/usr/bin/env python3
"""Audit exported glTF geometry/material costs. Counts mesh definitions, not runtime instances or shadows."""

import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]


def inspect(path: Path) -> dict:
    data = path.read_bytes()
    magic, version, size = struct.unpack_from("<4sII", data)
    if magic != b"glTF" or version != 2 or size != len(data):
        raise ValueError(f"Invalid GLB: {path}")
    length = struct.unpack_from("<I", data, 12)[0]
    doc = json.loads(data[20:20 + length])
    primitives = [p for m in doc["meshes"] for p in m["primitives"]]
    triangles = sum(doc["accessors"][p["indices"]]["count"] // 3 for p in primitives)
    return {"path": str(path.relative_to(ROOT)), "triangles": triangles,
            "surfaces": len(primitives), "materials": len(doc.get("materials", [])),
            "bytes": size, "nodes": [n.get("name", "") for n in doc["nodes"]]}


def main():
    assets = [inspect(p) for p in sorted((ROOT / "godot").rglob("*.glb"))]
    out = ROOT / "build" / "visual-review" / "assets.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(assets, indent=2) + "\n")
    for asset in assets:
        print(f"{Path(asset['path']).stem:22} {asset['triangles']:6} triangles "
              f"{asset['surfaces']:3} surfaces {asset['bytes'] / 1024:8.1f} KiB")
    print(f"TOTAL: {sum(a['triangles'] for a in assets)} triangles; "
          f"{sum(a['bytes'] for a in assets) / 1024 / 1024:.2f} MiB GLB files")


if __name__ == "__main__":
    main()
