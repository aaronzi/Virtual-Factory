"""Product PC-32-80-DA-M: ISO 15552 pneumatic cylinder Ø32 × 80 mm with red protective end cap.

Origin = bottom centre, standing on the rear end cap. Objects: "Body" (all metal parts + label), "Cap".
Export: godot/products/cylinder/cylinder.glb   Render: docs/screenshots/assets/cylinder.png
Draw-call budget: the body uses only 4 materials (metal, black, blue fitting, label) because up to ~25
parts are visible at once (KLTs).
"""

import importlib
import sys

sys.path.insert(0, "/Users/zielstor/Documents/GitProjects/Virtual-Factory/blender/scripts")
import vf_lib as L  # noqa: E402

importlib.reload(L)
L.reset_scene()

METAL = L.material("alu_anodised")
DARK = L.material("plastic_black")
CAP_W, CAP_H = 0.047, 0.024
BARREL_LEN = 0.150
TOP = 2 * CAP_H + BARREL_LEN  # 0.198


def end_cap(name: str, z: float, screws_up: bool):
    parts = [L.box(name, (CAP_W, CAP_W, CAP_H), (0, 0, z), METAL, bevel=0.0025)]
    sz = z + CAP_H / 2 if screws_up else z - CAP_H / 2
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(L.cylinder(f"{name}Screw", 0.0036, 0.002, (sx * 0.0165, sy * 0.0165, sz),
                                    DARK, segments=8))
    # supply port with push-in fitting on the -Y face
    parts.append(L.cylinder(f"{name}PortHex", 0.0062, 0.005, (0, -CAP_W / 2 - 0.0025, z), METAL,
                            axis="Y", segments=6))
    parts.append(L.cylinder(f"{name}Fitting", 0.0055, 0.008, (0, -CAP_W / 2 - 0.009, z),
                            L.material("plastic_blue"), axis="Y", segments=12))
    parts.append(L.cylinder(f"{name}Ring", 0.0042, 0.003, (0, -CAP_W / 2 - 0.0145, z), DARK,
                            axis="Y", segments=12))
    # cushioning adjustment screw on the +X face
    parts.append(L.cylinder(f"{name}Cushion", 0.0028, 0.003, (CAP_W / 2 + 0.0015, 0.008, z), METAL,
                            axis="X", segments=8))
    return parts


parts = end_cap("RearCap", CAP_H / 2, screws_up=False)
parts += end_cap("FrontCap", TOP - CAP_H / 2, screws_up=True)
parts.append(L.extrude_profile("Barrel", L.slot_profile(0.044, 0.006, 0.0015, 0.003), BARREL_LEN,
                               (0, 0, CAP_H + BARREL_LEN / 2), METAL))
parts.append(L.cylinder("Rod", 0.006, 0.032, (0, 0, TOP + 0.016), METAL, segments=16))
parts.append(L.cylinder("RodNut", 0.0098, 0.006, (0, 0, TOP + 0.024), METAL, segments=6))
parts.append(L.decal("TypePlate", "typeplate_cylinder.png", 0.034, 0.017, (0, -0.0222, CAP_H + 0.085), (90, 0, 0)))
body = L.join(parts, "Body")

cap = L.extrude_profile("Cap", L.rounded_rect(0.053, 0.053, 0.009, 3), 0.045, (0, 0, 0.2125),
                        L.material("cap_red"))
cap_top = L.cylinder("CapGrip", 0.012, 0.003, (0, 0, 0.2365), L.material("cap_red"), segments=16, bevel=0.001)
cap = L.join([cap, cap_top], "Cap")

L.export_glb(L.REPO / "godot" / "products" / "cylinder" / "cylinder.glb")
L.save_blend("cylinder")
tris = L.triangle_count()

# review render: red cap / no cap / blue cap side by side
import bpy  # noqa: E402

variants = []
for dx, mode in ((0.075, "none"), (0.15, "blue")):
    b = body.copy()
    b.data = body.data
    b.location.x = dx
    bpy.context.scene.collection.objects.link(b)
    variants.append(b)
    if mode == "blue":
        c = cap.copy()
        c.data = cap.data.copy()
        c.data.materials[0] = L.material("plastic_blue")
        c.location.x = dx
        bpy.context.scene.collection.objects.link(c)
        variants.append(c)
L.render_preview("cylinder", target=(0.075, 0, 0.12), distance=0.72, elevation=18, azimuth=28)
for v in variants:
    bpy.data.objects.remove(v, do_unlink=True)
result = {"triangles": tris, "objects": [o.name for o in bpy.context.scene.objects]}
