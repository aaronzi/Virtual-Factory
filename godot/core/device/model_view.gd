class_name ModelView
extends DeviceView
## Device view based on an imported 3D model (.glb from blender/). Subclasses look up parts by name
## and animate them from model outputs.

@export var model_scene: PackedScene

var model_root: Node3D


func bind(p_device: DeviceNode) -> void:
	super.bind(p_device)
	model_root = model_scene.instantiate()
	_model_parent().add_child(model_root)


## Named part of the model (searched recursively), e.g. "J3", "LedSignal".
func part(part_name: String) -> Node3D:
	var node := model_root.find_child(part_name, true, false) as Node3D
	if node == null:
		push_error("%s: model part '%s' not found" % [device.device_id, part_name])
	return node


## Node the model is attached to (override, e.g. a robot base frame on a pedestal).
func _model_parent() -> Node3D:
	return self
