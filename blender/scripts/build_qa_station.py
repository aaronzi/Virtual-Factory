"""QA station QS01: true-colour sensor on a profile post, looking at the part top from the operator side.

Device origin = belt surface at the inspection/stop position. Godot geometry (qa_station_geometry.gd):
inspection point (0, 0.23, 0) and sensor head (0, 0.32, 0.12) in Godot = (0, -0.12, 0.32) in Blender.
Objects: "Station" (post, arm, bracket, sensor housing, cable), "RingLight" (switched), "LampOk", "LampNok"
(switched), "Lens".
Export: godot/devices/qa_station/view/qa_station.glb
"""

import importlib
import math
import sys

sys.path.insert(0, "/Users/zielstor/Documents/GitProjects/Virtual-Factory/blender/scripts")
import vf_lib as L  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

importlib.reload(L)
L.reset_scene()

TARGET = Vector((0, 0, 0.23))
HEAD = Vector((0, -0.12, 0.32))
POST_Y = -0.21            # 40×40 post bolted to the outer face of the conveyor side profile
POST_TOP = 0.42
alu = L.material("alu_profile")
DIR = (TARGET - HEAD).normalized()
TILT = math.atan2(DIR.z, DIR.y)  # rotation about X that turns +Y into DIR


def oriented(objs, at: Vector):
    """Rotates parts built around the origin (front = +Y) so the front looks along DIR, then moves them."""
    m = Matrix.Translation(at) @ Matrix.Rotation(TILT, 4, "X")
    for o in objs:
        o.data.transform(m @ Matrix.Translation(o.location))
        o.location = (0, 0, 0)
    return objs


profile = L.slot_profile(0.04, 0.008, 0.004, 0.002)
station = [
    L.extrude_profile("Post", profile, POST_TOP + 0.085, (0, POST_Y, (POST_TOP - 0.085) / 2), alu),
    L.box("PostCap", (0.04, 0.04, 0.004), (0, POST_Y, POST_TOP + 0.002), L.material("plastic_black")),
    L.box("FootPlate", (0.08, 0.008, 0.1), (0, -0.194, -0.045), L.material("steel_zinc"), bevel=0.002),
    L.extrude_profile("Arm", profile, 0.1, (0, POST_Y + 0.05, 0.38), alu, axis="Y"),
    L.box("Clamp", (0.05, 0.05, 0.05), (0, POST_Y, 0.38), L.material("plastic_black"), bevel=0.004),
    L.box("SensorBracket", (0.04, 0.006, 0.07), (0, -0.112 - 0.04, 0.35), L.material("stainless")),
]
sensor = oriented([
    L.box("Housing", (0.05, 0.06, 0.035), (0, -0.03, 0), L.material("plastic_dark"), bevel=0.004),
    L.box("Window", (0.036, 0.002, 0.024), (0, 0.0005, 0), L.material("plastic_black")),
    L.cylinder("Connector", 0.0065, 0.018, (0, -0.068, 0), L.material("steel_zinc"), axis="Y", segments=10),
    L.cylinder("Cable", 0.003, 0.05, (0, -0.1, 0), L.material("plastic_black"), axis="Y", segments=8),
    L.cylinder("LedA", 0.0022, 0.002, (0.012, -0.045, 0.0176), L.material("led_green"), segments=8),
], HEAD)
L.join(station + sensor, "Station")
L.join(oriented([L.cylinder("RingLight", 0.028, 0.006, (0, 0.004, 0), L.material("paint_white"), axis="Y",
                            segments=24)], HEAD), "RingLight")
L.join(oriented([L.cylinder("Lens", 0.009, 0.004, (0, 0.007, 0), L.material("glass"), axis="Y", segments=16)],
                HEAD), "Lens")
lamp_base = Vector((0, POST_Y, POST_TOP))
L.cylinder("LampOk", 0.018, 0.04, lamp_base + Vector((0, 0, 0.026)), L.material("led_green"), segments=16)
L.cylinder("LampNok", 0.018, 0.04, lamp_base + Vector((0, 0, 0.068)), L.material("cap_red"), segments=16)
L.cylinder("LampTop", 0.018, 0.006, lamp_base + Vector((0, 0, 0.091)), L.material("plastic_black"), segments=16)

L.export_glb(L.REPO / "godot" / "devices" / "qa_station" / "view" / "qa_station.glb")
L.save_blend("qa_station")
tris = L.triangle_count()

import bpy  # noqa: E402

dummy = [L.box("DummyBelt", (0.6, 0.30, 0.004), (0, 0, -0.002), L.material("belt_green")),
         L.box("DummySide", (0.6, 0.04, 0.08), (0, -0.17, -0.045), L.material("alu_profile")),
         L.box("DummyPart", (0.047, 0.047, 0.19), (0, 0, 0.095), L.material("alu_anodised")),
         L.box("DummyCap", (0.053, 0.053, 0.045), (0, 0, 0.2125), L.material("cap_red"), bevel=0.006)]
L.render_preview("qa_station", target=(0, -0.08, 0.24), distance=1.25, elevation=18, azimuth=-60, lens=50,
                 floor_z=-0.85)
for o in dummy:
    bpy.data.objects.remove(o, do_unlink=True)
result = {"triangles": tris, "objects": sorted(o.name for o in bpy.context.scene.objects),
          "tilt_deg": math.degrees(TILT)}
