"""Belt conveyor parts (modular, assembled by the Godot view for any length).

Blender axes: X = transport direction, Y = across the belt (Godot -Z), Z = up. Belt top surface at z = 0.
Objects (each with its own origin):
  FrameSection  1 m of the two 40×80 side profiles + slider bed (scaled along X by the view)
  Belt          1 m × width top surface (UV 0..1, scrolling shader in Godot) + BeltBody (rubber)
  DriveEnd      end plates, belt wrap, bevel gear motor (−Y side) + child DriveDrum (rotates)
  IdlerEnd      end plates, belt wrap, tensioners + child IdlerDrum (rotates)
  Leg           support stand (2 × 40×40 legs, cross members, levelling feet), floor at z = −0.85
  GuideRail     1 m side guide (aluminium flat bar + PE strip), centred at y = 0
  GuideBracket  bracket from the +Y side profile to the guide rail (mirrored by the view)
  FlowArrow     decal (placed along the side profile by the view)
Export: godot/devices/conveyor/view/conveyor_parts.glb
"""

import importlib
import sys

sys.path.insert(0, "/Users/zielstor/Documents/GitProjects/Virtual-Factory/blender/scripts")
import vf_lib as L  # noqa: E402

importlib.reload(L)
L.reset_scene()

W = 0.30            # belt width
H = 0.85            # floor -> belt top
R = 0.03            # drum radius
PY = W / 2 + 0.02   # side profile centre (y)
PZ = -0.045         # side profile centre (z), 40 × 80 profile, top 5 mm below belt
GAP = 0.08          # guide gap (default; view positions rails)
alu = L.material("alu_profile")
zinc = L.material("steel_zinc")


def frame_section():
    parts = [L.extrude_profile(f"Side{s}", L.slot_profile_rect(0.04, 0.08), 1.0, (0, s * PY, PZ), alu, axis="X")
             for s in (-1, 1)]
    parts.append(L.box("SliderBed", (1.0, W - 0.01, 0.004), (0, 0, -0.008), zinc))
    for x in (-0.25, 0.25):
        parts.append(L.extrude_profile("Cross", L.slot_profile(0.04, 0.008, 0.004, 0.002), W, (x, 0, -0.065),
                                       alu, axis="Y"))
    return L.join(parts, "FrameSection")


def belt():
    top = L.plane("Belt", 1.0, W, (0, 0, 0.0002), L.material("belt_green"))
    body = L.box("BeltBody", (1.0, W, 0.0035), (0, 0, -0.0016), L.material("rubber"))
    return top, body


def end_unit(name: str, drum_name: str, sign: int, motor: bool):
    parts = []
    for s in (-1, 1):
        parts.append(L.box(f"{name}Plate", (0.13, 0.008, 0.11), (sign * 0.01, s * (PY + 0.024), -0.045), zinc,
                           bevel=0.003))
        parts.append(L.cylinder(f"{name}Bearing", 0.016, 0.012, (0, s * (PY + 0.034), -R), L.material("steel_black"),
                                axis="Y", segments=12))
    wrap = L.cylinder(f"{name}Wrap", R + 0.0035, W, (0, 0, -R), L.material("rubber"), axis="Y", segments=20)
    parts.append(wrap)
    if motor:
        parts += gear_motor()
        parts.append(L.decal("WarningPinch", "warning_general.png", 0.05, 0.045, (0.035, -(PY + 0.0285), -0.045),
                             (90, 0, 0)))
    else:
        for s in (-1, 1):
            parts.append(L.cylinder("Tensioner", 0.004, 0.06, (-0.05, s * (PY + 0.03), -R), zinc, axis="X",
                                    segments=6))
    unit = L.join(parts, name)
    drum = L.cylinder(drum_name, R, W + 0.006, (0, 0, -R), L.material("steel_zinc"), axis="Y", segments=20)
    groove = L.box(f"{drum_name}Mark", (0.006, W + 0.008, 0.004), (0, 0, -R + R - 0.001), L.material("steel_black"))
    drum = L.join([drum, groove], drum_name, origin=(0, 0, -R))
    L.parent(drum, unit)
    return unit


def gear_motor():
    y = -(PY + 0.028 + 0.05)
    blue = L.material("paint_blue")
    parts = [L.box("Gearbox", (0.1, 0.1, 0.12), (0, y, -R - 0.01), blue, bevel=0.008),
             L.cylinder("Motor", 0.045, 0.17, (-0.135, y, -R - 0.01), blue, axis="X", segments=20),
             L.cylinder("FanCover", 0.047, 0.04, (-0.24, y, -R - 0.01), L.material("plastic_dark"), axis="X",
                        segments=20),
             L.box("TerminalBox", (0.06, 0.06, 0.04), (-0.13, y, -R + 0.05), blue, bevel=0.004),
             L.cylinder("CableGland", 0.008, 0.02, (-0.13, y - 0.04, -R + 0.05), L.material("plastic_black"),
                        axis="Y", segments=10)]
    for k in range(7):
        parts.append(L.cylinder("Fin", 0.049, 0.004, (-0.19 + k * 0.018, y, -R - 0.01), blue, axis="X", segments=20))
    return parts


def leg():
    parts = []
    length = H - 0.085
    for s in (-1, 1):
        parts.append(L.extrude_profile("Post", L.slot_profile(0.04, 0.008, 0.004, 0.002), length,
                                       (0, s * PY, -0.085 - length / 2), alu, axis="Z"))
        parts.append(L.cylinder("FootThread", 0.006, 0.03, (0, s * PY, -H + 0.02), zinc, segments=8))
        parts.append(L.cylinder("FootPad", 0.03, 0.01, (0, s * PY, -H + 0.005), L.material("plastic_black"),
                                segments=16, bevel=0.002))
    for z in (-H + 0.18, -0.12):
        parts.append(L.extrude_profile("Brace", L.slot_profile(0.04, 0.008, 0.004, 0.002), 2 * PY - 0.04,
                                       (0, 0, z), alu, axis="Y"))
    return L.join(parts, "Leg")


def guides():
    rail = L.join([L.box("RailBar", (1.0, 0.006, 0.03), (0, 0.002, 0.017), alu),
                   L.box("RailStrip", (1.0, 0.004, 0.024), (0, -0.003, 0.017), L.material("paint_white"))],
                  "GuideRail")
    y_rail = GAP / 2 + 0.006
    bracket = L.join([
        L.box("ClampBlock", (0.03, 0.03, 0.02), (0, PY, 0.012), L.material("plastic_black"), bevel=0.003),
        L.cylinder("Rod", 0.005, PY - y_rail, (0, (PY + y_rail) / 2, 0.025), zinc, axis="Y", segments=8),
        L.box("RailClamp", (0.02, 0.012, 0.03), (0, y_rail + 0.004, 0.025), L.material("plastic_black"),
              bevel=0.002)], "GuideBracket")
    return rail, bracket


frame_section()
belt()
end_unit("DriveEnd", "DriveDrum", 1, motor=True)
end_unit("IdlerEnd", "IdlerDrum", -1, motor=False)
leg()
guides()
L.decal("FlowArrow", "arrow_flow.png", 0.12, 0.06, (0, -(PY + 0.0205), PZ), (90, 0, 0))

L.export_glb(L.REPO / "godot" / "devices" / "conveyor" / "view" / "conveyor_parts.glb")
L.save_blend("conveyor")
tris = L.triangle_count()

# review render: assemble a 3 m conveyor from the parts (temporary copies)
import bpy  # noqa: E402

temp = []


def place(name, x, scale_x=1.0, mirror=False):
    src = bpy.data.objects[name]
    obj = src.copy()
    bpy.context.scene.collection.objects.link(obj)
    obj.location = (x + src.location.x, src.location.y, H + src.location.z)
    obj.scale.x = scale_x
    if mirror:
        obj.rotation_euler.z = 3.14159265
    temp.append(obj)
    for child in src.children:
        c = child.copy()
        bpy.context.scene.collection.objects.link(c)
        c.parent = obj
        c.matrix_parent_inverse = child.matrix_parent_inverse.copy()
        temp.append(c)
    return obj


originals = [o for o in bpy.context.scene.objects if o.parent is None]
place("FrameSection", 0, 3.0)
place("Belt", 0, 3.0)
place("BeltBody", 0, 3.0)
place("DriveEnd", 1.5)
place("IdlerEnd", -1.5)
for x in (-1.35, 0.0, 1.35):
    place("Leg", x)
for s in (-1, 1):
    r = place("GuideRail", 0, 2.9)
    r.location.y = s * (GAP / 2 + 0.003)
    r.rotation_euler.z = 0 if s > 0 else 3.14159265
for x in (-1.2, -0.4, 0.4, 1.2):
    place("GuideBracket", x)
    place("GuideBracket", x, mirror=True)
place("FlowArrow", -0.6)
for o in originals:
    o.hide_render = True
for o in bpy.data.objects:
    if o.parent in originals:
        o.hide_render = True
L.render_preview("conveyor", target=(0.2, 0, 0.55), distance=3.2, elevation=26, azimuth=28, lens=28)
L.render_preview("conveyor_drive", target=(1.3, 0, 0.8), distance=0.9, elevation=30, azimuth=35, lens=35)
for o in temp:
    bpy.data.objects.remove(o, do_unlink=True)
for o in bpy.data.objects:
    o.hide_render = False
result = {"triangles": tris, "objects": sorted(o.name for o in bpy.context.scene.objects)}
