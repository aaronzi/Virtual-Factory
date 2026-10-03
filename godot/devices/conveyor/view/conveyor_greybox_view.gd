extends DeviceView
## Greybox conveyor: aluminium frame, legs, rollers, gear motor, side guides and a moving belt.
## Transport is physical: the belt body's constant_linear_velocity carries items (Jolt).
## Device origin = belt top surface, centre of the belt; local +X = transport direction.

const FRAME := Color(0.72, 0.74, 0.76)
const MOTOR := Color(0.2, 0.35, 0.55)

var _belt_body: StaticBody3D
var _belt_material: ShaderMaterial
var _rollers: Array[Node3D] = []
var _roller_radius := 0.03


func bind(p_device: DeviceNode) -> void:
	super.bind(p_device)
	var g := device.geometry
	var length: float = g.get("length", 3.0)
	var width: float = g.get("width", 0.3)
	var height: float = g.get("height", 0.85)
	_build_belt(length, width)
	_build_frame(length, width, height)
	_build_guides(length, g.get("guide_gap", 0.08))
	_build_motor(length, width)


func apply(model: Fmi3CoSimulation, _delta: float) -> void:
	var v: float = model.get_value("belt_speed")
	var pos: float = model.get_value("belt_position")
	_belt_body.constant_linear_velocity = device.global_basis.x * v
	_belt_material.set_shader_parameter("offset", pos)
	for roller in _rollers:
		roller.rotation.z = -pos / _roller_radius


func _build_belt(length: float, width: float) -> void:
	_belt_body = StaticBody3D.new()
	_belt_body.name = "BeltBody"
	_belt_body.collision_layer = PhysicsLayers.WORLD
	add_child(_belt_body)
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(length, 0.04, width)
	shape.shape = box
	shape.position.y = -0.02
	_belt_body.add_child(shape)
	_belt_body.physics_material_override = PhysicsMaterial.new()
	_belt_body.physics_material_override.friction = 1.0
	_belt_material = ShaderMaterial.new()
	_belt_material.shader = preload("res://devices/conveyor/view/belt.gdshader")
	_belt_material.set_shader_parameter("length_m", length)
	var plane := PlaneMesh.new()
	plane.size = Vector2(length, width)
	var top := MeshInstance3D.new()
	top.mesh = plane
	top.material_override = _belt_material
	top.position.y = 0.0005
	_belt_body.add_child(top)
	Greybox.box(_belt_body, Vector3(length, 0.02, width), Vector3(0, -0.0105, 0),
		Greybox.material(Color(0.1, 0.11, 0.11), 0.9))


func _build_frame(length: float, width: float, height: float) -> void:
	var alu := Greybox.material(FRAME, 0.35, 0.7)
	for side in [-1.0, 1.0]:
		Greybox.box(self, Vector3(length + 0.08, 0.08, 0.03), Vector3(0, -0.05, side * (width * 0.5 + 0.015)), alu)
		for x in [-length * 0.5 + 0.1, length * 0.5 - 0.1]:
			Greybox.box(self, Vector3(0.04, height - 0.09, 0.04),
				Vector3(x, -0.09 - (height - 0.09) * 0.5, side * (width * 0.5 + 0.015)), alu)
	for x in [-length * 0.5 + 0.1, length * 0.5 - 0.1]:
		Greybox.box(self, Vector3(0.04, 0.04, width), Vector3(x, -height * 0.6, 0), alu)
	var roller_mat := Greybox.material(Color(0.5, 0.52, 0.55), 0.3, 0.8)
	for x in [-length * 0.5, length * 0.5]:
		var pivot := Node3D.new()
		pivot.position = Vector3(x, -_roller_radius, 0)
		add_child(pivot)
		Greybox.cylinder(pivot, _roller_radius, width + 0.01, Vector3.ZERO, roller_mat, Vector3.BACK)
		var marker_mat := Greybox.material(Color(0.3, 0.3, 0.32))
		Greybox.box(pivot, Vector3(0.008, 0.059, width + 0.012), Vector3.ZERO, marker_mat)
		_rollers.append(pivot)


func _build_guides(length: float, gap: float) -> void:
	var guides := StaticBody3D.new()
	guides.name = "Guides"
	guides.collision_layer = PhysicsLayers.WORLD
	add_child(guides)
	var mat := Greybox.material(Color(0.85, 0.85, 0.82), 0.3, 0.5)
	for side in [-1.0, 1.0]:
		var z: float = side * (gap * 0.5 + 0.005)
		Greybox.box(guides, Vector3(length - 0.1, 0.03, 0.01), Vector3(0, 0.017, z), mat)
		var shape := CollisionShape3D.new()
		var box := BoxShape3D.new()
		box.size = Vector3(length - 0.1, 0.03, 0.01)
		shape.shape = box
		shape.position = Vector3(0, 0.017, z)
		guides.add_child(shape)


func _build_motor(length: float, width: float) -> void:
	var mat := Greybox.material(MOTOR, 0.5, 0.2)
	var z := -(width * 0.5 + 0.09)
	Greybox.cylinder(self, 0.045, 0.16, Vector3(length * 0.5, -0.03, z - 0.05), mat, Vector3.BACK)
	Greybox.box(self, Vector3(0.1, 0.1, 0.08), Vector3(length * 0.5, -0.03, z + 0.04), mat)
