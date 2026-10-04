"""Animated demo scene of the line, keyframed from a recorded simulation trajectory.

Input:  blender/data/demo_trajectory.json   (godot/tests/tools/record_demo_trajectory.gd)
Output: blender/demo_animation.blend        (open in Blender and press play)
        <frames_dir>/####.png               (optional render, set RENDER_DIR)
Robot joints, gripper fingers, conveyor drums and every workpiece follow the simulated motion exactly.
Godot -> Blender coordinates: p_b = (x, -z, y), R_b = M^T R_g M with M = Blender->Godot axis map.
"""

import importlib
import json
import math
import sys

sys.path.insert(0, "/Users/zielstor/Documents/GitProjects/Virtual-Factory/blender/scripts")
import bpy  # noqa: E402
import vf_lib as L  # noqa: E402
import vf_surfaces as S  # noqa: E402
from mathutils import Matrix, Quaternion, Vector  # noqa: E402

importlib.reload(L)
importlib.reload(S)
L.reset_scene()

DATA = json.loads((L.BLEND_DIR / "data" / "demo_trajectory.json").read_text())
RENDER_DIR = globals().get("RENDER_DIR")
M = Matrix(((1, 0, 0), (0, 0, 1), (0, -1, 0)))  # columns: Blender x, y, z expressed in Godot coordinates


def g2b(p) -> Vector:
    return Vector((p[0], -p[2], p[1]))


def append(name: str) -> list:
    with bpy.data.libraries.load(str(L.BLEND_DIR / f"{name}.blend"), link=False) as (src, dst):
        dst.objects = list(src.objects)
    for obj in dst.objects:
        bpy.context.scene.collection.objects.link(obj)
    return list(dst.objects)


def roots(objs) -> list:
    return [o for o in objs if o.parent is None]


def place(objs, godot_pos) -> None:
    for o in roots(objs):
        o.location = Vector(o.location) + g2b(godot_pos)


def by_name(objs, prefix: str):
    return next(o for o in objs if o.name.split(".")[0] == prefix)


def build_scene():
    floor = S.project_uv(L.box("Floor", (12, 8, 0.02), (-1.0, 0.5, -0.01),
                              S.image_tile("epoxy", (0.25, 0.29, 0.28), 0.57)))
    robot = append("ur5e")
    place(robot, (0.25, 0.75, -0.55))
    for name, pos in (("qa_station", (0.25, 0.85, 0)), ("assembly_cell", (-3.4, 0, 0))):
        place(append(name), pos)
    for pos in ((-2.1, 0.85, 0), (0.19, 0.85, 0)):
        place(append("light_barrier"), pos)
    klt_a = append("klt_container")
    place(klt_a, (0.75, 0, -0.55))
    by_name(klt_a, "LabelB").hide_render = True
    klt_b = append("klt_container")
    place(klt_b, (-0.25, 0, -0.55))
    by_name(klt_b, "LabelA").hide_render = True
    by_name(klt_b, "Box").data = by_name(klt_b, "Box").data.copy()
    by_name(klt_b, "Box").data.materials[0] = L.material("klt_red")
    drums = build_conveyor(append("conveyor"))
    product = append("cylinder")
    return floor, robot, drums, product


def build_conveyor(parts) -> list:
    """3 m conveyor from the modular parts (same rules as the Godot conveyor view)."""
    origin = g2b((-1.0, 0.85, 0.0))
    lib = {o.name.split(".")[0]: o for o in parts}

    def copy(name, x, sx=1.0, y=0.0, rz=0.0):
        src = lib[name]
        obj = src.copy()
        bpy.context.scene.collection.objects.link(obj)
        obj.location = Vector(src.location) + origin + Vector((x, y, 0))
        obj.scale.x, obj.rotation_euler.z = sx, rz
        return obj

    for name in ("FrameSection", "Belt", "BeltBody"):
        copy(name, 0, 3.0)
    for x in (-1.35, 0.0, 1.35):
        copy("Leg", x)
    for side in (-1, 1):
        copy("GuideRail", 0, 2.9, y=side * 0.043, rz=0 if side > 0 else math.pi)
        for x in (-1.2, -0.4, 0.4, 1.2):
            copy("GuideBracket", x, rz=0 if side > 0 else math.pi)
    drums = []
    for end, x in (("DriveEnd", 1.5), ("IdlerEnd", -1.5)):
        unit = copy(end, x)
        drum = lib[end.replace("End", "Drum")].copy()
        bpy.context.scene.collection.objects.link(drum)
        drum.parent = unit
        drum.matrix_parent_inverse = lib[end.replace("End", "Drum")].matrix_parent_inverse.copy()
        drums.append(drum)
    for o in parts:
        o.hide_render = o.hide_viewport = True
    return drums


def animate(robot, drums, product):
    joints = [by_name(robot, f"J{i}") for i in range(1, 7)]
    fingers = (by_name(robot, "FingerA"), by_name(robot, "FingerB"))
    body, cap = by_name(product, "Body"), by_name(product, "Cap")
    body.hide_render = body.hide_viewport = cap.hide_render = cap.hide_viewport = True
    items = {}
    for f, frame in enumerate(DATA["frames"], start=1):
        for j, q in zip(joints, frame["q"]):
            j.rotation_euler.z = q
            j.keyframe_insert("rotation_euler", index=2, frame=f)
        half = frame["gripper"] / 2 + 0.006
        for finger, sign in zip(fingers, (1, -1)):
            finger.location.x = sign * half
            finger.keyframe_insert("location", index=0, frame=f)
        for drum in drums:
            drum.rotation_euler.y = frame["belt"] / 0.03
            drum.keyframe_insert("rotation_euler", index=1, frame=f)
        present = set()
        for it in frame["items"]:
            obj = items.get(it["id"]) or new_item(items, it, body, cap, f)
            rot_g = Quaternion((it["q"][3], it["q"][0], it["q"][1], it["q"][2])).to_matrix()
            obj.rotation_mode = "QUATERNION"
            obj.rotation_quaternion = (M.transposed() @ rot_g @ M).to_quaternion()
            obj.location = g2b(it["p"])
            obj.keyframe_insert("location", frame=f)
            obj.keyframe_insert("rotation_quaternion", frame=f)
            present.add(it["id"])
        for item_id, obj in items.items():
            visible = item_id in present
            for o in (obj, *obj.children):
                o.hide_render = not visible
                o.keyframe_insert("hide_render", frame=f)
    for action in bpy.data.actions:
        for fc in L.fcurves(action):
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"


def new_item(items, it, body, cap, frame):
    obj = body.copy()
    bpy.context.scene.collection.objects.link(obj)
    obj.hide_render = obj.hide_viewport = False
    obj.name = it["id"]
    if it["variant"] != 1:
        c = cap.copy()
        c.data = cap.data.copy()
        c.data.materials[0] = L.material("cap_red" if it["variant"] == 0 else "plastic_blue")
        bpy.context.scene.collection.objects.link(c)
        c.hide_render = c.hide_viewport = False
        c.parent = obj
        c.matrix_parent_inverse = Matrix.Identity(4)
    items[it["id"]] = obj
    return obj


def setup_camera_and_render():
    scene = bpy.context.scene
    scene.render.fps = int(DATA["hz"])
    scene.frame_start, scene.frame_end = 1, len(DATA["frames"])
    cam = bpy.data.objects.new("DemoCam", bpy.data.cameras.new("DemoCam"))
    scene.collection.objects.link(cam)
    cam.data.lens = 32
    cam.location = (1.9, -2.2, 1.85)
    cam.rotation_euler = (Vector((-0.05, 0.25, 0.9)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    sun = bpy.data.objects.new("DemoSun", bpy.data.lights.new("DemoSun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(40), 0, math.radians(30))
    scene.collection.objects.link(sun)
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.42, 0.45, 0.48, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 8
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.render.resolution_x, scene.render.resolution_y = 960, 540


floor, robot, drums, product = build_scene()
animate(robot, drums, product)
setup_camera_and_render()
bpy.ops.wm.save_as_mainfile(filepath=str(L.BLEND_DIR / "demo_animation.blend"), copy=True)
if RENDER_DIR:
    bpy.context.scene.render.filepath = str(RENDER_DIR) + "/"
    bpy.ops.render.render(animation=True)
result = {"frames": len(DATA["frames"]), "items": len([o for o in bpy.data.objects if o.name.startswith("PC3280")])}
