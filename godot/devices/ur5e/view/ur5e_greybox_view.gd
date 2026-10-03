extends DeviceView
## Greybox UR5e driven by forward kinematics of the model's joint angles: pedestal, joint housings,
## link tubes, flange and a 2-finger gripper. Also positions the shared "TCP" node.

const LINK := Color(0.83, 0.85, 0.86)
const CAP := Color(0.33, 0.52, 0.68)
const RADII := [0.06, 0.06, 0.05, 0.045, 0.045]

var _base: Node3D
var _tcp: Node3D
var _segments: Array[Node3D] = []
var _housings: Array[Node3D] = []
var _gripper: Node3D
var _fingers: Array[Node3D] = []
var _segment_lengths: Array[float] = []


func bind(p_device: DeviceNode) -> void:
	super.bind(p_device)
	_base = device.get_node("Base")
	_tcp = device.get_node("Base/TCP")
	var pedestal_h: float = device.geometry.get("pedestal_height", 0.75)
	var steel := Greybox.material(Color(0.25, 0.27, 0.3), 0.5, 0.4)
	Greybox.box(self, Vector3(0.22, pedestal_h - 0.02, 0.22), Vector3(0, (pedestal_h - 0.02) * 0.5, 0), steel)
	Greybox.box(self, Vector3(0.3, 0.02, 0.3), Vector3(0, pedestal_h - 0.01, 0), steel)
	Greybox.cylinder(_base, 0.075, 0.09, Vector3(0, 0.045, 0), Greybox.material(LINK, 0.4))
	_build_arm()
	_build_gripper()


func apply(model: Fmi3CoSimulation, _delta: float) -> void:
	var q := PackedFloat64Array()
	for i in 6:
		q.append(model.get_value("q%d" % (i + 1)))
	var frames := UrKinematics.forward_frames(q)
	var points: Array[Vector3] = [Vector3.ZERO]
	for f in frames:
		points.append(Ur5eDeviceFrames.to_base(f).origin)
	for i in 6:
		_place_segment(_segments[i], points[i], points[i + 1])
	for i in 5:
		var f := Ur5eDeviceFrames.to_base(frames[i])
		_housings[i].transform = Transform3D(f.basis, f.origin)
	var flange := Ur5eDeviceFrames.to_base(frames[5])
	_gripper.transform = flange
	var tool_length: float = model.get_value("tool_length")
	_tcp.transform = Transform3D(flange.basis, flange.origin + flange.basis.z * tool_length)
	var half: float = model.get_value("gripper_width") * 0.5
	_fingers[0].position.x = half + 0.006
	_fingers[1].position.x = -half - 0.006


func _build_arm() -> void:
	var link_mat := Greybox.material(LINK, 0.4)
	var cap_mat := Greybox.material(CAP, 0.4)
	var radii := [0.06, 0.055, 0.045, 0.04, 0.04, 0.035]
	for i in 6:
		var seg := Node3D.new()
		_base.add_child(seg)
		Greybox.cylinder(seg, radii[i], 1.0, Vector3.ZERO, link_mat)
		_segments.append(seg)
	for i in 5:
		var housing := Node3D.new()
		_base.add_child(housing)
		Greybox.cylinder(housing, RADII[i], RADII[i] * 2.4, Vector3.ZERO, cap_mat, Vector3.BACK)
		_housings.append(housing)


func _build_gripper() -> void:
	_gripper = Node3D.new()
	_base.add_child(_gripper)
	var dark := Greybox.material(Color(0.12, 0.12, 0.13), 0.5)
	Greybox.cylinder(_gripper, 0.032, 0.012, Vector3(0, 0, 0.006), Greybox.material(LINK, 0.4), Vector3.BACK)
	Greybox.box(_gripper, Vector3(0.11, 0.06, 0.07), Vector3(0, 0, 0.047), dark)
	for side in [1.0, -1.0]:
		var finger := Node3D.new()
		finger.position = Vector3(side * 0.04, 0, 0.12)
		_gripper.add_child(finger)
		var finger_mat := Greybox.material(Color(0.6, 0.62, 0.64), 0.3, 0.7)
		Greybox.box(finger, Vector3(0.012, 0.022, 0.07), Vector3.ZERO, finger_mat)
		_fingers.append(finger)


func _place_segment(seg: Node3D, a: Vector3, b: Vector3) -> void:
	var length := a.distance_to(b)
	if length < 1e-4:
		seg.visible = false
		return
	seg.visible = true
	var rot := Basis(Quaternion(Vector3.UP, (b - a) / length))
	seg.transform = Transform3D(rot * Basis.from_scale(Vector3(1, length, 1)), (a + b) * 0.5)
