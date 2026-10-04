"""Offline vertex shading and material batching. No runtime AO or extra texture fetches.

Keep switchable parts and decal materials intact: Godot addresses them by name.
AO is local to each rigid mesh, so it stays valid when joints and doors move.
"""

import math

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

SWITCHED = {"Box", "Cap", "Belt", "RingLight", "LightRed", "LightAmber", "LightGreen",
            "LampOk", "LampNok", "LedSignal", "LedPower"}


def plain(mat):
    if not mat or not mat.use_nodes or mat.name.startswith("VF_"):
        return False
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    return (bsdf is not None and not bsdf.inputs["Base Color"].is_linked
            and bsdf.inputs["Alpha"].default_value == 1
            and bsdf.inputs["Emission Strength"].default_value == 0)


def batch_material(metallic, roughness):
    name = "VF_metal" if metallic > 0.5 else ("VF_rubber" if roughness > 0.75 else "VF_paint")
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.use_backface_culling = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Metallic"].default_value = 0.85 if metallic > 0.5 else 0
    bsdf.inputs["Roughness"].default_value = 0.36 if metallic > 0.5 else (0.85 if roughness > 0.75 else 0.56)
    attr = mat.node_tree.nodes.new("ShaderNodeVertexColor")
    attr.layer_name = "VFColor"
    mat.node_tree.links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def occlusion(tree, point, normal, radius):
    tangent = normal.cross(Vector((0, 0, 1)))
    if tangent.length < 0.1:
        tangent = normal.cross(Vector((0, 1, 0)))
    tangent.normalize()
    bitangent = normal.cross(tangent)
    origin = point + normal * 0.0003
    hits = 0.0
    for i in range(8):
        angle = i * 2.399963
        r = math.sqrt((i + 0.5) / 8)
        direction = tangent * (r * math.cos(angle)) + bitangent * (r * math.sin(angle))
        direction += normal * math.sqrt(1 - r * r)
        hit, _, _, distance = tree.ray_cast(origin, direction, radius)
        if hit is not None:
            hits += 1 - distance / radius
    return 1 - 0.48 * hits / 8


def finish_mesh(obj):
    if obj.name in SWITCHED or obj.name.startswith(("Light", "Lamp", "Led")):
        return
    mesh = obj.data
    old = list(mesh.materials)
    if not any(plain(m) for m in old) or mesh.color_attributes.get("VFColor"):
        return
    colors = mesh.color_attributes.new(name="VFColor", type="FLOAT_COLOR", domain="CORNER")
    mesh.color_attributes.active_color = colors
    tree = BVHTree.FromPolygons([v.co for v in mesh.vertices], [p.vertices[:] for p in mesh.polygons])
    radius = min(0.12, max(obj.dimensions) * 0.3)
    mats, indices, bases = [], [], []
    for mat in old:
        bsdf = mat.node_tree.nodes.get("Principled BSDF") if plain(mat) else None
        new = batch_material(bsdf.inputs["Metallic"].default_value,
                             bsdf.inputs["Roughness"].default_value) if bsdf else mat
        if new not in mats:
            mats.append(new)
        indices.append(mats.index(new))
        bases.append(tuple(bsdf.inputs["Base Color"].default_value[:3]) if bsdf else (1, 1, 1))
    polygon_materials = [indices[p.material_index] for p in mesh.polygons]
    for poly in mesh.polygons:
        base = bases[poly.material_index]
        for li in poly.loop_indices:
            point = mesh.vertices[mesh.loops[li].vertex_index].co
            # Sample just inside the face to avoid self intersections at sharp corners.
            sample = point.lerp(poly.center, 0.015)
            ao = occlusion(tree, sample, poly.normal, radius) if plain(old[poly.material_index]) else 1
            colors.data[li].color = (*(c * ao for c in base), 1)
    mesh.materials.clear()
    for mat in mats:
        mesh.materials.append(mat)
    for poly, index in zip(mesh.polygons, polygon_materials):
        poly.material_index = index


def prepare():
    bpy.context.view_layer.update()
    for obj in list(bpy.context.scene.objects):
        if obj.type == "MESH":
            finish_mesh(obj)
