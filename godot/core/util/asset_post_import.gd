@tool
extends EditorScenePostImport
## Enforce vertex tint on batched Blender materials. The glTF importer can leave this disabled
## when a material is reused by several primitives. Keep labels and switchable materials intact.


func _post_import(scene: Node) -> Object:
	var shared := {}
	for node in scene.find_children("*", "MeshInstance3D", true, false):
		if node.name == "ContactShadow" or String(node.name).begins_with("Detail"):
			node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		var mesh := (node as MeshInstance3D).mesh
		for surface in mesh.get_surface_count():
			var mat := mesh.surface_get_material(surface) as BaseMaterial3D
			if mat and mat.resource_name in ["VF_paint", "VF_metal", "VF_rubber"]:
				if not shared.has(mat.resource_name):
					var finish := ShaderMaterial.new()
					finish.shader = preload("res://core/util/vertex_finish.gdshader")
					finish.resource_name = mat.resource_name
					finish.set_shader_parameter("metallic", mat.metallic)
					finish.set_shader_parameter("roughness", mat.roughness)
					shared[mat.resource_name] = finish
				mesh.surface_set_material(surface, shared[mat.resource_name])
	return scene
