class_name QualitySettings
extends RefCounted
## Complete visual presets, with the same collision and interaction geometry at every quality level.

enum Preset { LOW, MEDIUM, HIGH }

const NAMES := ["QUALITY_LOW", "QUALITY_MEDIUM", "QUALITY_HIGH"]
const LOW_SHADOW_DISTANCE := 0.1  ## m; Low renders no real-time casters, only the baked shadowmask
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
		Preset.MEDIUM:
			viewport.msaa_3d = Viewport.MSAA_2X
			viewport.scaling_3d_scale = 1.0
		Preset.HIGH:
			viewport.msaa_3d = Viewport.MSAA_4X
			viewport.scaling_3d_scale = 1.0
	_shadows(root, preset)
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
			# the tile PNGs store these values as sRGB bytes, so the flat fallback uses them unconverted
			mat.albedo_color = color if preset == Preset.LOW else Color.WHITE


## Real-time directional shadows. With baked lighting (ADR-0031) static geometry is in the lightmap's
## shadowmask and the shadow map only holds moving casters (robot, door, workpieces); Low keeps the light's
## shadows on with no casters at all, because the shadowmask is only applied to shadowed lights.
static func _shadows(root: Node, preset: int) -> void:
	var baked := not root.find_children("*", "LightmapGI", true, false).is_empty()
	RenderingServer.directional_shadow_atlas_set_size([1024, 2048, 4096][preset], true)
	RenderingServer.directional_soft_shadow_filter_set_quality(
		[RenderingServer.SHADOW_QUALITY_SOFT_VERY_LOW, RenderingServer.SHADOW_QUALITY_SOFT_LOW,
		RenderingServer.SHADOW_QUALITY_SOFT_HIGH][preset])
	for light: DirectionalLight3D in root.find_children("*", "DirectionalLight3D", true, false):
		if light.has_meta("casts_shadows") or light.shadow_enabled:
			light.set_meta("casts_shadows", true)
			if not light.has_meta("shadow_distance"):
				light.set_meta("shadow_distance", light.directional_shadow_max_distance)
			light.shadow_enabled = preset != Preset.LOW or baked
			light.shadow_caster_mask = 0 if preset == Preset.LOW else 0xFFFFFFFF
			# Low: beyond the (tiny) real-time range only the shadowmask is sampled - no shadow-map lookups
			light.directional_shadow_max_distance = LOW_SHADOW_DISTANCE if preset == Preset.LOW \
				else float(light.get_meta("shadow_distance"))
