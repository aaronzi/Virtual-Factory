extends DeviceProbe
## Detects an item between the gripper fingers (Area3D at the TCP).

var _area: Area3D


func bind(p_device: DeviceNode) -> void:
	super.bind(p_device)
	_area = Area3D.new()
	_area.collision_layer = 0
	_area.collision_mask = PhysicsLayers.ITEMS
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(0.06, 0.03, 0.03)
	shape.shape = box
	_area.add_child(shape)
	add_child(_area)


func sample(model: Fmi3CoSimulation, _delta: float) -> void:
	var item := get_item_in_grip()
	model.set_value("object_in_grip", item != null)
	model.set_value("object_width", item.get_grip_width() if item else 0.0)


func get_item_in_grip() -> TrackedItem:
	for body in _area.get_overlapping_bodies():
		if body is TrackedItem and body.visible:
			return body
	return null
