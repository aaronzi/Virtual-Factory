class_name WorldPanel
extends Node3D
## A 2D Control rendered into a SubViewport and shown on a quad in the 3D world (XR-ready UI, ADR-0003).
## Pointer hits on the quad are converted into mouse events for the viewport, so ordinary Controls (buttons,
## trees, text fields) work with the desktop mouse and later with XR controller rays.

static var _frame_owner := {}  # frame number -> true: at most one panel re-renders per frame

@export var size_m := Vector2(0.8, 0.5)
@export var pixels_per_meter := 1000.0
## The viewport is re-rendered only when marked dirty (input, new data) and at most `max_fps` times per
## second - keeps the draw-call budget (ADR-0010) although several panels are visible.
@export var max_fps := 15.0
## Periodic refresh even without changes (0 = only when dirty), e.g. for the live indicator fade.
@export var refresh_hz := 0.0

var viewport: SubViewport
var content: Control
var _quad: MeshInstance3D
var _input := _PanelInput.new()
var _dirty := true
var _since_render := 0.0


func _ready() -> void:
	viewport = SubViewport.new()
	viewport.size = Vector2i(size_m * pixels_per_meter)
	viewport.transparent_bg = false
	viewport.render_target_update_mode = SubViewport.UPDATE_ONCE
	viewport.gui_embed_subwindows = true
	add_child(viewport)
	_build_quad()
	_build_body()
	_input.panel = self
	add_child(_input)
	if content:
		viewport.add_child(content)


func _process(delta: float) -> void:
	_since_render += delta
	if refresh_hz > 0.0 and _since_render >= 1.0 / refresh_hz:
		_dirty = true
	if not _dirty or not is_visible_in_tree() or _since_render < 1.0 / max_fps:
		return
	var frame := Engine.get_process_frames()
	if _frame_owner.has(frame):
		return  # another panel renders this frame; try again next frame
	_frame_owner.clear()
	_frame_owner[frame] = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ONCE
	_dirty = false
	_since_render = 0.0


## Requests a re-render (call after changing the content).
func mark_dirty() -> void:
	_dirty = true


## Shows `control` on the panel (it is resized to the panel's pixel size).
func set_content(control: Control) -> void:
	if content and content.get_parent():
		content.get_parent().remove_child(content)
	content = control
	# explicit size instead of full-rect anchors: the anchors follow the window's (HiDPI-scaled) visible rect
	content.set_anchors_preset(Control.PRESET_TOP_LEFT)
	content.position = Vector2.ZERO
	content.size = size_m * pixels_per_meter
	if viewport:
		viewport.add_child(content)


## Turns the panel so that its front faces `point` (keeps it upright).
func face(point: Vector3) -> void:
	var target := Vector3(point.x, global_position.y, point.z)
	if target.distance_to(global_position) > 0.01:
		look_at(target, Vector3.UP, true)


func to_viewport(world_point: Vector3) -> Vector2:
	var local := _quad.global_transform.affine_inverse() * world_point
	var uv := Vector2(local.x / size_m.x + 0.5, 0.5 - local.y / size_m.y)
	return uv * Vector2(viewport.size)


func _build_quad() -> void:
	_quad = MeshInstance3D.new()
	var mesh := QuadMesh.new()
	mesh.size = size_m
	_quad.mesh = mesh
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.albedo_texture = viewport.get_texture()
	mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	_quad.material_override = mat
	_quad.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_quad)
	var back := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = Vector3(size_m.x + 0.02, size_m.y + 0.02, 0.015)
	back.mesh = box
	back.position.z = -0.009
	var frame := StandardMaterial3D.new()
	frame.albedo_color = Color(0.13, 0.14, 0.16)
	back.material_override = frame
	back.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF  # draw-call budget (shadow pass)
	add_child(back)


func _build_body() -> void:
	var body := StaticBody3D.new()
	body.collision_layer = Interactable.UI_LAYER
	body.collision_mask = 0
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(size_m.x, size_m.y, 0.01)
	shape.shape = box
	body.add_child(shape)
	add_child(body)
	_input.register(body)


class _PanelInput:
	extends Interactable
	var panel: WorldPanel
	var _last := Vector2.ZERO
	var _button_down := false

	func pointer_moved(hit: Dictionary) -> void:
		var pos := panel.to_viewport(hit.position)
		var event := InputEventMouseMotion.new()
		event.position = pos
		event.global_position = pos
		event.relative = pos - _last
		event.button_mask = MOUSE_BUTTON_MASK_LEFT if _button_down else 0
		_last = pos
		panel.viewport.push_input(event)
		panel.mark_dirty()
		panel.mark_dirty()

	func pointer_pressed(hit: Dictionary) -> void:
		_button_down = true
		_click(panel.to_viewport(hit.position), true)

	func pointer_released(hit: Dictionary) -> void:
		_button_down = false
		_click(panel.to_viewport(hit.position) if hit else _last, false)

	func pointer_exited() -> void:
		if _button_down:
			pointer_released({})

	func _click(pos: Vector2, pressed: bool) -> void:
		var event := InputEventMouseButton.new()
		event.button_index = MOUSE_BUTTON_LEFT
		event.pressed = pressed
		event.position = pos
		event.global_position = pos
		_last = pos
		panel.viewport.push_input(event)
		panel.mark_dirty()
