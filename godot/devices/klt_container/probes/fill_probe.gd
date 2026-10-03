extends DeviceProbe
## Presence sensing of items resting inside the container (Area3D over the inner volume).

var _area: Area3D


func bind(p_device: DeviceNode) -> void:
	super.bind(p_device)
	_area = Area3D.new()
	_area.name = "FillArea"
	_area.collision_layer = 0
	_area.collision_mask = PhysicsLayers.ITEMS
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = KltGeometry.OUTER - Vector3(0.04, 0.0, 0.04)
	shape.shape = box
	shape.position.y = KltGeometry.floor_height(device.geometry) + box.size.y * 0.5
	_area.add_child(shape)
	add_child(_area)


func sample(model: Fmi3CoSimulation, _delta: float) -> void:
	model.set_value("item_count_measured", get_resting_items().size())


func get_resting_items() -> Array[TrackedItem]:
	var items: Array[TrackedItem] = []
	for body in _area.get_overlapping_bodies():
		if body is TrackedItem and not body.is_attached() and body.visible:
			items.append(body)
	return items
