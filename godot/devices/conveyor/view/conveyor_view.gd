extends ModelView
## Conveyor assembled from the modular parts in conveyor_parts.glb for the configured length.
## Transport is physical: the belt body's constant_linear_velocity carries items (ADR-0009).
## Device origin = belt top surface, centre of the belt; local +X = transport direction.

const DRUM_RADIUS := 0.03
const LEG_SPACING := 1.4
const BRACKET_SPACING := 0.8

var _belt_body: StaticBody3D
var _belt_material: ShaderMaterial
var _drums: Array[Node3D] = []
var _static: Node3D  ## temporary parent of static parts before merging


func bind(p_device: DeviceNode) -> void:
	super.bind(p_device)
	model_root.visible = false  # parts library; copies are placed below
	var g := device.geometry
	var length: float = g.get("length", 3.0)
	var gap: float = g.get("guide_gap", 0.08)
	_belt_material = ShaderMaterial.new()
	_belt_material.shader = preload("res://devices/conveyor/view/belt.gdshader")
	_belt_material.set_shader_parameter("length_m", length)
	var belt := part("Belt").duplicate() as MeshInstance3D
	add_child(belt)
	belt.position = part("Belt").position
	belt.scale.x = length
	belt.material_override = _belt_material
	_static = Node3D.new()
	add_child(_static)
	_place("FrameSection", Vector3.ZERO, length)
	_place("BeltBody", Vector3.ZERO, length)
	for end in [["DriveEnd", "DriveDrum", 1.0], ["IdlerEnd", "IdlerDrum", -1.0]]:
		var unit := _place(end[0], Vector3(end[2] * length / 2, 0, 0))
		var drum := unit.get_node(end[1]) as Node3D
		drum.reparent(self)
		_drums.append(drum)
	_place_repeated(length, gap)
	MeshMerger.merge(_static, self, "StaticParts")
	_static.queue_free()
	_build_physics(length, g.get("width", 0.3), gap)


func apply(model: Fmi3CoSimulation, _delta: float) -> void:
	var pos: float = model.get_value("belt_position")
	_belt_body.constant_linear_velocity = device.global_basis.x * float(model.get_value("belt_speed"))
	_belt_material.set_shader_parameter("offset", pos)
	for drum in _drums:
		drum.rotation.z = -pos / DRUM_RADIUS


func _place_repeated(length: float, gap: float) -> void:
	var legs := maxi(2, ceili(length / LEG_SPACING) + 1)
	for i in legs:
		_place("Leg", Vector3(lerpf(-length / 2 + 0.15, length / 2 - 0.15, float(i) / (legs - 1)), 0, 0))
	for side in [-1.0, 1.0]:
		var rail := _place("GuideRail", Vector3(0, 0, side * (gap / 2 + 0.003)), length - 0.1)
		rail.rotation.y = 0.0 if side < 0.0 else PI
		var n := maxi(2, floori(length / BRACKET_SPACING))
		for i in n:
			var x := lerpf(-length / 2 + 0.3, length / 2 - 0.3, float(i) / (n - 1))
			_place("GuideBracket", Vector3(x, 0, 0)).rotation.y = 0.0 if side < 0.0 else PI
	for x in [-length / 4, length / 4]:
		_place("FlowArrow", Vector3(x, 0, 0))


## Copies a static part of the library to `offset` (added to the part's own position) and stretches it
## along X to `length` metres (parts are modelled 1 m long) if given. Static parts are merged later.
func _place(part_name: String, offset: Vector3, length := 0.0) -> Node3D:
	var src := part(part_name)
	var copy := src.duplicate() as Node3D
	_static.add_child(copy)
	copy.position = src.position + offset
	if length > 0.0:
		copy.scale.x = length
	return copy


func _build_physics(length: float, width: float, gap: float) -> void:
	_belt_body = StaticBody3D.new()
	_belt_body.name = "BeltBody"
	_belt_body.collision_layer = PhysicsLayers.WORLD
	_belt_body.physics_material_override = PhysicsMaterial.new()
	_belt_body.physics_material_override.friction = 1.0
	add_child(_belt_body)
	_add_box(_belt_body, Vector3(length, 0.04, width), Vector3(0, -0.02, 0))
	var guides := StaticBody3D.new()
	guides.collision_layer = PhysicsLayers.WORLD
	add_child(guides)
	for side in [-1.0, 1.0]:
		_add_box(guides, Vector3(length - 0.1, 0.03, 0.01), Vector3(0, 0.017, side * (gap / 2 + 0.005)))


func _add_box(body: StaticBody3D, size: Vector3, pos: Vector3) -> void:
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = size
	shape.shape = box
	shape.position = pos
	body.add_child(shape)
