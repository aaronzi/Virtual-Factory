"""Tiny baked contact-shadow cards for static equipment, including the shadow-free Low preset.

Each card follows its asset, never the hall layout. No physics or live AO pass.
"""

import bpy
import numpy as np

FOOTPRINTS = {
    "assembly_cell": (1.7, 1.65, 0.004),
    "klt_container": (0.48, 0.68, 0.004),
    "ur5e": (0.48, 0.48, -0.747),
    "control_cabinet": (0.84, 0.44, 0.004),
    "hmi_stand": (0.43, 0.43, 0.004),
}


def add(stem):
    if stem not in FOOTPRINTS or bpy.data.objects.get("ContactShadow"):
        return
    import vf_lib as L
    w, d, z = FOOTPRINTS[stem]
    n = 64
    axis = np.linspace(-1, 1, n)
    fade = np.exp(-((axis[:, None] / 0.68) ** 6 + (axis[None, :] / 0.68) ** 6))
    pixels = np.zeros((n, n, 4), dtype=np.float32)
    pixels[:, :, 3] = fade * 0.24
    image = bpy.data.images.new("equipment_contact", width=n, height=n, alpha=True)
    image.pixels.foreach_set(pixels.ravel())
    path = L.BLEND_DIR / "textures" / "equipment_contact.png"
    path.parent.mkdir(exist_ok=True)
    image.filepath_raw, image.file_format = str(path), "PNG"
    image.save()
    image.pack()
    mat = bpy.data.materials.new("VF_contact")
    mat.use_nodes = True
    mat.use_backface_culling = True
    mat.surface_render_method = "BLENDED"
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
    tex.image = image
    mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    mat.node_tree.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    bsdf.inputs["Roughness"].default_value = 1
    L.plane("ContactShadow", w * 1.6, d * 1.6, (0, 0, z), mat)
