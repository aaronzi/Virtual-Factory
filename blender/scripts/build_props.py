"""Static props placed via the layout's "props" section (one .glb each, origin = placement point).

safety_fence.glb     robot cell fence (origin = robot base on the floor): back + both sides, 2.0 m high,
                     open towards the conveyor; hinged door with safety switch on the +X side ("Door").
control_cabinet.glb  line control cabinet PLC01 (origin = floor centre, front = Blender -Y / Godot +Z).
hmi_stand.glb        line operator panel on a stand (origin = floor centre, screen facing Godot +Z).
"""

import importlib
import sys

sys.path.insert(0, "/Users/zielstor/Documents/GitProjects/Virtual-Factory/blender/scripts")
import vf_lib as L  # noqa: E402

importlib.reload(L)
import bpy  # noqa: E402

OUT = L.REPO / "godot" / "world" / "props"


def yellow():
    return L.material("paint_yellow")


def dark():
    return L.material("paint_anthracite")


def mesh_mat():
    return L.material("glass", color=(0.08, 0.09, 0.1))


def fence_panel(name, x0, y0, x1, y1, h=2.0):
    """Mesh panel between two posts (frame + see-through mesh infill)."""
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    along_x = abs(x1 - x0) > abs(y1 - y0)
    length = abs(x1 - x0) if along_x else abs(y1 - y0)
    size = (length - 0.08, 0.02, 0.03) if along_x else (0.02, length - 0.08, 0.03)
    infill = (length - 0.1, 0.004, h - 0.25) if along_x else (0.004, length - 0.1, h - 0.25)
    side = (0.03, 0.02, h - 0.2) if along_x else (0.02, 0.03, h - 0.2)
    off = ((length / 2 - 0.055), 0) if along_x else (0, (length / 2 - 0.055))
    return [L.box(f"{name}Top", size, (cx, cy, h - 0.03), dark()), L.box(f"{name}Bot", size, (cx, cy, 0.17), dark()),
            L.box(f"{name}SideA", side, (cx - off[0], cy - off[1], 0.15 + (h - 0.2) / 2), dark()),
            L.box(f"{name}SideB", side, (cx + off[0], cy + off[1], 0.15 + (h - 0.2) / 2), dark()),
            L.box(f"{name}Mesh", infill, (cx, cy, 0.15 + (h - 0.2) / 2), mesh_mat())]


def post(x, y, h=2.0):
    return [L.box("Post", (0.06, 0.06, h), (x, y, h / 2), yellow()),
            L.box("PostFoot", (0.14, 0.14, 0.008), (x, y, 0.004), yellow())]


def safety_fence():
    L.reset_scene()
    # Blender y = -Godot z; relative to the robot base: back at y = +0.6, front ends at y = -0.3
    xl, xr, yb, yf = -1.0, 1.0, 0.6, -0.3
    parts = []
    for x, y in ((xl, yb), (0, yb), (xr, yb), (xl, yf), (xr, yf), (xr, 0.15)):
        parts += post(x, y)
    parts += fence_panel("Back1", xl, yb, 0, yb) + fence_panel("Back2", 0, yb, xr, yb)
    parts += fence_panel("Left", xl, yf, xl, yb)
    parts += fence_panel("Right", xr, yf, xr, 0.15)
    parts.append(L.box("SwitchBox", (0.04, 0.06, 0.1), (xr + 0.05, 0.19, 1.1), yellow(), bevel=0.004))
    parts.append(L.decal("Warning", "warning_robot.png", 0.2, 0.18, (xr + 0.012, -0.08, 1.5), (90, 0, 90)))
    L.join(parts, "Fence")
    door = fence_panel("Door", xr, 0.15, xr, yb)
    door.append(L.box("DoorHandle", (0.03, 0.12, 0.03), (xr + 0.03, 0.22, 1.05), L.material("plastic_black")))
    d = L.join(door, "Door", origin=(xr, yb - 0.02, 0))  # hinge at the back post
    L.export_glb(OUT / "safety_fence.glb")
    L.save_blend("safety_fence")
    return L.triangle_count()


def control_cabinet():
    L.reset_scene()
    grey = L.material("paint_grey", color=(0.8, 0.8, 0.78))
    parts = [L.box("Body", (0.8, 0.4, 1.8), (0, 0, 1.0), grey, bevel=0.01),
             L.box("Plinth", (0.8, 0.4, 0.1), (0, 0, 0.05), dark()),
             L.box("DoorGap", (0.004, 0.402, 1.7), (0, 0, 1.0), L.material("plastic_dark")),
             L.box("Duct", (0.3, 0.2, 0.3), (0, 0.05, 2.05), dark()),
             L.box("Fan", (0.15, 0.01, 0.15), (0.2, -0.2005, 0.4), L.material("plastic_grey"))]
    for x in (-0.05, 0.05):
        parts.append(L.cylinder("Lock", 0.012, 0.015, (x * 6, -0.205, 1.1), L.material("plastic_black"), axis="Y",
                                segments=10))
    parts.append(L.decal("WarnElectric", "warning_electric.png", 0.12, 0.11, (-0.2, -0.2005, 1.6), (90, 0, 0)))
    parts.append(L.decal("TypePlate", "typeplate_line.png", 0.16, 0.08, (0.2, -0.2005, 1.6), (90, 0, 0)))
    L.join(parts, "Cabinet")
    L.export_glb(OUT / "control_cabinet.glb")
    L.save_blend("control_cabinet")
    return L.triangle_count()


def hmi_stand():
    L.reset_scene()
    parts = [L.box("Foot", (0.4, 0.4, 0.02), (0, 0, 0.01), dark()),
             L.cylinder("Pole", 0.03, 1.15, (0, 0.05, 0.595), L.material("alu_profile"), segments=12),
             L.box("Panel", (0.5, 0.08, 0.36), (0, 0, 1.3), dark(), bevel=0.012),
             L.box("Keys", (0.5, 0.12, 0.05), (0, -0.06, 1.1), dark(), bevel=0.008),
             L.box("EStop", (0.07, 0.04, 0.07), (0.18, -0.13, 1.12), L.material("paint_yellow"), bevel=0.005),
             L.cylinder("EStopKnob", 0.025, 0.03, (0.18, -0.16, 1.12), L.material("cap_red"), axis="Y", segments=14)]
    for i, mat in enumerate(("led_green", "cap_red", "paint_white")):
        parts.append(L.cylinder("Button", 0.014, 0.012, (-0.18 + i * 0.06, -0.125, 1.11), L.material(mat), axis="Y",
                                segments=12))
    parts.append(L.decal("Screen", "hmi_line.png", 0.42, 0.26, (0, -0.0405, 1.31), (90, 0, 0)))
    panel = L.join(parts, "HmiStand")
    panel.rotation_euler.x = 0
    L.export_glb(OUT / "hmi_stand.glb")
    L.save_blend("hmi_stand")
    return L.triangle_count()


tris = {"safety_fence": safety_fence(), "control_cabinet": control_cabinet(), "hmi_stand": hmi_stand()}
# preview of all three side by side
for f in ("safety_fence", "control_cabinet"):
    with bpy.data.libraries.load(str(L.BLEND_DIR / f"{f}.blend")) as (src, dst):
        dst.objects = list(src.objects)
    for i, obj in enumerate(dst.objects):
        bpy.context.scene.collection.objects.link(obj)
        if f == "control_cabinet":
            obj.location.x -= 2.0
        else:
            obj.location.x += 1.3
L.render_preview("props", target=(0.0, 0, 1.0), distance=6.0, elevation=20, azimuth=-25, lens=40)
result = {"triangles": tris}
