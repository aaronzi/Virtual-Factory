class_name HallGreybox
extends Node3D
## Procedural greybox of the factory hall (placeholder until the Blender hall in M2).
## Origin = hall floor centre. +X = along the line (material flow), -Z = back wall.

const COLOR_FLOOR := Color(0.55, 0.56, 0.57)
const COLOR_EPOXY := Color(0.42, 0.52, 0.49)
const COLOR_WALL := Color(0.80, 0.81, 0.80)
const COLOR_WALL_BASE := Color(0.33, 0.37, 0.41)
const COLOR_COLUMN := Color(0.22, 0.34, 0.46)
const COLOR_MARKING := Color(0.95, 0.75, 0.05)

@export var size := Vector2(36.0, 24.0)          ## floor X × Z in metres
@export var wall_height := 9.0
@export var column_spacing := 6.0
@export var production_zone := Rect2(-9.0, -6.0, 18.0, 10.0)  ## epoxy area (X, Z, w, d)


func _ready() -> void:
	_build_floor()
	_build_walls()
	_build_columns()
	_build_markings()


func _build_floor() -> void:
	var body := StaticBody3D.new()
	body.name = "Floor"
	add_child(body)
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(size.x, 0.2, size.y)
	shape.shape = box
	shape.position.y = -0.1
	body.add_child(shape)
	_add_box(body, Vector3(size.x, 0.02, size.y), Vector3(0, -0.01, 0), COLOR_FLOOR, 0.9)
	var zone_center := production_zone.get_center()
	_add_box(body, Vector3(production_zone.size.x, 0.004, production_zone.size.y),
		Vector3(zone_center.x, 0.002, zone_center.y), COLOR_EPOXY, 0.35)


func _build_walls() -> void:
	var walls := Node3D.new()
	walls.name = "Walls"
	add_child(walls)
	var half := size * 0.5
	var t := 0.3
	# back, left, right walls (front left open so the default camera sees in)
	for spec in [
		[Vector3(size.x, wall_height, t), Vector3(0, wall_height * 0.5, -half.y - t * 0.5)],
		[Vector3(t, wall_height, size.y), Vector3(-half.x - t * 0.5, wall_height * 0.5, 0)],
		[Vector3(t, wall_height, size.y), Vector3(half.x + t * 0.5, wall_height * 0.5, 0)],
	]:
		_add_box(walls, spec[0], spec[1], COLOR_WALL, 0.95)
		var base_size: Vector3 = spec[0]
		base_size.y = 1.2
		var base_pos: Vector3 = spec[1]
		base_pos.y = 0.6
		_add_box(walls, base_size * Vector3(1.002, 1, 1.002), base_pos, COLOR_WALL_BASE, 0.8)


func _build_columns() -> void:
	var columns := Node3D.new()
	columns.name = "Columns"
	add_child(columns)
	var half := size * 0.5
	var x := -half.x + column_spacing
	while x < half.x - 0.1:
		for z in [-half.y + 0.35, half.y - 0.35]:
			_add_box(columns, Vector3(0.4, wall_height, 0.4), Vector3(x, wall_height * 0.5, z),
				COLOR_COLUMN, 0.6)
		x += column_spacing


func _build_markings() -> void:
	var marks := Node3D.new()
	marks.name = "FloorMarkings"
	add_child(marks)
	var r := production_zone
	var w := 0.1
	var y := 0.006
	_add_box(marks, Vector3(r.size.x, 0.002, w), Vector3(r.get_center().x, y, r.position.y), COLOR_MARKING, 0.5)
	_add_box(marks, Vector3(r.size.x, 0.002, w), Vector3(r.get_center().x, y, r.end.y), COLOR_MARKING, 0.5)
	_add_box(marks, Vector3(w, 0.002, r.size.y), Vector3(r.position.x, y, r.get_center().y), COLOR_MARKING, 0.5)
	_add_box(marks, Vector3(w, 0.002, r.size.y), Vector3(r.end.x, y, r.get_center().y), COLOR_MARKING, 0.5)
	# walkway along the front of the production zone
	_add_box(marks, Vector3(size.x - 2.0, 0.002, w), Vector3(0, y, r.end.y + 1.5), COLOR_MARKING, 0.5)


func _add_box(
		parent: Node3D, box_size: Vector3, pos: Vector3, color: Color, roughness: float
) -> MeshInstance3D:
	var mesh := BoxMesh.new()
	mesh.size = box_size
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.roughness = roughness
	mesh.material = mat
	var inst := MeshInstance3D.new()
	inst.mesh = mesh
	inst.position = pos
	parent.add_child(inst)
	return inst
