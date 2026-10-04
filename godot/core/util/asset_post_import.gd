@tool
extends EditorScenePostImport
## Enforce vertex tint on batched Blender materials. The glTF importer can leave this disabled
## when a material is reused by several primitives. Keep labels and switchable materials intact.


func _post_import(scene: Node) -> Object:
	for node in scene.find_children("*", "MeshInstance3D", true, false):
		var mesh := (node as MeshInstance3D).mesh
		for surface in mesh.get_surface_count():
			var mat := mesh.surface_get_material(surface) as BaseMaterial3D
			if mat and mat.resource_name in ["VF_paint", "VF_metal", "VF_rubber"]:
				mat.vertex_color_use_as_albedo = true
	return scene
