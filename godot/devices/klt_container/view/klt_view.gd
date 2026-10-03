extends ModelView
## KLT model on its stand: colour and label (A/B) from the layout geometry, palletizing teach markers,
## collision shapes, and exchange handling (items inside are retired when the KLT is exchanged).

var _last_exchange_count := 0


func bind(p_device: DeviceNode) -> void:
	super.bind(p_device)
	var g := device.geometry
	var box := part("Box") as MeshInstance3D
	var mat := box.get_active_material(0).duplicate() as BaseMaterial3D
	mat.albedo_color = Color.from_string(g.get("color", "#2f5f9e"), mat.albedo_color)
	box.material_override = mat
	var label: String = g.get("label", "A")
	part("LabelA").visible = label == "A"
	part("LabelB").visible = label == "B"
	var corners := KltGeometry.slot_corners(g)
	for i in 3:
		var marker := Marker3D.new()
		marker.name = ["SlotOrigin", "SlotRowEnd", "SlotColEnd"][i]
		marker.position = corners[i]
		add_child(marker)
	_build_physics(g.get("stand_height", 0.55))


func apply(model: Fmi3CoSimulation, _delta: float) -> void:
	var count: int = model.get_value("exchange_count")
	if count == _last_exchange_count:
		return
	_last_exchange_count = count
	for item in device.get_node("FillProbe").get_resting_items():
		item.retire()


func _build_physics(stand_h: float) -> void:
	var o := KltGeometry.OUTER
	var w := KltGeometry.WALL
	var body := StaticBody3D.new()
	body.collision_layer = PhysicsLayers.WORLD
	add_child(body)
	for p in [
		[Vector3(0.46, 0.03, 0.66), Vector3(0, stand_h - 0.015, 0)],
		[Vector3(o.x, w, o.z), Vector3(0, stand_h + w * 0.5, 0)],
		[Vector3(w, o.y, o.z), Vector3(-o.x * 0.5 + w * 0.5, stand_h + o.y * 0.5, 0)],
		[Vector3(w, o.y, o.z), Vector3(o.x * 0.5 - w * 0.5, stand_h + o.y * 0.5, 0)],
		[Vector3(o.x, o.y, w), Vector3(0, stand_h + o.y * 0.5, -o.z * 0.5 + w * 0.5)],
		[Vector3(o.x, o.y, w), Vector3(0, stand_h + o.y * 0.5, o.z * 0.5 - w * 0.5)],
	]:
		var shape := CollisionShape3D.new()
		var box := BoxShape3D.new()
		box.size = p[0]
		shape.shape = box
		shape.position = p[1]
		body.add_child(shape)
