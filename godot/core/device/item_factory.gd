class_name ItemFactory
extends RefCounted
## Spawns TrackedItems from a scene and recycles retired ones (object pool, no allocations in
## continuous production).

signal item_spawned(item: TrackedItem)

var _scene: PackedScene
var _parent: Node3D
var _pool: Array[TrackedItem] = []
var _active: Array[TrackedItem] = []


func _init(scene: PackedScene, parent: Node3D) -> void:
	_scene = scene
	_parent = parent


func spawn(xform: Transform3D, item_id: String, item_properties: Dictionary) -> TrackedItem:
	var item: TrackedItem = _pool.pop_back() if not _pool.is_empty() else _create()
	if item.get_parent() != _parent:
		item.reparent(_parent, false)
	item.global_transform = xform
	item.freeze = false
	item.linear_velocity = Vector3.ZERO
	item.angular_velocity = Vector3.ZERO
	item.visible = true
	item.process_mode = Node.PROCESS_MODE_INHERIT
	item.configure(item_id, item_properties)
	_active.append(item)
	item_spawned.emit(item)
	return item


func get_active_items() -> Array[TrackedItem]:
	return _active


func get_parent_node() -> Node3D:
	return _parent


func _create() -> TrackedItem:
	var item: TrackedItem = _scene.instantiate()
	_parent.add_child(item)
	item.retired.connect(_on_retired)
	return item


func _on_retired(item: TrackedItem) -> void:
	_active.erase(item)
	item.visible = false
	item.freeze = true
	item.process_mode = Node.PROCESS_MODE_DISABLED
	item.reparent(_parent, false)
	item.position = Vector3(0, -10, 0)
	_pool.append(item)
