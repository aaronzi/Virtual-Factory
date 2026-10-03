class_name Interactable
extends Node
## Something the player's pointer can hover and press (world-space panels, buttons, levers).
## Attach as a child of a CollisionObject3D and call `register(collision_object)`, or register any object; the
## pointer router finds it through the collider's metadata. Override the pointer_* methods.

const META := "interactable"
## Physics layer 10: world UI panels (no collision with workpieces).
const UI_LAYER := 1 << 9
## Physics layer 11: selection volumes of assets (inspector); ignored by the UI pointer.
const SELECTION_LAYER := 1 << 10


## Makes `body` route pointer events to this interactable.
func register(body: CollisionObject3D) -> void:
	body.set_meta(META, self)


func pointer_entered() -> void:
	pass


func pointer_exited() -> void:
	pass


func pointer_moved(_hit: Dictionary) -> void:
	pass


func pointer_pressed(_hit: Dictionary) -> void:
	pass


func pointer_released(_hit: Dictionary) -> void:
	pass


## The interactable registered on `collider` or one of its ancestors, or null.
static func find(collider: Object) -> Interactable:
	var node := collider as Node
	while node:
		if node.has_meta(META):
			return node.get_meta(META) as Interactable
		node = node.get_parent()
	return null
