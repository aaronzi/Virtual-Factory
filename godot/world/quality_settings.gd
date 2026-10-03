class_name QualitySettings
extends RefCounted
## Render quality presets for the Compatibility renderer (ADR-0010). Low targets old iGPUs: no shadows, no
## MSAA, 75 % render scale; High: 4x MSAA, large shadow map.

enum Preset { LOW, MEDIUM, HIGH }

const NAMES := ["QUALITY_LOW", "QUALITY_MEDIUM", "QUALITY_HIGH"]


static func apply(root: Node, preset: int) -> void:
	var viewport := root.get_viewport()
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


static func _shadows(root: Node, enabled: bool, size: int) -> void:
	RenderingServer.directional_shadow_atlas_set_size(size, true)
	for light: DirectionalLight3D in root.find_children("*", "DirectionalLight3D", true, false):
		if light.has_meta("casts_shadows") or light.shadow_enabled:
			light.set_meta("casts_shadows", true)
			light.shadow_enabled = enabled
