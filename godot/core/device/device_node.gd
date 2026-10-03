class_name DeviceNode
extends Node3D
## Root node of every device scene. Owns the device's FMI model instance and drives its
## environment probes (physical stimuli -> model inputs) and views (model outputs -> 3D).
##
## The composition root (factory) calls, in this order:
##   device_id/geometry/services = ...; create_model(params); <master initialize>;
##   then every physics frame: sample_probes(dt) -> <master step> -> apply_views(dt).

## Behaviour model: a script extending Fmi3CoSimulation.
@export var model_script: Script
## FMI 3.0 model description of the behaviour model.
@export_file("*.xml") var model_description_path := ""

var device_id := ""
## Geometry/scene options from the layout (e.g. conveyor length), read by views and probes.
var geometry := {}
var model: Fmi3CoSimulation
## Scoped services injected by the composition root (e.g. "item_factory", "item_parent").
var services := {}
var _probes: Array[DeviceProbe] = []
var _views: Array[DeviceView] = []


func create_model(parameters: Dictionary) -> Fmi3CoSimulation:
	var md := Fmi3ModelDescription.load_file(model_description_path)
	model = model_script.new()
	if model.instantiate(device_id, md) != Fmi3.Status.OK:
		push_error("Device %s: instantiate failed" % device_id)
		return null
	for key in parameters:
		if model.set_value(key, parameters[key]) != Fmi3.Status.OK:
			push_error("Device %s: cannot set parameter '%s'" % [device_id, key])
	_collect(self)
	for probe in _probes:
		probe.bind(self)
	for view in _views:
		view.bind(self)
	return model


func sample_probes(delta: float) -> void:
	for probe in _probes:
		probe.sample(model, delta)


func apply_views(delta: float) -> void:
	for view in _views:
		view.apply(model, delta)


## Converts a world position into the device's own coordinate frame (override for devices whose
## frame differs from the node frame, e.g. a Z-up robot base frame).
func world_to_device_frame(world_position: Vector3) -> Vector3:
	return to_local(world_position)


## Returns a named marker (Node3D) of this device, e.g. "PickPoint" or "Outlet".
func get_marker(marker_name: String) -> Node3D:
	return find_child(marker_name, true, false) as Node3D


func _collect(node: Node) -> void:
	for child in node.get_children():
		if child is DeviceNode:
			continue
		if child is DeviceProbe:
			_probes.append(child)
		elif child is DeviceView:
			_views.append(child)
		_collect(child)
