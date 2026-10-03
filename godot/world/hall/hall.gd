class_name Hall
extends Node3D
## Factory hall (hall.glb): 36 × 24 m, 8 m eaves, closed walls and roof. Adds collision for floor and
## walls and exposes the walkable interior volume (used to keep the camera inside).
## The hall shell does not cast shadows, so the directional "high-bay" light reaches the floor
## (indoor lighting without baked lightmaps, ADR-0010) and the shadow pass stays cheap.

const SIZE := Vector3(36.0, 8.0, 24.0)
const WALL_INSET := 0.35


func _ready() -> void:
	var model: Node3D = preload("res://world/hall/hall.glb").instantiate()
	add_child(model)
	for mesh in model.find_children("*", "GeometryInstance3D", true, false):
		(mesh as GeometryInstance3D).cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_build_collision()


## Interior volume in hall coordinates (inside walls, above floor, below the roof girders).
func get_interior_bounds() -> AABB:
	var half := Vector3(SIZE.x / 2 - WALL_INSET, 0.0, SIZE.z / 2 - WALL_INSET)
	return AABB(Vector3(-half.x, 0.0, -half.z), Vector3(half.x * 2, SIZE.y - 0.4, half.z * 2))


func _build_collision() -> void:
	var body := StaticBody3D.new()
	body.name = "HallCollision"
	body.collision_layer = PhysicsLayers.WORLD
	add_child(body)
	_add_box(body, Vector3(SIZE.x, 0.2, SIZE.z), Vector3(0, -0.1, 0))
	for z in [-SIZE.z / 2, SIZE.z / 2]:
		_add_box(body, Vector3(SIZE.x, SIZE.y, 0.3), Vector3(0, SIZE.y / 2, z))
	for x in [-SIZE.x / 2, SIZE.x / 2]:
		_add_box(body, Vector3(0.3, SIZE.y, SIZE.z), Vector3(x, SIZE.y / 2, 0))


func _add_box(body: StaticBody3D, size: Vector3, pos: Vector3) -> void:
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = size
	shape.shape = box
	shape.position = pos
	body.add_child(shape)
