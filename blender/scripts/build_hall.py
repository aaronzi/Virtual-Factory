"""Factory hall: 36 × 24 m steel portal frame building, 8 m eaves, closed walls and roof.

Origin = floor centre. Blender X = along the line (Godot X), Blender Y = depth (Godot -Z), Z up.
Objects: "Floor" (concrete + epoxy zone + markings), "Structure" (columns, girders, purlins, bracing),
"Walls" (plinth, sandwich panels, windows, doors), "Roof" (panels + skylight bands), "Lights" (emissive
LED high-bay fixtures), "Services" (cable trays, signs, fire extinguishers).
Export: godot/world/hall/hall.glb
"""

import importlib
import sys

sys.path.insert(0, "/Users/zielstor/Documents/GitProjects/Virtual-Factory/blender/scripts")
import vf_lib as L  # noqa: E402
import vf_surfaces as S  # noqa: E402
import vf_details as D  # noqa: E402

importlib.reload(L)
importlib.reload(S)
L.reset_scene()

LX, LY, HE = 36.0, 24.0, 8.0          # length, depth, eaves height
BAY = 6.0
steel = L.material("paint_grey", color=(0.32, 0.36, 0.4))
concrete = L.material("paint_grey", color=(0.5, 0.5, 0.49))
panel = L.material("paint_white", color=(0.78, 0.8, 0.8))
yellow = L.material("paint_yellow")


def floor():
    cement = S.image_tile("concrete", (0.36, 0.355, 0.34), 0.88)
    epoxy = S.image_tile("epoxy", (0.25, 0.29, 0.28), 0.57)
    parts = [S.project_uv(L.box("Concrete", (LX, LY, 0.1), (0, 0, -0.05), cement)),
             S.project_uv(L.box("Epoxy", (18.0, 10.0, 0.004), (0, 1.0, 0.002), epoxy))]
    # floor layers with >= 2 mm between coplanar surfaces (depth precision at 30 m, otherwise z-fighting flicker):
    # concrete 0, epoxy top 4 mm, joints 6 mm, markings top 9 mm, contact-shadow cards 11 mm (vf_grounding.py)
    seam = L.material("paint_grey", color=(0.19, 0.21, 0.2))
    for x in range(-15, 18, 3):
        parts.append(L.plane("ExpansionJoint", 0.006, LY, (x, 0, 0.006), seam))
    for y in range(-9, 12, 3):
        parts.append(L.plane("ExpansionJoint", LX, 0.006, (0, y, 0.006), seam))
    # production zone outline and pedestrian walkway (Blender y = -Godot z)
    for (x, y, w, d) in ((0, 6.0, 18.0, 0.1), (0, -4.0, 18.0, 0.1), (-9.0, 1.0, 0.1, 10.0), (9.0, 1.0, 0.1, 10.0),
                         (0, -5.5, 34.0, 0.1), (0, -7.0, 34.0, 0.1)):
        parts.append(L.box("Marking", (w, d, 0.004), (x, y, 0.007), yellow))
    for k in range(-16, 17, 2):
        parts.append(L.box("Hatch", (0.6, 0.1, 0.004), (k, -6.25, 0.007), yellow))
    return L.join(parts, "Floor")


def structure():
    parts = []
    xs = [-LX / 2 + i * BAY for i in range(int(LX / BAY) + 1)]
    for x in xs:
        for y in (-LY / 2 + 0.2, LY / 2 - 0.2):
            parts.append(L.box("ColumnBase", (0.55, 0.55, 0.04), (x, y, 0.025), steel))
            for dx in (-0.2, 0.2):
                for dy in (-0.2, 0.2):
                    parts.append(L.cylinder("Anchor", 0.022, 0.045, (x + dx, y + dy, 0.05),
                                            L.material("steel_zinc"), segments=6))
            parts.append(L.box("ColumnWeb", (0.3, 0.012, HE), (x, y, HE / 2), steel))
            parts.append(L.box("ColumnFlangeA", (0.02, 0.3, HE), (x - 0.14, y, HE / 2), steel))
            parts.append(L.box("ColumnFlangeB", (0.02, 0.3, HE), (x + 0.14, y, HE / 2), steel))
        parts.append(L.box("GirderWeb", (0.012, LY, 0.6), (x, 0, HE + 0.3), steel))
        parts.append(L.box("GirderFlangeT", (0.25, LY, 0.02), (x, 0, HE + 0.6), steel))
        parts.append(L.box("GirderFlangeB", (0.25, LY, 0.02), (x, 0, HE), steel))
    for y in [-LY / 2 + i * 2.0 for i in range(int(LY / 2.0) + 1)]:
        parts.append(L.box("Purlin", (LX, 0.12, 0.2), (0, y, HE + 0.7), steel))
    for x in (xs[0] + BAY / 2, xs[-1] - BAY / 2):
        for sign in (-1, 1):
            brace = L.cylinder("Brace", 0.02, (BAY ** 2 + (HE - 1) ** 2) ** 0.5,
                               (x, sign * (LY / 2 - 0.15), HE / 2 + 0.5), steel, segments=6)
            import math
            brace.rotation_euler.y = sign * math.atan2(BAY, HE - 1)
            parts.append(brace)
    return L.join(parts, "Structure")


def walls():
    plinth_h, win_z0, win_z1 = 1.2, 3.0, 4.2
    parts = []
    for y in (-LY / 2, LY / 2):
        parts += [L.box("Plinth", (LX, 0.25, plinth_h), (0, y, plinth_h / 2), concrete),
                  L.box("PanelLow", (LX, 0.12, win_z0 - plinth_h), (0, y, (win_z0 + plinth_h) / 2), panel),
                  L.box("PanelHigh", (LX, 0.12, HE + 0.8 - win_z1), (0, y, (HE + 0.8 + win_z1) / 2), panel)]
    for x in (-LX / 2, LX / 2):
        parts += [L.box("PlinthS", (0.25, LY, plinth_h), (x, 0, plinth_h / 2), concrete),
                  L.box("PanelS", (0.12, LY, HE + 0.8 - plinth_h), (x, 0, (HE + 0.8 + plinth_h) / 2), panel)]
    for k in range(int(HE / 0.5)):
        z = plinth_h + 0.25 + k * 0.5
        if win_z0 < z < win_z1:
            continue
        for y in (-LY / 2 + 0.069, LY / 2 - 0.069):  # back face just inside the panel (no coplanar faces)
            # panel profile in the panel colour: thin dark-edged ribs crawled (aliasing) at grazing angles
            parts.append(L.box("Rib", (LX, 0.02, 0.035), (0, y, z), panel))
    # sectional door (east wall), personnel door + emergency exit sign (north wall)
    parts += [L.box("SectionalDoor", (0.08, 4.0, 4.5), (LX / 2 - 0.07, -4.0, 2.25), L.material("paint_grey",
                                                                                            color=(0.6, 0.63, 0.66))),
              L.box("DoorFrame", (0.1, 4.3, 0.15), (LX / 2 - 0.08, -4.0, 4.55), steel),
              L.box("PersonnelDoor", (1.0, 0.08, 2.1), (-12.0, -LY / 2 + 0.07, 1.05), L.material("paint_blue")),
              L.box("ExitSign", (0.4, 0.04, 0.15), (-12.0, -LY / 2 + 0.1, 2.4), L.material("led_green"))]
    for k in range(5):
        parts.append(L.box("DoorSegment", (0.09, 4.0, 0.02), (LX / 2 - 0.12, -4.0, 0.9 * (k + 1)), steel))
    for x in (-LX / 2 + 0.065, LX / 2 - 0.065):
        for z in range(2, 9):
            parts.append(L.box("EndWallSeam", (0.012, LY, 0.012), (x, 0, z), steel))
    return L.join(parts, "Walls")


def windows():
    glass = L.material("glass", color=(0.6, 0.72, 0.8))
    parts = []
    for y in (-LY / 2, LY / 2):
        parts.append(L.box("WindowBand", (LX, 0.05, 1.2), (0, y, 3.6), glass))
        for x in range(-18, 19, 2):
            parts.append(L.box("Mullion", (0.06, 0.1, 1.2), (x, y, 3.6), steel))
    return L.join(parts, "Windows")


def roof():
    sky = L.material("lamp_white", color=(0.85, 0.9, 0.95))
    parts = [L.box("RoofDeck", (LX + 0.4, LY + 0.4, 0.1), (0, 0, HE + 0.85), panel)]
    for y in (-6.0, 0.0, 6.0):
        parts.append(L.box("Skylight", (LX - 6, 1.6, 0.02), (0, y, HE + 0.79), sky))
    return L.join(parts, "Roof")


def lights():
    parts = []
    for x in range(-15, 16, 6):
        for y in (-7.5, -2.5, 2.5, 7.5):
            parts.append(L.cylinder("Pendant", 0.006, 0.8, (x, y, HE - 0.4), steel, segments=6))
            parts.append(L.cylinder("Housing", 0.25, 0.08, (x, y, HE - 0.84), L.material("paint_anthracite"),
                                    segments=20))
            parts.append(L.cylinder("Diffuser", 0.22, 0.01, (x, y, HE - 0.885), L.material("lamp_white"),
                                    segments=20))
    return L.join(parts, "Lights")


def services():
    parts = D.hall_signs()
    for y in (-LY / 2 + 0.6, LY / 2 - 0.6):
        parts.append(L.box("CableTray", (LX - 1, 0.3, 0.06), (0, y, 5.5), L.material("steel_zinc")))
    for x in (-12.0, 6.0):
        parts += [L.cylinder("Extinguisher", 0.08, 0.5, (x + 0.25, LY / 2 - 0.45, 0.65), L.material("cap_red"),
                             segments=12),
                  L.box("ExtSign", (0.25, 0.02, 0.25), (x + 0.25, LY / 2 - 0.36, 1.4), L.material("cap_red"))]
    return L.join(parts, "Services")


floor()
structure()
walls()
windows()
roof()
lights()
services()
L.export_glb(L.REPO / "godot" / "world" / "hall" / "hall.glb")
L.save_blend("hall")
tris = L.triangle_count()

import bpy  # noqa: E402

bpy.data.objects["Roof"].hide_render = True
L.render_preview("hall", target=(0, 0, 3.0), distance=55, elevation=35, azimuth=-30, lens=35)
bpy.data.objects["Roof"].hide_render = False
result = {"triangles": tris}
