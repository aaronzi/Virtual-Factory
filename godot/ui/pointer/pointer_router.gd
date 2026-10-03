class_name PointerRouter
extends Node
## Routes the player rig's pointer to Interactables (hover, move, press, release) and reports presses on
## anything else as `world_pressed` (used for selecting devices and workpieces). Works with any PlayerRig, so
## an XR controller ray behaves like the desktop mouse.

signal world_pressed(hit: Dictionary)

@export var ray_length := 30.0

var rig: PlayerRig:
	set = set_rig
var _hovered: Interactable
var _pressed: Interactable
var _last_hit := {}


## The interactable currently under the pointer (null if none).
func hovered() -> Interactable:
	return _hovered if is_instance_valid(_hovered) else null


func set_rig(value: PlayerRig) -> void:
	if rig:
		rig.pointer_pressed.disconnect(_on_pressed)
		rig.pointer_released.disconnect(_on_released)
		rig.pointer_scrolled.disconnect(_on_scrolled)
	rig = value
	if rig:
		rig.pointer_pressed.connect(_on_pressed)
		rig.pointer_released.connect(_on_released)
		rig.pointer_scrolled.connect(_on_scrolled)


func _physics_process(_delta: float) -> void:
	if rig == null:
		return
	var hit := _cast() if rig.is_pointer_active() else {}
	var target: Interactable = Interactable.find(hit.collider) if hit else null
	if target != _hovered:
		if is_instance_valid(_hovered):
			_hovered.pointer_exited()
		_hovered = target
		if _hovered:
			_hovered.pointer_entered()
	if _hovered:
		_hovered.pointer_moved(hit)
	_last_hit = hit


func _on_pressed(_rig_hit: Dictionary) -> void:
	var hit := _cast()
	var target: Interactable = Interactable.find(hit.collider) if hit else null
	if target:
		_pressed = target
		target.pointer_pressed(hit)
	elif hit:
		world_pressed.emit(hit)


func _on_released(_rig_hit: Dictionary) -> void:
	if is_instance_valid(_pressed):
		_pressed.pointer_released(_cast())
	_pressed = null


## Scrolling goes to the interactable under the pointer (panels); elsewhere it is ignored.
func _on_scrolled(amount: Vector2) -> void:
	var hit := _cast()
	var target: Interactable = Interactable.find(hit.collider) if hit else null
	if target:
		target.pointer_scrolled(hit, amount)


func _cast() -> Dictionary:
	var ray := rig.get_pointer_ray()
	var query := PhysicsRayQueryParameters3D.create(ray.origin, ray.origin + ray.direction * ray_length)
	query.collision_mask = ~Interactable.SELECTION_LAYER
	return rig.get_world_3d().direct_space_state.intersect_ray(query)
