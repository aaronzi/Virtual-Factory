class_name Ur5eDeviceFrames
extends RefCounted
## Robot base frame (Z-up) -> Godot Base node frame (Y-up).

const ROBOT_TO_GODOT := Basis(Vector3(1, 0, 0), Vector3(0, 0, -1), Vector3(0, 1, 0))


static func to_base(t: Transform3D) -> Transform3D:
	return Transform3D(ROBOT_TO_GODOT, Vector3.ZERO) * t
