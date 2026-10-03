"""Light barrier: compact retro-reflective photoelectric sensor + reflector, each on a stainless bracket.

Device origin = belt surface centreline at the beam position. The beam runs along Blender Y (Godot Z):
emitter at y = -0.22 (Godot +Z, operator side), reflector at y = +0.22. Optical axis 0.05 above the belt.
Objects: "Emitter" (housing, lens, bracket, M12 connector, cable, green power LED), "LedSignal" (yellow,
switched by the view), "Reflector".
Export: godot/devices/light_barrier/view/light_barrier.glb
"""

import importlib
import sys

sys.path.insert(0, "/Users/zielstor/Documents/GitProjects/Virtual-Factory/blender/scripts")
import vf_lib as L  # noqa: E402

importlib.reload(L)
L.reset_scene()

HALF = 0.22
AXIS_Z = 0.05
PROFILE_FACE = 0.19      # outer face of the conveyor side profile (y)
steel = L.material("stainless")


def bracket(sign: int, top: float):
    """Angle bracket from the side profile face to the device (sign: -1 emitter side, +1 reflector side)."""
    y_face = sign * PROFILE_FACE
    y_dev = sign * (HALF + 0.012)
    return [L.box("BracketVert", (0.03, 0.003, top + 0.07), (0, y_face + sign * 0.0015, (top - 0.07) / 2), steel),
            L.box("BracketArm", (0.03, abs(y_dev - y_face), 0.003), (0, (y_face + y_dev) / 2, top), steel),
            L.cylinder("BracketScrew", 0.004, 0.004, (0, y_face + sign * 0.0035, -0.045), L.material("steel_black"),
                       axis="Y", segments=6)]


emitter = [
    L.box("Housing", (0.032, 0.022, 0.05), (0, -(HALF + 0.011), AXIS_Z), L.material("plastic_dark"), bevel=0.003),
    L.box("Lens", (0.02, 0.002, 0.024), (0, -HALF + 0.0005, AXIS_Z + 0.004), L.material("glass")),
    L.cylinder("EmitterSpot", 0.003, 0.002, (0, -HALF + 0.0012, AXIS_Z + 0.004), L.material("cap_red"), axis="Y",
               segments=8),
    L.cylinder("Connector", 0.006, 0.014, (0, -(HALF + 0.011), AXIS_Z - 0.032), L.material("steel_zinc"), segments=10),
    L.cylinder("CableBoot", 0.0055, 0.012, (0, -(HALF + 0.011), AXIS_Z - 0.045), L.material("plastic_black"),
               segments=10),
    L.cylinder("Cable", 0.003, 0.09, (0, -(HALF + 0.011), AXIS_Z - 0.095), L.material("plastic_black"), segments=8),
    L.cylinder("LedPower", 0.0022, 0.002, (0.008, -(HALF + 0.011), AXIS_Z + 0.025), L.material("led_green"),
               segments=8),
]
emitter += bracket(-1, AXIS_Z - 0.026)
L.join(emitter, "Emitter")
L.cylinder("LedSignal", 0.0022, 0.002, (-0.008, -(HALF + 0.011), AXIS_Z + 0.025), L.material("led_yellow"),
           segments=8)

reflector = [
    L.cylinder("ReflectorBody", 0.024, 0.008, (0, HALF + 0.004, AXIS_Z), L.material("plastic_black"), axis="Y",
               segments=20, bevel=0.0015),
    L.cylinder("ReflectorFace", 0.021, 0.002, (0, HALF - 0.0005, AXIS_Z), L.material("cap_red"), axis="Y",
               segments=20),
]
reflector += bracket(1, AXIS_Z - 0.026)
L.join(reflector, "Reflector")

L.export_glb(L.REPO / "godot" / "devices" / "light_barrier" / "view" / "light_barrier.glb")
L.save_blend("light_barrier")
tris = L.triangle_count()

# review render with a short belt dummy for context
import bpy  # noqa: E402

dummy = [L.box("DummyBelt", (0.5, 0.30, 0.004), (0, 0, -0.002), L.material("belt_green")),
         L.box("DummySide", (0.5, 0.04, 0.08), (0, -0.17, -0.045), L.material("alu_profile")),
         L.box("DummySide2", (0.5, 0.04, 0.08), (0, 0.17, -0.045), L.material("alu_profile"))]
L.render_preview("light_barrier", target=(0, 0, 0.0), distance=0.8, elevation=22, azimuth=-40, lens=50, floor_z=-0.85)
for o in dummy:
    bpy.data.objects.remove(o, do_unlink=True)
result = {"triangles": tris, "objects": sorted(o.name for o in bpy.context.scene.objects)}
