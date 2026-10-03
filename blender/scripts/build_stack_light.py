"""Stack light (signal tower) on the line control cabinet: mounting base, pole, buzzer module and three LED
segments (green, amber, red from bottom to top) with a cap.

Device origin = centre of the mounting base, bottom face (sits on the cabinet roof). Overall height 0.46 m.
Objects: "Tower" (base, pole, buzzer, rings, cap - static, one material), "LampGreen", "LampAmber", "LampRed" (switched by the
view; separate objects so each gets its own material/emission state).
Export: godot/devices/stack_light/view/stack_light.glb
"""

import importlib
import sys

sys.path.insert(0, "/Users/zielstor/Documents/GitProjects/Virtual-Factory/blender/scripts")
import vf_lib as L  # noqa: E402

importlib.reload(L)
L.reset_scene()

R = 0.035                # module radius (70 mm tower)
SEG_H = 0.065            # height of one LED segment
RING_H = 0.006           # joint ring between modules
SEG = 20                 # cylinder segments
dark = L.material("plastic_dark")   # one material for the whole static tower (1 draw call)

tower = [
    L.cylinder("Base", 0.045, 0.012, (0, 0, 0.006), dark, segments=SEG, bevel=0.002),
    L.cylinder("Pole", 0.012, 0.16, (0, 0, 0.012 + 0.08), dark, segments=10),
    L.cylinder("Adapter", 0.03, 0.02, (0, 0, 0.182), dark, segments=SEG),
    L.cylinder("Buzzer", R, 0.045, (0, 0, 0.2145), dark, segments=SEG),
]
z = 0.237
lamps = []
for name, mat in (("LampGreen", "lamp_green"), ("LampAmber", "lamp_amber"), ("LampRed", "lamp_red")):
    tower.append(L.cylinder("Ring", R + 0.001, RING_H, (0, 0, z + RING_H / 2), dark, segments=SEG))
    z += RING_H
    lamps.append(L.cylinder(name, R - 0.001, SEG_H, (0, 0, z + SEG_H / 2), L.material(mat), segments=SEG))
    z += SEG_H
tower.append(L.cylinder("Cap", R + 0.001, 0.012, (0, 0, z + 0.006), dark, segments=SEG, bevel=0.004))
L.join(tower, "Tower")

L.export_glb(L.REPO / "godot" / "devices" / "stack_light" / "view" / "stack_light.glb")
L.save_blend("stack_light")
tris = L.triangle_count()

import bpy  # noqa: E402

for lamp in lamps:   # review render with all segments lit
    lamp.active_material.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 3.0
    lamp.active_material.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = \
        lamp.active_material.diffuse_color
L.render_preview("stack_light", target=(0, 0, 0.23), distance=1.5, elevation=12, azimuth=-35, lens=50)
result = {"triangles": tris, "objects": sorted(o.name for o in bpy.context.scene.objects), "height": z + 0.012}
