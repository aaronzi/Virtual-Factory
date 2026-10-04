class_name QualitySettings
extends RefCounted
## Complete visual presets, with the same collision and interaction geometry at every quality level.

enum Preset { LOW, MEDIUM, HIGH }

const NAMES := ["QUALITY_LOW", "QUALITY_MEDIUM", "QUALITY_HIGH"]
static var _surface_sources := {}


static func apply(root: Node, preset: int) -> void:
	preset = clampi(preset, Preset.LOW, Preset.HIGH)
	var viewport := root.get_viewport()
	viewport.mesh_lod_threshold = [6.0, 2.0, 0.5][preset]
	RenderingServer.global_shader_parameter_set("vf_surface_detail", [0.0, 0.35, 1.0][preset])
	_details(root, preset)
	_surface_textures(root, preset)
	match preset:
		Preset.LOW:
			viewport.msaa_3d = Viewport.MSAA_DISABLED
			viewport.scaling_3d_scale = 0.75
			_shadows(root, false, 1024)
		Preset.MEDIUM:
			viewport.msaa_3d = Viewport.MSAA_2X
			viewport.scaling_3d_scale = 1.0
			_shadows(root, true, 2048)
		Preset.HIGH:
			viewport.msaa_3d = Viewport.MSAA_4X
			viewport.scaling_3d_scale = 1.0
			_shadows(root, true, 4096)
	print("[Quality] preset=%d lod=%.1f scale=%.2f" %
		[preset, viewport.mesh_lod_threshold, viewport.scaling_3d_scale])


static func _details(root: Node, preset: int) -> void:
	for mesh: MeshInstance3D in root.find_children("Detail*", "MeshInstance3D", true, false):
		mesh.visible = preset != Preset.LOW
		mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	for probe: ReflectionProbe in root.find_children("*", "ReflectionProbe", true, false):
		probe.visible = preset == Preset.HIGH
	for hall: Node3D in root.find_children("Hall", "Node3D", true, false):
		for mesh: MeshInstance3D in hall.find_children("*", "MeshInstance3D", true, false):
			mesh.layers = 1 | 2  # layer 2: static hall only, captured by the High reflection probe


static func _surface_textures(root: Node, preset: int) -> void:
	for mesh: MeshInstance3D in root.find_children("*", "MeshInstance3D", true, false):
		for surface in mesh.mesh.get_surface_count():
			var mat := mesh.get_active_material(surface) as BaseMaterial3D
			if mat == null or mat.resource_name not in ["VF_concrete", "VF_epoxy"]:
				continue
			if not _surface_sources.has(mat):
				_surface_sources[mat] = [mat.albedo_texture, mat.roughness_texture, mat.normal_enabled]
			var original: Array = _surface_sources[mat]
			mat.albedo_texture = original[0] if preset != Preset.LOW else null
			mat.roughness_texture = original[1] if preset == Preset.HIGH else null
			mat.normal_enabled = original[2] and preset == Preset.HIGH
			mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
			var color := Color(0.36, 0.355, 0.34) if mat.resource_name == "VF_concrete" \
				else Color(0.25, 0.29, 0.28)
			mat.albedo_color = color.linear_to_srgb() if preset == Preset.LOW else Color.WHITE


static func _shadows(root: Node, enabled: bool, size: int) -> void:
	RenderingServer.directional_shadow_atlas_set_size(size, true)
	for light: DirectionalLight3D in root.find_children("*", "DirectionalLight3D", true, false):
		if light.has_meta("casts_shadows") or light.shadow_enabled:
			light.set_meta("casts_shadows", true)
			light.shadow_enabled = enabled
