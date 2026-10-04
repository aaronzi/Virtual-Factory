"""Small deterministic, seamless factory textures, generated in Blender; no external assets.

512 px tiles cover 2 metres. Geometry supplies joints, fasteners and silhouette detail.
"""

from pathlib import Path

import bpy
import numpy as np

TEXTURES = Path(__file__).resolve().parents[1] / "textures"


def image_tile(name, color, roughness):
    path = TEXTURES / (name + ".png")
    TEXTURES.mkdir(exist_ok=True)
    n = 512
    rng = np.random.default_rng(7301)
    noise = rng.normal(size=(n, n))
    freq = np.fft.fftfreq(n)
    radius = freq[:, None] ** 2 + freq[None, :] ** 2
    broad = np.fft.ifft2(np.fft.fft2(noise) * np.exp(-radius * 9000)).real
    broad /= max(broad.std(), 0.0001)
    detail = broad * 0.004 + noise * (0.008 if name == "concrete" else 0.003)
    pixels = np.ones((n, n, 4), dtype=np.float32)
    pixels[:, :, :3] = np.clip(np.array(color) + detail[:, :, None], 0, 1)
    image = bpy.data.images.new(name, width=n, height=n, alpha=False)
    image.pixels.foreach_set(pixels.ravel())
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()
    image.pack()
    mat = bpy.data.materials.new("VF_" + name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
    tex.image = image
    mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = roughness
    surface_maps(mat, name, noise, roughness)
    return mat


def data_image(name, pixels, path):
    image = bpy.data.images.new(name, width=pixels.shape[1], height=pixels.shape[0], alpha=False)
    image.colorspace_settings.name = "Non-Color"
    image.pixels.foreach_set(pixels.astype(np.float32).ravel())
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()
    image.pack()
    return image


def surface_maps(mat, name, noise, roughness):
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    pixels = np.ones((*noise.shape, 4))
    pixels[:, :, :3] = np.clip(roughness + noise[:, :, None] * 0.035, 0, 1)
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = data_image(name + "_rough", pixels, TEXTURES / (name + "_rough.png"))
    links.new(tex.outputs["Color"], bsdf.inputs["Roughness"])
    pixels[:, :, 0] = 0.5 + (noise - np.roll(noise, 1, axis=1)) * 0.025
    pixels[:, :, 1] = 0.5 + (noise - np.roll(noise, 1, axis=0)) * 0.025
    pixels[:, :, 2] = 1.0
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = data_image(name + "_normal", pixels, TEXTURES / (name + "_normal.png"))
    normal = nodes.new("ShaderNodeNormalMap")
    normal.inputs["Strength"].default_value = 0.22
    links.new(tex.outputs["Color"], normal.inputs["Color"])
    links.new(normal.outputs["Normal"], bsdf.inputs["Normal"])


def project_uv(obj, metres=2.0):
    mesh = obj.data
    uv = mesh.uv_layers.new(name="UVMap") if not mesh.uv_layers else mesh.uv_layers[0]
    for poly in mesh.polygons:
        normal_axis = max(range(3), key=lambda i: abs(poly.normal[i]))
        axes = [i for i in range(3) if i != normal_axis]
        for li in poly.loop_indices:
            p = mesh.vertices[mesh.loops[li].vertex_index].co + obj.location
            uv.data[li].uv = (p[axes[0]] / metres, p[axes[1]] / metres)
    return obj
