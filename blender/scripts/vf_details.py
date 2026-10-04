"""Small industrial details, joined into their owner's existing material surfaces."""

import math

import bpy
import vf_lib as L
from mathutils import Vector


def fasteners(xs, zs, y):
    return [L.cylinder("PanelScrew", 0.004, 0.002, (x, y, z), L.material("steel_zinc"),
                       axis="Y", segments=6) for x in xs for z in zs]


def vents(x, y, z, width=0.22, count=7):
    return [L.box("Louvre", (width, 0.004, 0.006), (x, y, z + i * 0.018),
                  L.material("plastic_dark")) for i in range(count)]


def cable(points, radius=0.008):
    parts = []
    for start, end in zip(points, points[1:]):
        a, b = Vector(start), Vector(end)
        obj = L.cylinder("ServiceCable", radius, (b - a).length, (a + b) / 2,
                         L.material("rubber"), segments=8)
        obj.rotation_euler = (b - a).to_track_quat("Z", "Y").to_euler()
        parts.append(obj)
    return parts


def text_mesh(text, size, location, material, rotation=(90, 0, 0)):
    data = bpy.data.curves.new("SignText", "FONT")
    data.body, data.size, data.align_x = text, size, "CENTER"
    data.resolution_u = 2
    data.materials.append(material)
    obj = bpy.data.objects.new("SignText", data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = tuple(math.radians(a) for a in rotation)
    with bpy.context.temp_override(active_object=obj, object=obj,
                                   selected_objects=[obj], selected_editable_objects=[obj]):
        bpy.ops.object.convert(target="MESH")
    return obj


def hall_signs():
    paint = L.material("paint_blue", color=(0.10, 0.17, 0.20))
    white = L.material("paint_white")
    parts = [L.box("BaySign", (5.0, 0.03, 0.95), (-3, 11.9, 2.2), paint),
             text_mesh("01  /  ASSEMBLY", 0.42, (-3, 11.87, 2.23), white),
             text_mesh("INSPECTION  -  SORTING", 0.17, (-3, 11.865, 1.92), white)]
    for x, label in [(-12, "A"), (0, "B"), (12, "C")]:
        parts.append(L.box("BayMarker", (0.6, 0.03, 0.8), (x + 0.7, 11.85, 5), paint))
        parts.append(text_mesh(label, 0.5, (x + 0.7, 11.82, 4.82), white))
    return parts
