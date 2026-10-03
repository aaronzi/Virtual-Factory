"""Assembly cell AC01 ("black box"): enclosed cylinder assembly & test cell with outlet onto the conveyor.

Device origin = floor centre. Size 1.6 (X) × 1.2 (Y) × 2.0 (Z). Front (door, HMI) = Blender -Y (Godot +Z).
Outlet at +X: parts appear at (0.95, 0, 0.853) (Godot outlet marker) under an open hood.
Objects: "Cell" (base, frame, panels, door, cabinet, hood, interior), "Windows" (tinted glass),
"LightRed", "LightAmber", "LightGreen" (stack light segments, switched by the view), "HmiScreen".
Export: godot/devices/assembly_cell/view/assembly_cell.glb
"""

import importlib
import sys

sys.path.insert(0, "/Users/zielstor/Documents/GitProjects/Virtual-Factory/blender/scripts")
import vf_lib as L  # noqa: E402

importlib.reload(L)
L.reset_scene()

SX, SY, SZ = 1.6, 1.2, 2.0
BASE = 0.12
P = 0.045                 # frame profile size
BELT_Z = 0.85
alu = L.material("alu_profile")
panel = L.material("paint_white")
anth = L.material("paint_anthracite")
profile = L.slot_profile(P, 0.01, 0.005, 0.003)


def frame():
    parts = [L.box("Base", (SX, SY, BASE), (0, 0, BASE / 2), anth, bevel=0.006)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(L.cylinder("Foot", 0.035, 0.02, (sx * (SX / 2 - 0.08), sy * (SY / 2 - 0.08), 0.01),
                                    L.material("plastic_black"), segments=12))
            parts.append(L.extrude_profile("Post", profile, SZ - BASE, (sx * (SX / 2 - P / 2), sy * (SY / 2 - P / 2),
                                                                         BASE + (SZ - BASE) / 2), alu))
    for z in (0.95, SZ - P / 2):
        for sy in (-1, 1):
            parts.append(L.extrude_profile("RailX", profile, SX - 2 * P, (0, sy * (SY / 2 - P / 2), z), alu, axis="X"))
        for sx in (-1, 1):
            parts.append(L.extrude_profile("RailY", profile, SY - 2 * P, (sx * (SX / 2 - P / 2), 0, z), alu, axis="Y"))
    parts.append(L.box("Roof", (SX - 0.01, SY - 0.01, 0.01), (0, 0, SZ - 0.005), L.material("paint_grey")))
    return parts


def panels():
    lower_h = 0.95 - BASE
    zc = BASE + lower_h / 2
    parts = []
    for sy in (-1, 1):
        parts.append(L.box("PanelX", (SX - 2 * P, 0.006, lower_h), (0, sy * (SY / 2 - P / 2), zc), panel))
    for sx in (-1, 1):
        parts.append(L.box("PanelY", (0.006, SY - 2 * P, lower_h), (sx * (SX / 2 - P / 2), 0, zc), panel))
    # front door (right half of the front, Blender -Y)
    y = -(SY / 2 - P / 2) - 0.01
    parts += [L.box("DoorFrame", (0.7, 0.012, 0.92), (0.33, y, 1.42), alu, bevel=0.004),
              L.box("Handle", (0.03, 0.04, 0.22), (0.05, y - 0.03, 1.3), L.material("plastic_black"), bevel=0.008),
              L.box("DoorSwitch", (0.05, 0.03, 0.08), (0.0, y - 0.015, 1.55), L.material("paint_yellow"), bevel=0.004),
              L.box("Hinge", (0.03, 0.03, 0.08), (0.67, y - 0.01, 1.7), alu),
              L.box("Hinge2", (0.03, 0.03, 0.08), (0.67, y - 0.01, 1.1), alu)]
    return parts


def windows():
    glass = L.material("glass", color=(0.25, 0.33, 0.38))
    upper_h = SZ - 0.95 - P
    zc = 0.95 + P / 2 + upper_h / 2
    parts = []
    for sy in (-1, 1):
        parts.append(L.box("WinX", (SX - 2 * P, 0.005, upper_h), (0, sy * (SY / 2 - P / 2), zc), glass))
    for sx in (-1, 1):
        parts.append(L.box("WinY", (0.005, SY - 2 * P, upper_h), (sx * (SX / 2 - P / 2), 0, zc), glass))
    return L.join(parts, "Windows")


def interior():
    grey = L.material("paint_grey")
    return [L.box("Table", (1.3, 0.9, 0.03), (0, 0.05, 0.95), L.material("steel_zinc")),
            L.box("GantryBeam", (1.3, 0.12, 0.12), (0, 0.3, 1.75), grey),
            L.box("GantryPostL", (0.1, 0.1, 0.8), (-0.6, 0.3, 1.35), grey),
            L.box("GantryPostR", (0.1, 0.1, 0.8), (0.6, 0.3, 1.35), grey),
            L.box("ZAxis", (0.1, 0.1, 0.45), (-0.1, 0.18, 1.5), L.material("paint_blue")),
            L.box("Press", (0.25, 0.25, 0.5), (0.35, 0.1, 1.22), L.material("paint_blue"), bevel=0.01),
            L.box("Fixture", (0.2, 0.2, 0.06), (-0.1, 0.05, 1.0), L.material("alu_cast"))]


def cabinet():
    y = SY / 2 + 0.2
    return [L.box("Cabinet", (0.8, 0.4, 1.6), (-0.3, y, 0.92), L.material("paint_grey"), bevel=0.01),
            L.box("CabinetBase", (0.8, 0.4, 0.1), (-0.3, y, 0.05), anth),
            L.cylinder("CabinetLock", 0.012, 0.01, (0.05, y + 0.205, 1.1), L.material("plastic_black"), axis="Y",
                       segments=10),
            L.decal("WarnElectric", "warning_electric.png", 0.1, 0.09, (-0.3, y + 0.2015, 1.5), (90, 0, 180)),
            L.decal("TypePlate", "typeplate_cell.png", 0.16, 0.08, (-0.3, y + 0.2015, 1.3), (90, 0, 180)),
            L.box("Duct", (0.12, 0.12, 0.25), (-0.3, SY / 2 + 0.06, 1.85), anth)]


def outlet():
    x0, length = SX / 2, 0.32
    z_top = BELT_Z + 0.32
    plate = L.material("steel_zinc")
    return [L.box("HoodTop", (length, 0.24, 0.006), (x0 + length / 2, 0, z_top), plate),
            L.box("HoodSideA", (length, 0.006, 0.3), (x0 + length / 2, -0.12, z_top - 0.15), plate),
            L.box("HoodSideB", (length, 0.006, 0.3), (x0 + length / 2, 0.12, z_top - 0.15), plate),
            L.box("Curtain", (0.004, 0.22, 0.08), (x0 + length - 0.01, 0, z_top - 0.045),
                  L.material("plastic_dark")),
            L.decal("WarnHood", "warning_general.png", 0.07, 0.063, (x0 + 0.16, -0.1235, z_top - 0.08), (90, 0, 0))]


def hmi():
    x, y = -0.55, -(SY / 2) - 0.25
    arm = [L.cylinder("HmiArm", 0.025, 0.25, (x, y + 0.125, 1.55), alu, axis="Y", segments=12),
           L.box("HmiBox", (0.42, 0.06, 0.3), (x, y, 1.45), anth, bevel=0.01),
           L.box("EStop", (0.06, 0.03, 0.06), (x + 0.15, y - 0.04, 1.33), L.material("paint_yellow"), bevel=0.005),
           L.cylinder("EStopKnob", 0.022, 0.025, (x + 0.15, y - 0.065, 1.33), L.material("cap_red"), axis="Y",
                      segments=14)]
    screen = L.decal("HmiScreen", "hmi_cell.png", 0.34, 0.21, (x, y - 0.0305, 1.47), (90, 0, 0))
    return arm, screen


def stack_light():
    x, y = SX / 2 - 0.15, -(SY / 2) + 0.15
    L.cylinder("StackPole", 0.012, 0.2, (x, y, SZ + 0.1), alu, segments=10)
    z = SZ + 0.2
    for name, mat in (("LightGreen", "led_green"), ("LightAmber", "led_yellow"), ("LightRed", "cap_red")):
        L.cylinder(name, 0.035, 0.07, (x, y, z + 0.035), L.material(mat), segments=16)
        z += 0.072
    L.cylinder("StackCap", 0.035, 0.015, (x, y, z + 0.0075), L.material("plastic_black"), segments=16)


arm, screen = hmi()
L.join(frame() + panels() + interior() + cabinet() + outlet() + arm + [bpy_obj for bpy_obj in []], "Cell")
windows()
stack_light()
import bpy  # noqa: E402

L.join([bpy.data.objects["StackPole"], bpy.data.objects["StackCap"]], "StackLight")

L.export_glb(L.REPO / "godot" / "devices" / "assembly_cell" / "view" / "assembly_cell.glb")
L.save_blend("assembly_cell")
tris = L.triangle_count()
L.render_preview("assembly_cell", target=(0.15, 0, 1.0), distance=4.6, elevation=16, azimuth=-38, lens=40)
result = {"triangles": tris, "objects": sorted(o.name for o in bpy.context.scene.objects)}
