class_name HoverHighlight
extends Node3D
## Shows what can be clicked: an outline box and a name tag over the asset under the pointer (devices, tagged
## props, workpieces) and a hand cursor over anything clickable (assets, panels, the fence door).

const RATE_S := 0.1
const COLOR := Color(1.0, 0.62, 0.15)

var rig: PlayerRig
var router: PointerRouter
var _outline: MeshInstance3D
var _label: Label3D
var _timer := 0.0
var _cursor := Input.CURSOR_ARROW


func setup(p_rig: PlayerRig, p_router: PointerRouter) -> void:
	rig = p_rig
	router = p_router
	_outline = MeshInstance3D.new()
	_outline.mesh = _box_lines()
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.albedo_color = COLOR
	mat.no_depth_test = true
	_outline.material_override = mat
	_outline.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_outline)
	_label = Label3D.new()
	_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	_label.no_depth_test = true
	_label.font_size = 36
	_label.pixel_size = 0.0016
	_label.outline_size = 10
	_label.modulate = COLOR.lightened(0.4)
	add_child(_label)
	_show(false)


func _process(delta: float) -> void:
	_timer -= delta
	if _timer > 0.0 or rig == null:
		return
	_timer = RATE_S
	var over_ui := router.hovered() != null
	var picked := {}
	if rig.is_pointer_active() and not over_ui:
		picked = AssetPicker.pick(rig.get_world_3d(), rig.get_pointer_ray())
	_set_cursor(Input.CURSOR_POINTING_HAND if over_ui or not picked.is_empty() else Input.CURSOR_ARROW)
	if picked.is_empty():
		_show(false)
		return
	_frame(picked)
	_label.text = tr("HOVER_HINT") % picked.tag.replace("WP_", "").replace("_", "-") \
		if picked.kind == "workpiece" else tr("HOVER_HINT") % picked.tag
	_show(true)


func _frame(picked: Dictionary) -> void:
	var volume: Area3D = picked.get("volume")
	if volume:
		var shape := volume.get_child(0) as CollisionShape3D
		var size: Vector3 = (shape.shape as BoxShape3D).size
		_outline.global_transform = shape.global_transform.scaled_local(size)
		_label.global_position = shape.global_position + Vector3(0, size.y * 0.5 + 0.12, 0)
	else:  # workpiece: small box around the cylinder
		var node := picked.node as Node3D
		_outline.global_transform = Transform3D(Basis.from_scale(Vector3(0.07, 0.2, 0.07)),
			node.global_position + Vector3(0, 0.1, 0))
		_label.global_position = node.global_position + Vector3(0, 0.32, 0)


func _show(on: bool) -> void:
	_outline.visible = on
	_label.visible = on


func _set_cursor(shape: Input.CursorShape) -> void:
	if shape != _cursor:
		_cursor = shape
		Input.set_default_cursor_shape(shape)


## Unit cube (-0.5..0.5) as 12 line segments.
static func _box_lines() -> ImmediateMesh:
	var mesh := ImmediateMesh.new()
	mesh.surface_begin(Mesh.PRIMITIVE_LINES)
	var c := [Vector3(-1, -1, -1), Vector3(1, -1, -1), Vector3(1, -1, 1), Vector3(-1, -1, 1)]
	for i in 4:
		var a: Vector3 = c[i] * 0.5
		var b: Vector3 = c[(i + 1) % 4] * 0.5
		for v in [a, b, a + Vector3(0, 1, 0), b + Vector3(0, 1, 0), a, a + Vector3(0, 1, 0)]:
			mesh.surface_add_vertex(v)
	mesh.surface_end()
	return mesh
