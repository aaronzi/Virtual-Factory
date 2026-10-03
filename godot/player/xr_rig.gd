class_name XRRig
extends PlayerRig
## OpenXR player rig (ADR-0003): XROrigin3D with head camera and two controllers. The right controller's ray
## is the pointer (trigger = press), the left thumbstick moves smoothly, the right thumbstick snap-turns
## (left/right) and scrolls the panel under the ray (up/down).
## Built in code so the rig has no scene dependencies; `try_start()` returns false without an XR runtime, and
## the composition root then keeps the DesktopRig (--vf-xr enables the attempt).

const SCROLL_STEPS_PER_S := 12.0

@export var move_speed := 1.5
@export var snap_turn_deg := 30.0

var origin: XROrigin3D
var head: XRCamera3D
var left: XRController3D
var right: XRController3D
var _trigger_down := false
var _turn_ready := true


func _init() -> void:
	origin = XROrigin3D.new()
	add_child(origin)
	head = XRCamera3D.new()
	head.near = 0.05
	origin.add_child(head)
	left = _controller("left_hand")
	right = _controller("right_hand")


## Initialises OpenXR and switches the main viewport to XR. False if no runtime/headset is available.
func try_start() -> bool:
	var xr := XRServer.find_interface("OpenXR")
	if xr == null or not (xr.is_initialized() or xr.initialize()):
		return false
	get_viewport().use_xr = true
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	return true


func _process(delta: float) -> void:
	var trigger := right.get_float("trigger") > 0.6
	if trigger != _trigger_down:
		_trigger_down = trigger
		if trigger:
			pointer_pressed.emit({})
		else:
			pointer_released.emit({})
	var stick := left.get_vector2("primary")
	if stick.length() > 0.15:
		var forward := -head.global_basis.z
		var side := head.global_basis.x
		forward.y = 0.0
		side.y = 0.0
		global_position += (forward.normalized() * stick.y + side.normalized() * stick.x) * move_speed * delta
	var turn := right.get_vector2("primary").x
	if absf(turn) > 0.7 and _turn_ready:
		rotate_y(-signf(turn) * deg_to_rad(snap_turn_deg))
		_turn_ready = false
	elif absf(turn) < 0.3:
		_turn_ready = true
	var scroll := right.get_vector2("primary").y
	if absf(scroll) > 0.3:  # right thumbstick up/down scrolls the panel under the ray
		pointer_scrolled.emit(Vector2(0.0, -scroll * SCROLL_STEPS_PER_S * delta))


func get_pointer_ray() -> Dictionary:
	return {"origin": right.global_position, "direction": -right.global_basis.z}


func get_view_camera() -> Camera3D:
	return head


func teleport_to(from: Vector3, target: Vector3) -> void:
	global_position = Vector3(from.x, 0.0, from.z)  # the headset provides the eye height
	var dir := target - from
	rotation.y = atan2(-dir.x, -dir.z)


func _controller(tracker: String) -> XRController3D:
	var c := XRController3D.new()
	c.tracker = tracker
	origin.add_child(c)
	return c
