extends DeviceView
## Physical effect of the gripper: attaches the gripped item to the TCP when the grasp succeeds and
## releases it into the world when the gripper opens.

var _held: TrackedItem = null
var _last_grasp := false
var _last_closed := false


func apply(model: Fmi3CoSimulation, _delta: float) -> void:
	var grasp: bool = model.get_value("grasp_ok")
	var closed: bool = model.get_value("gripper_closed")
	if grasp and not _last_grasp and _held == null:
		_held = device.get_node("Base/TCP/GripProbe").get_item_in_grip()
		if _held:
			_held.attach_to(device.get_node("Base/TCP"))
	if _last_closed and not closed and _held != null:
		var factory: ItemFactory = device.services.get("item_factory")
		_held.detach(factory.get_parent_node() if factory else device.get_parent())
		_held = null
	_last_grasp = grasp
	_last_closed = closed
