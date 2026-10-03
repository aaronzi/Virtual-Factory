extends TrackedItem
## ISO 15552 pneumatic cylinder Ø32 × 80 mm (PC-32-80-DA-M), standing on its rear end cap.
## Origin = bottom centre. The protective end cap ("lid") is red (ok), missing, or blue (wrong).

const CAP_COLORS := {0: Color(0.78, 0.08, 0.10), 2: Color(0.10, 0.30, 0.80)}
const ALUMINIUM := Color(0.70, 0.71, 0.72)
const ANODISED := Color(0.78, 0.79, 0.80)
const CAP_ZONE_Y := 0.19
const HEIGHT := 0.235

var _cap: MeshInstance3D


func _ready() -> void:
	collision_layer = PhysicsLayers.ITEMS
	collision_mask = PhysicsLayers.WORLD | PhysicsLayers.ITEMS
	mass = 0.6
	physics_material_override = PhysicsMaterial.new()
	physics_material_override.friction = 0.8
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(0.047, HEIGHT, 0.047)
	shape.shape = box
	shape.position.y = HEIGHT * 0.5
	add_child(shape)
	_build_visual()


func configure(p_item_id: String, p_properties: Dictionary) -> void:
	super.configure(p_item_id, p_properties)
	var variant: int = p_properties.get("cap_variant", 0)
	_cap.visible = CAP_COLORS.has(variant)
	if _cap.visible:
		_cap.material_override = Greybox.material(CAP_COLORS[variant], 0.55)


func get_surface_color_at(world_point: Vector3) -> Color:
	if to_local(world_point).y < CAP_ZONE_Y:
		return ANODISED
	return CAP_COLORS.get(properties.get("cap_variant", 0), ALUMINIUM)


func get_grip_width() -> float:
	return 0.044


func _build_visual() -> void:
	var cast := Greybox.material(Color(0.62, 0.64, 0.66), 0.45, 0.8)
	var profile := Greybox.material(ANODISED, 0.3, 0.85)
	var steel := Greybox.material(Color(0.85, 0.86, 0.88), 0.15, 1.0)
	var brass := Greybox.material(Color(0.72, 0.58, 0.25), 0.35, 0.9)
	Greybox.box(self, Vector3(0.047, 0.024, 0.047), Vector3(0, 0.012, 0), cast)
	Greybox.box(self, Vector3(0.044, 0.150, 0.044), Vector3(0, 0.099, 0), profile)
	Greybox.box(self, Vector3(0.047, 0.024, 0.047), Vector3(0, 0.186, 0), cast)
	Greybox.cylinder(self, 0.006, 0.03, Vector3(0, 0.213, 0), steel)
	for y in [0.012, 0.186]:
		Greybox.cylinder(self, 0.005, 0.008, Vector3(0, y, 0.0275), brass, Vector3.BACK)
	_cap = Greybox.cylinder(self, 0.027, 0.045, Vector3(0, 0.2125, 0), Greybox.material(CAP_COLORS[0], 0.55))
