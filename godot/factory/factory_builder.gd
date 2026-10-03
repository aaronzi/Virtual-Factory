class_name FactoryBuilder
extends RefCounted
## Builds the factory from a layout file (composition root, ADR-0006):
##   1. instantiate device scenes (res://devices/<type>/<type>.tscn) and their FMI models, place props
##   2. instantiate the PLC program (also an FMI model)
##   3. teach robot positions from device markers ("commissioning")
##   4. connect FMI variables and initialise the co-simulation master

var master := CoSimMaster.new()
var devices: Dictionary = {}  ## id -> DeviceNode
var item_factory: ItemFactory
var layout: Dictionary = {}


func build(layout_path: String, root: Node3D, items_root: Node3D) -> Error:
	layout = _load_json(layout_path)
	if layout.is_empty():
		return ERR_PARSE_ERROR
	item_factory = ItemFactory.new(load(layout.product.scene), items_root)
	for spec in layout.devices:
		if not _add_device(spec, root):
			return ERR_CANT_CREATE
	for prop in layout.get("props", []):
		_add_prop(prop, root)
	_teach(layout.get("teach", []))
	_add_controller(layout.controller)
	for conn in layout.get("connections", []):
		if master.connect_variables(conn[0], conn[1]) != OK:
			return ERR_INVALID_DATA
	master.initialize()
	return OK


func _add_device(spec: Dictionary, root: Node3D) -> bool:
	var scene: PackedScene = load("res://devices/%s/%s.tscn" % [spec.type, spec.type])
	if scene == null:
		push_error("FactoryBuilder: unknown device type '%s'" % spec.type)
		return false
	var device: DeviceNode = scene.instantiate()
	device.name = spec.id
	device.device_id = spec.id
	device.geometry = _geometry(spec.get("geometry", {}))
	device.services = {"item_factory": item_factory}
	root.add_child(device)
	var p: Array = spec.get("position", [0, 0, 0])
	device.position = Vector3(p[0], p[1], p[2])
	device.rotation_degrees.y = spec.get("rotation_deg", 0.0)
	var model := device.create_model(spec.get("parameters", {}))
	if model == null:
		return false
	master.add_instance(model)
	devices[spec.id] = device
	return true


## Static scenery placed with the line (fence, cabinet, HMI stand); moves along on reorganisation.
func _add_prop(spec: Dictionary, root: Node3D) -> void:
	var prop: Node3D = (load(spec.scene) as PackedScene).instantiate()
	root.add_child(prop)
	var p: Array = spec.get("position", [0, 0, 0])
	prop.position = Vector3(p[0], p[1], p[2])
	prop.rotation_degrees.y = spec.get("rotation_deg", 0.0)


func _add_controller(spec: Dictionary) -> void:
	var program: Fmi3CoSimulation = load(spec.program).new()
	program.instantiate(spec.id, Fmi3ModelDescription.load_file(spec.model_description))
	for key in spec.get("parameters", {}):
		program.set_value(key, spec.parameters[key])
	master.add_instance(program)


## Sets <parameter>_x/_y/_z of a device from the position of a marker of another device,
## expressed in the target device's own frame (like teaching a robot point).
func _teach(entries: Array) -> void:
	for entry in entries:
		var path: PackedStringArray = entry.marker.split("/")
		var marker := (devices[path[0]] as DeviceNode).get_marker(path[1])
		if marker == null:
			push_error("FactoryBuilder: teach marker %s not found" % entry.marker)
			continue
		var target: DeviceNode = devices[entry.device]
		var p := target.world_to_device_frame(marker.global_position)
		for axis in ["x", "y", "z"]:
			target.model.set_value("%s_%s" % [entry.parameter, axis], p[axis])


static func _geometry(raw: Dictionary) -> Dictionary:
	var g := {}
	for key in raw:
		var v: Variant = raw[key]
		g[key] = Vector3(v[0], v[1], v[2]) if v is Array and v.size() == 3 else v
	return g


static func _load_json(path: String) -> Dictionary:
	var text := FileAccess.get_file_as_string(path)
	var data: Variant = JSON.parse_string(text)
	if not data is Dictionary:
		push_error("FactoryBuilder: cannot parse layout %s" % path)
		return {}
	return data
