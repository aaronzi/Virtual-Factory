class_name DesktopRig
extends PlayerRig
## Mouse/keyboard fly camera. Hold right mouse button to look around, WASD to move,
## Q/E down/up, Shift for fast movement, left click to point at things.

@export var move_speed := 3.0
@export var fast_multiplier := 4.0
@export var mouse_sensitivity := 0.003
@export var pointer_length := 50.0
## Initial look-at point in world space (the rig keeps its own position).
@export var look_at_on_start := Vector3(0.0, 0.5, 0.0)

var _yaw := 0.0
var _pitch := 0.0
@onready var _camera: Camera3D = $Camera3D


func _ready() -> void:
	teleport_to(global_position, look_at_on_start)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_RIGHT:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED if event.pressed else Input.MOUSE_MODE_VISIBLE
	elif event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		_yaw -= event.relative.x * mouse_sensitivity
		_pitch = clampf(_pitch - event.relative.y * mouse_sensitivity, -1.5, 1.5)
		rotation.y = _yaw
		_camera.rotation.x = _pitch
	elif event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		pointer_pressed.emit(_raycast_pointer())


func _process(delta: float) -> void:
	var input := Vector3(
		Input.get_axis("move_left", "move_right"),
		Input.get_axis("move_down", "move_up"),
		Input.get_axis("move_forward", "move_back"))
	if input == Vector3.ZERO:
		return
	var speed := move_speed * (fast_multiplier if Input.is_action_pressed("move_fast") else 1.0)
	var basis_flat := _camera.global_basis
	global_position += (basis_flat * Vector3(input.x, 0.0, input.z)) * speed * delta
	global_position.y += input.y * speed * delta


func get_pointer_ray() -> Dictionary:
	var mouse := get_viewport().get_mouse_position()
	return {"origin": _camera.project_ray_origin(mouse), "direction": _camera.project_ray_normal(mouse)}


func get_view_camera() -> Camera3D:
	return _camera


func teleport_to(from: Vector3, target: Vector3) -> void:
	global_position = from
	var dir := (target - from).normalized()
	_yaw = atan2(-dir.x, -dir.z)
	_pitch = asin(clampf(dir.y, -1.0, 1.0))
	rotation = Vector3(0.0, _yaw, 0.0)
	_camera.rotation = Vector3(_pitch, 0.0, 0.0)


func _raycast_pointer() -> Dictionary:
	var ray := get_pointer_ray()
	var query := PhysicsRayQueryParameters3D.create(
		ray.origin, ray.origin + ray.direction * pointer_length)
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	return hit
