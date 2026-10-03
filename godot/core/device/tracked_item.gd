class_name TrackedItem
extends RigidBody3D
## A physical item that moves through the factory (e.g. a workpiece). Devices only know this
## contract; product-specific scenes extend it.

signal retired(item: TrackedItem)

var item_id := ""
var properties := {}


func _init() -> void:
	# Belt transport uses StaticBody3D.constant_linear_velocity, which does not wake sleeping bodies.
	can_sleep = false


## Called when the item is (re)spawned. Override to update the visual variant.
func configure(p_item_id: String, p_properties: Dictionary) -> void:
	item_id = p_item_id
	properties = p_properties


## Global asset id the item carries (e.g. the GS1 Digital Link of its QR code); "" if it has none.
func get_asset_id() -> String:
	return ""


## Colour a sensor would perceive at `world_point` on the item's surface (override).
func get_surface_color_at(_world_point: Vector3) -> Color:
	return Color.GRAY


## Width across the grip faces in metres (override).
func get_grip_width() -> float:
	return 0.05


## Attaches the item rigidly to a holder (e.g. a gripper TCP).
func attach_to(holder: Node3D) -> void:
	freeze_mode = RigidBody3D.FREEZE_MODE_KINEMATIC
	freeze = true
	reparent(holder, true)


## Releases the item into the physics world under `world_parent`.
func detach(world_parent: Node3D) -> void:
	reparent(world_parent, true)
	freeze = false
	linear_velocity = Vector3.ZERO
	angular_velocity = Vector3.ZERO


func is_attached() -> bool:
	return freeze


## Removes the item from the world (returned to its pool).
func retire() -> void:
	retired.emit(self)
