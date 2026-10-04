"""Tiny baked contact-shadow cards for static equipment, including the shadow-free Low preset.

Each card follows its asset, never the hall layout. No physics or live AO pass.
"""

import bpy
import numpy as np

# Card height above the hall floor: clearly above the epoxy coat (top 4 mm) and the floor markings (top 9 mm,
# build_hall.py) - a card in the same plane as the floor z-fights and flickers when the camera moves.
CARD_Z = 0.011
FOOTPRINTS = {
    "assembly_cell": (1.7, 1.65, CARD_Z),
    "klt_container": (0.48, 0.68, CARD_Z),
    "ur5e": (0.48, 0.48, CARD_Z - 0.75),  # origin = pedestal top, 0.75 m above the floor
    "control_cabinet": (0.84, 0.44, CARD_Z),
    "hmi_stand": (0.43, 0.43, CARD_Z),
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
