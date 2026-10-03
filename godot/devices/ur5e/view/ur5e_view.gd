extends ModelView
## UR5e model (ur5e.glb): joints J1..J6 rotate about their local Y axis (Blender local Z, DH frames),
## fingers follow the gripper width, and the device's Base/TCP node follows the model TCP.

const FINGER_OFFSET := 0.006  ## finger body centre beyond the gripping face

var _joints: Array[Node3D] = []
var _finger_a: Node3D
var _finger_b: Node3D
var _model_tcp: Node3D
var _tcp: Node3D


func bind(p_device: DeviceNode) -> void:
	super.bind(p_device)
	for i in 6:
		_joints.append(part("J%d" % (i + 1)))
	_finger_a = part("FingerA")
	_finger_b = part("FingerB")
	_model_tcp = part("TCP")
	_tcp = device.get_node("Base/TCP")


func apply(model: Fmi3CoSimulation, _delta: float) -> void:
	for i in 6:
		_joints[i].basis = Basis(Vector3.UP, model.get_value("q%d" % (i + 1)))
	var half: float = model.get_value("gripper_width") * 0.5 + FINGER_OFFSET
	_finger_a.position.x = half
	_finger_b.position.x = -half
	_tcp.global_transform = _model_tcp.global_transform


func _model_parent() -> Node3D:
	return device.get_node("Base")
