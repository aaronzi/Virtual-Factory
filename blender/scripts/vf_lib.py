"""Shared helpers for the Virtual Factory Blender asset scripts (run inside Blender via the MCP).

Conventions
- Metres, Z up (Blender). The glTF exporter converts to Godot's Y up: (x, y, z) -> (x, z, -y).
- One build script per asset: build geometry -> join per logical part -> export .glb -> save .blend -> render.
- Materials are flat PBR (Principled BSDF); details come from geometry, bevels and small decal images only.

Usage inside Blender:
    import sys; sys.path.insert(0, "<repo>/blender/scripts"); import vf_lib as L
"""

from __future__ import annotations

import math
from pathlib import Path

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

REPO = Path(__file__).resolve().parents[2]
BLEND_DIR = REPO / "blender"
DECALS = BLEND_DIR / "decals"
RENDERS = REPO / "docs" / "screenshots" / "assets"

# name: (base colour as sRGB 0..1, metallic, roughness, emission strength). Blender/glTF colours are linear;
# material() converts, so palette values match what you see in a colour picker.
PALETTE = {
    "alu_anodised": ((0.78, 0.79, 0.81), 0.9, 0.32, 0.0),
    "alu_profile": ((0.72, 0.74, 0.76), 0.85, 0.38, 0.0),
    "alu_cast": ((0.62, 0.64, 0.66), 0.8, 0.5, 0.0),
    "stainless": ((0.86, 0.87, 0.88), 1.0, 0.18, 0.0),
    "steel_zinc": ((0.66, 0.68, 0.70), 0.9, 0.35, 0.0),
    "steel_black": ((0.05, 0.05, 0.055), 0.6, 0.45, 0.0),
    "brass": ((0.78, 0.6, 0.26), 1.0, 0.3, 0.0),
    "plastic_black": ((0.03, 0.03, 0.035), 0.0, 0.55, 0.0),
    "plastic_dark": ((0.12, 0.13, 0.14), 0.0, 0.5, 0.0),
    "plastic_grey": ((0.45, 0.47, 0.5), 0.0, 0.5, 0.0),
    "plastic_blue": ((0.05, 0.25, 0.6), 0.0, 0.45, 0.0),
    "cap_red": ((0.75, 0.04, 0.05), 0.0, 0.5, 0.0),
    "rubber": ((0.04, 0.045, 0.045), 0.0, 0.85, 0.0),
    "belt_green": ((0.07, 0.16, 0.12), 0.0, 0.7, 0.0),
    "paint_blue": ((0.05, 0.22, 0.45), 0.0, 0.5, 0.0),
    "paint_grey": ((0.55, 0.57, 0.59), 0.0, 0.7, 0.0),
    "paint_anthracite": ((0.14, 0.15, 0.17), 0.0, 0.55, 0.0),
    "paint_white": ((0.86, 0.87, 0.86), 0.0, 0.6, 0.0),
    "paint_yellow": ((0.95, 0.72, 0.03), 0.0, 0.5, 0.0),
    "glass": ((0.55, 0.65, 0.7), 0.0, 0.05, 0.0),
    "robot_grey": ((0.82, 0.84, 0.85), 0.0, 0.35, 0.0),
    "robot_cap": ((0.32, 0.53, 0.71), 0.0, 0.35, 0.0),
    "klt_blue": ((0.06, 0.24, 0.52), 0.0, 0.55, 0.0),
    "klt_red": ((0.62, 0.06, 0.06), 0.0, 0.55, 0.0),
    "led_green": ((0.1, 0.9, 0.2), 0.0, 0.3, 2.0),
    "led_yellow": ((1.0, 0.7, 0.05), 0.0, 0.3, 2.0),
    "lamp_white": ((1.0, 0.98, 0.94), 0.0, 0.3, 6.0),
}


# --- scene ----------------------------------------------------------------------------------------

def reset_scene() -> None:
    """Removes all objects and orphan data, keeps the scene."""
    bpy.ops.object.mode_set(mode="OBJECT") if bpy.context.object and bpy.context.object.mode != "OBJECT" else None
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    for lib in list(bpy.data.libraries):
        bpy.data.libraries.remove(lib)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.actions,
                  bpy.data.cameras, bpy.data.lights, bpy.data.curves):
        for item in list(block):
            if item.users == 0:
                block.remove(item)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.frame_start, scene.frame_end = 1, 1


def srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def material(name: str, color=None) -> bpy.types.Material:
    """Palette material (created once). `color` overrides the base colour (new material name)."""
    key = name if color is None else f"{name}_{'%02x%02x%02x' % tuple(int(c * 255) for c in color)}"
    mat = bpy.data.materials.get(key)
    if mat:
        return mat
    base, metallic, rough, emission = PALETTE[name]
    base = tuple(srgb_to_linear(c) for c in (color or base))
    mat = bpy.data.materials.new(key)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*base, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = rough
    if emission > 0:
        bsdf.inputs["Emission Color"].default_value = (*base, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission
    if name == "glass":
        bsdf.inputs["Alpha"].default_value = 0.35
        mat.surface_render_method = "BLENDED"
    mat.diffuse_color = (*base, 1.0)
    return mat


def decal_material(image_name: str) -> bpy.types.Material:
    """Material with an image from blender/decals (alpha-clipped), e.g. 'warning_hand.png'."""
    key = f"decal_{Path(image_name).stem}"
    mat = bpy.data.materials.get(key)
    if mat:
        return mat
    mat = bpy.data.materials.new(key)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(DECALS / image_name), check_existing=True)
    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    bsdf.inputs["Roughness"].default_value = 0.45
    mat.surface_render_method = "DITHERED"
    return mat


# --- mesh primitives ------------------------------------------------------------------------------

def _new_object(name: str, bm: bmesh.types.BMesh, mat, location=(0, 0, 0)) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    if mat is not None:
        mesh.materials.append(mat)
    for poly in mesh.polygons:
        poly.use_smooth = False
    return obj


def _bevel(bm: bmesh.types.BMesh, width: float, segments: int = 1, angle_deg: float = 30.0) -> None:
    if width <= 0:
        return
    edges = [e for e in bm.edges if e.is_manifold and e.calc_face_angle(0) > math.radians(angle_deg)]
    bmesh.ops.bevel(bm, geom=edges, offset=width, segments=segments, profile=0.5, affect="EDGES",
                    clamp_overlap=True)


def box(name: str, size, location=(0, 0, 0), mat=None, bevel: float = 0.0, segments: int = 1):
    """Axis-aligned box centred at `location`."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    _bevel(bm, bevel, segments)
    return _new_object(name, bm, mat, location)


def cylinder(name: str, radius: float, depth: float, location=(0, 0, 0), mat=None, axis: str = "Z",
             segments: int = 16, bevel: float = 0.0, radius_top: float | None = None):
    """Cylinder (or cone frustum) centred at `location`, along X, Y or Z."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments, radius1=radius,
                          radius2=radius if radius_top is None else radius_top, depth=depth)
    _bevel(bm, bevel, 1, 40.0)
    rot = {"X": Matrix.Rotation(math.pi / 2, 4, "Y"), "Y": Matrix.Rotation(math.pi / 2, 4, "X"),
           "Z": Matrix.Identity(4)}[axis]
    bmesh.ops.transform(bm, matrix=rot, verts=bm.verts)
    return _new_object(name, bm, mat, location)


def extrude_profile(name: str, outline, length: float, location=(0, 0, 0), mat=None, axis: str = "Z"):
    """Extrudes a closed 2D outline [(u, v), ...] by `length` (centred) along X, Y or Z."""
    bm = bmesh.new()
    verts = [bm.verts.new((u, v, -length / 2)) for u, v in outline]
    face = bm.faces.new(verts)
    ext = bmesh.ops.extrude_face_region(bm, geom=[face])
    top = [v for v in ext["geom"] if isinstance(v, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, 0, length), verts=top)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    rot = {"X": Matrix.Rotation(math.pi / 2, 4, "Y") @ Matrix.Rotation(math.pi / 2, 4, "Z"),
           "Y": Matrix.Rotation(-math.pi / 2, 4, "X"), "Z": Matrix.Identity(4)}[axis]
    bmesh.ops.transform(bm, matrix=rot, verts=bm.verts)
    return _new_object(name, bm, mat, location)


def rounded_rect(w: float, h: float, r: float, seg: int = 3):
    """Outline of a rounded rectangle centred at the origin."""
    pts = []
    for cx, cy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90),
                       (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
        for i in range(seg + 1):
            a = math.radians(a0 + 90 * i / seg)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def slot_profile(size: float, slot_w: float, slot_d: float, chamfer: float):
    """Square aluminium profile outline with one centred slot per face (e.g. 40×40, slot 8)."""
    h, s = size / 2, slot_w / 2
    side = [(-h + chamfer, -h), (-s, -h), (-s, -h + slot_d), (s, -h + slot_d), (s, -h), (h - chamfer, -h)]
    pts = []
    for k in range(4):
        rot = Matrix.Rotation(math.radians(90 * k), 2)
        pts += [tuple(rot @ Vector(p)) for p in side]
    return pts


def slot_profile_rect(w: float, h: float, slot_w: float = 0.008, slot_d: float = 0.004,
                      chamfer: float = 0.002, grid: float = 0.04):
    """Rectangular aluminium profile outline (e.g. 40×80) with one slot per `grid` segment of every face."""
    corners = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    pts = []
    for k in range(4):
        a, b = Vector(corners[k]), Vector(corners[(k + 1) % 4])
        edge = b - a
        n_slots = max(1, round(edge.length / grid))
        d = edge.normalized()
        inward = Vector((-d.y, d.x))
        pts.append(tuple(a + d * chamfer))
        for i in range(n_slots):
            c = a + d * (edge.length * (i + 0.5) / n_slots)
            for p in (c - d * slot_w / 2, c - d * slot_w / 2 + inward * slot_d,
                      c + d * slot_w / 2 + inward * slot_d, c + d * slot_w / 2):
                pts.append(tuple(p))
        pts.append(tuple(b - d * chamfer))
    return pts


def plane(name: str, width: float, height: float, location=(0, 0, 0), mat=None, rotation=(0, 0, 0)):
    """Flat quad in the local XY plane (normal +Z) with UVs 0..1."""
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
    bmesh.ops.scale(bm, vec=(width, height, 1), verts=bm.verts)
    uv = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for loop in f.loops:
            loop[uv].uv = (loop.vert.co.x / width + 0.5, loop.vert.co.y / height + 0.5)
    obj = _new_object(name, bm, mat, location)
    obj.rotation_euler = Euler([math.radians(a) for a in rotation])
    return obj


def decal(name: str, image: str, width: float, height: float, location, rotation=(0, 0, 0)):
    """Flat quad with a decal image from blender/decals (normal = local +Z before rotation)."""
    return plane(name, width, height, location, decal_material(image), rotation)


# --- object utilities -----------------------------------------------------------------------------

def apply_transforms(obj) -> None:
    obj.data.transform(obj.matrix_basis)
    obj.matrix_basis = Matrix.Identity(4)


def join(objects, name: str, origin=(0, 0, 0)):
    """Joins meshes into one object named `name` whose origin is `origin` (world coordinates)."""
    objects = [o for o in objects if o is not None]
    for o in objects:
        apply_transforms(o)
        o.data.transform(Matrix.Translation(-Vector(origin)))
    target = objects[0]
    if len(objects) > 1:
        with bpy.context.temp_override(active_object=target, selected_editable_objects=objects,
                                       selected_objects=objects):
            bpy.ops.object.join()
    target.name = name
    target.data.name = name
    target.location = origin
    uv_layers = target.data.uv_layers
    if len(uv_layers):
        uv_layers.active_index = 0
        uv_layers[0].active_render = True
    return target


def empty(name: str, location=(0, 0, 0), parent=None):
    obj = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(obj)
    obj.empty_display_size = 0.05
    obj.location = location
    if parent:
        obj.parent = parent
    return obj


def parent(child, parent_obj, keep_world: bool = True) -> None:
    bpy.context.view_layer.update()
    world = child.matrix_world.copy()
    child.parent = parent_obj
    if keep_world:
        child.matrix_world = world


def triangle_count(objects=None) -> int:
    objects = objects or [o for o in bpy.context.scene.objects if o.type == "MESH"]
    return sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objects if o.type == "MESH")


# --- output ---------------------------------------------------------------------------------------

def export_glb(path: Path, animations: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=False,
                              export_apply=True, export_yup=True, export_animations=animations,
                              export_cameras=False, export_lights=False, export_extras=True)


def save_blend(name: str) -> Path:
    path = BLEND_DIR / f"{name}.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(path), copy=True)
    return path


def render_preview(name: str, target=(0, 0, 0), distance: float = 1.0, elevation: float = 25.0,
                   azimuth: float = 35.0, size=(1200, 800), lens: float = 50.0,
                   exclude=(), floor_z: float = 0.0) -> Path:
    """Studio render (EEVEE) for review; camera/lights are removed again afterwards."""
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.42, 0.45, 0.48, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
    floor = box("PreviewFloor", (40, 40, 0.01), (0, 0, floor_z - 0.005), material("paint_grey"))
    t = Vector(target)
    el, az = math.radians(elevation), math.radians(azimuth)
    cam_pos = t + distance * Vector((math.cos(el) * math.sin(az), -math.cos(el) * math.cos(az), math.sin(el)))
    cam_data = bpy.data.cameras.new("PreviewCam")
    cam_data.lens = lens
    cam = bpy.data.objects.new("PreviewCam", cam_data)
    scene.collection.objects.link(cam)
    cam.location = cam_pos
    cam.rotation_euler = (t - cam_pos).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    lights = []
    for i, (energy, rot) in enumerate(((3.0, (50, 0, 30)), (1.0, (60, 0, 210)))):
        ld = bpy.data.lights.new(f"PreviewSun{i}", "SUN")
        ld.energy = energy
        lo = bpy.data.objects.new(f"PreviewSun{i}", ld)
        lo.rotation_euler = Euler([math.radians(a) for a in rot])
        scene.collection.objects.link(lo)
        lights.append(lo)
    for o in exclude:
        o.hide_render = True
    RENDERS.mkdir(parents=True, exist_ok=True)
    out = RENDERS / f"{name}.png"
    scene.render.filepath = str(out)
    bpy.ops.render.render(write_still=True)
    for o in [cam, *lights, floor]:
        bpy.data.objects.remove(o, do_unlink=True)
    for o in exclude:
        o.hide_render = False
    return out
