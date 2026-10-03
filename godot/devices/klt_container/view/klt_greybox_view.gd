extends DeviceView
## Greybox KLT on a stand. Executes exchanges: on each new exchange event, the items inside are
## removed (the full container is carried away and replaced by an empty one).

var _last_exchange_count := 0


func bind(p_device: DeviceNode) -> void:
	super.bind(p_device)
	var g := device.geometry
	var color: Color = Color.from_string(g.get("color", "#2f5f9e"), Color(0.18, 0.37, 0.62))
	var stand_h: float = g.get("stand_height", 0.55)
	_build_stand(stand_h)
	_build_box(stand_h, Greybox.material(color, 0.7))
	var corners := KltGeometry.slot_corners(g)
	for i in 3:
		var marker := Marker3D.new()
		marker.name = ["SlotOrigin", "SlotRowEnd", "SlotColEnd"][i]
		marker.position = corners[i]
		add_child(marker)


func apply(model: Fmi3CoSimulation, _delta: float) -> void:
	var count: int = model.get_value("exchange_count")
	if count == _last_exchange_count:
		return
	_last_exchange_count = count
	for item in device.get_node("FillProbe").get_resting_items():
		item.retire()


func _build_stand(stand_h: float) -> void:
	var steel := Greybox.material(Color(0.3, 0.32, 0.35), 0.5, 0.5)
	Greybox.box(self, Vector3(0.46, 0.03, 0.66), Vector3(0, stand_h - 0.015, 0), steel)
	for x in [-0.2, 0.2]:
		for z in [-0.3, 0.3]:
			Greybox.box(self, Vector3(0.03, stand_h - 0.03, 0.03), Vector3(x, (stand_h - 0.03) * 0.5, z), steel)
	var body := StaticBody3D.new()
	body.collision_layer = PhysicsLayers.WORLD
	add_child(body)
	_add_shape(body, Vector3(0.46, 0.03, 0.66), Vector3(0, stand_h - 0.015, 0))


func _build_box(stand_h: float, mat: Material) -> void:
	var o := KltGeometry.OUTER
	var w := KltGeometry.WALL
	var body := StaticBody3D.new()
	body.name = "Box"
	body.collision_layer = PhysicsLayers.WORLD
	add_child(body)
	var parts := [
		[Vector3(o.x, w, o.z), Vector3(0, stand_h + w * 0.5, 0)],
		[Vector3(w, o.y, o.z), Vector3(-o.x * 0.5 + w * 0.5, stand_h + o.y * 0.5, 0)],
		[Vector3(w, o.y, o.z), Vector3(o.x * 0.5 - w * 0.5, stand_h + o.y * 0.5, 0)],
		[Vector3(o.x, o.y, w), Vector3(0, stand_h + o.y * 0.5, -o.z * 0.5 + w * 0.5)],
		[Vector3(o.x, o.y, w), Vector3(0, stand_h + o.y * 0.5, o.z * 0.5 - w * 0.5)],
	]
	for p in parts:
		Greybox.box(body, p[0], p[1], mat)
		_add_shape(body, p[0], p[1])


func _add_shape(body: StaticBody3D, size: Vector3, pos: Vector3) -> void:
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = size
	shape.shape = box
	shape.position = pos
	body.add_child(shape)
