extends TrackedItem
## ISO 15552 pneumatic cylinder Ø32 × 80 mm (PC-32-80-DA-M), standing on its rear end cap.
## Origin = bottom centre. The protective end cap ("lid") is red (ok), missing, or blue (wrong).
## The type plate carries a QR code of the part's GS1 Digital Link (its globalAssetId, ADR-0023).

const MODEL := preload("res://products/cylinder/cylinder.glb")
const CAP_COLORS := {0: Color(0.78, 0.08, 0.10), 2: Color(0.10, 0.30, 0.80)}
const ALUMINIUM := Color(0.70, 0.71, 0.72)
const ANODISED := Color(0.78, 0.79, 0.80)
const CAP_ZONE_Y := 0.19
const HEIGHT := 0.235
const GTIN := "04099999032808"  # PC-32-80-DA-M

static var _cap_materials := {}
## Domain of the canonical Digital Links (set by the composition root from the backend configuration).
static var digital_link_domain := DigitalLink.DEFAULT_DOMAIN

var _cap: MeshInstance3D
var _label: CylinderLabel


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
	var model := MODEL.instantiate()
	add_child(model)
	_cap = model.find_child("Cap") as MeshInstance3D
	_label = CylinderLabel.new(model.find_child("Body") as MeshInstance3D,
		DigitalLink.product(GTIN, digital_link_domain))


func _exit_tree() -> void:
	if _label:
		_label.finish()


func configure(p_item_id: String, p_properties: Dictionary) -> void:
	super.configure(p_item_id, p_properties)
	var variant: int = p_properties.get("cap_variant", 0)
	_cap.visible = CAP_COLORS.has(variant)
	if _cap.visible:
		_cap.material_override = _cap_material(variant)
	_label.show_link(get_asset_id())


func get_asset_id() -> String:
	return DigitalLink.item(GTIN, item_id, digital_link_domain) if item_id != "" else ""


func get_surface_color_at(world_point: Vector3) -> Color:
	if to_local(world_point).y < CAP_ZONE_Y:
		return ANODISED
	return CAP_COLORS.get(properties.get("cap_variant", 0), ALUMINIUM)


func get_grip_width() -> float:
	return 0.044


func _cap_material(variant: int) -> Material:
	if not _cap_materials.has(variant):
		var mat := (_cap.get_active_material(0) as BaseMaterial3D).duplicate() as BaseMaterial3D
		mat.albedo_color = CAP_COLORS[variant]
		_cap_materials[variant] = mat
	return _cap_materials[variant]
