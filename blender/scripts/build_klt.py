"""KLT container (VDA 4500 style, 600 × 400 × 280 mm) on a steel stand.

Device origin = floor below the box centre. Long side along Blender Y (Godot Z), label side towards
Blender -Y (Godot +Z, operator side). Box floor top at stand_height + 0.02 (klt_geometry.gd).
Objects: "Box" (body, single material -> colour set by the view), "BoxDetails" (handle recesses, label
holder), "LabelA", "LabelB" (one is shown by the view), "Stand".
Export: godot/devices/klt_container/view/klt_container.glb
"""

import importlib
import sys

sys.path.insert(0, "/Users/zielstor/Documents/GitProjects/Virtual-Factory/blender/scripts")
import vf_lib as L  # noqa: E402

importlib.reload(L)
L.reset_scene()

SX, SY, SZ = 0.40, 0.60, 0.28
WALL = 0.02
STAND = 0.55
body = L.material("klt_blue")
dark = L.material("plastic_dark")


def box_body():
    z0 = STAND
    parts = [L.box("Floor", (SX - 0.01, SY - 0.01, WALL), (0, 0, z0 + WALL / 2), body)]
    for s in (-1, 1):
        parts.append(L.box("WallLong", (WALL, SY, SZ), (s * (SX / 2 - WALL / 2), 0, z0 + SZ / 2), body))
        parts.append(L.box("WallShort", (SX, WALL, SZ), (0, s * (SY / 2 - WALL / 2), z0 + SZ / 2), body))
        parts.append(L.box("RimLong", (0.012, SY + 0.012, 0.025), (s * (SX / 2 + 0.002), 0, z0 + SZ - 0.0125), body,
                           bevel=0.003))
        parts.append(L.box("RimShort", (SX + 0.012, 0.012, 0.025), (0, s * (SY / 2 + 0.002), z0 + SZ - 0.0125), body,
                           bevel=0.003))
        for k in (-1, 0, 1):
            parts.append(L.box("RibLong", (0.008, 0.012, SZ - 0.05), (s * (SX / 2 + 0.004), k * 0.2, z0 + SZ / 2 - 0.01),
                               body))
        for k in (-1, 1):
            parts.append(L.box("RibShort", (0.012, 0.008, SZ - 0.05), (k * 0.12, s * (SY / 2 + 0.004), z0 + SZ / 2 - 0.01),
                               body))
        for k in (-1, 1):
            parts.append(L.box("Foot", (0.06, 0.06, 0.012), (k * 0.14, s * 0.24, z0 - 0.006), body))
    return L.join(parts, "Box")


def box_details():
    z0 = STAND
    parts = []
    for s in (-1, 1):
        parts.append(L.box("Handle", (0.12, 0.006, 0.035), (0, s * (SY / 2 + 0.0005), z0 + SZ - 0.06), dark,
                           bevel=0.004))
    parts.append(L.box("LabelHolder", (0.17, 0.006, 0.09), (0, -(SY / 2 + 0.006), z0 + SZ - 0.17),
                       L.material("plastic_grey"), bevel=0.002))
    return L.join(parts, "BoxDetails")


def label(name: str, image: str):
    return L.decal(name, image, 0.15, 0.075, (0, -(SY / 2 + 0.0095), STAND + SZ - 0.17), (90, 0, 0))


def stand():
    paint = L.material("paint_anthracite")
    parts = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(L.box("Leg", (0.03, 0.03, STAND - 0.01), (sx * 0.2, sy * 0.3, (STAND - 0.01) / 2), paint))
            parts.append(L.cylinder("Foot", 0.022, 0.012, (sx * 0.2, sy * 0.3, 0.006), L.material("plastic_black"),
                                    segments=12))
        parts.append(L.box("RailY", (0.04, 0.66, 0.02), (sx * 0.2, 0, STAND - 0.01), paint, bevel=0.002))
        parts.append(L.box("LowerY", (0.025, 0.6, 0.025), (sx * 0.2, 0, 0.12), paint))
    for sy in (-1, 1):
        parts.append(L.box("RailX", (0.43, 0.04, 0.02), (0, sy * 0.3, STAND - 0.01), paint, bevel=0.002))
        parts.append(L.box("Stop", (0.43, 0.01, 0.05), (0, sy * 0.312, STAND + 0.02), paint))
    return L.join(parts, "Stand")


box_body()
box_details()
label("LabelA", "klt_label_a.png")
label("LabelB", "klt_label_b.png")
stand()

L.export_glb(L.REPO / "godot" / "devices" / "klt_container" / "view" / "klt_container.glb")
L.save_blend("klt_container")
tris = L.triangle_count()

import bpy  # noqa: E402

bpy.data.objects["LabelB"].hide_render = True
L.render_preview("klt_container", target=(0, 0, 0.5), distance=2.0, elevation=24, azimuth=-30, lens=45)
bpy.data.objects["LabelB"].hide_render = False
result = {"triangles": tris, "objects": sorted(o.name for o in bpy.context.scene.objects)}
