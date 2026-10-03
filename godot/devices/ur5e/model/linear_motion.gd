class_name Ur5eLinearMotion
extends RefCounted
## movel: straight-line TCP motion with constant tool orientation; IK solved per sample, choosing
## the solution closest to the previous configuration.

var duration := 0.0
var _p0: Vector3
var _p1: Vector3
var _tool_basis: Basis
var _tool_length := 0.0
var _profile: TrapezoidProfile


func _init(p0: Vector3, p1: Vector3, tool_basis: Basis, tool_length: float, vmax: float, amax: float) -> void:
	_p0 = p0
	_p1 = p1
	_tool_basis = tool_basis
	_tool_length = tool_length
	_profile = TrapezoidProfile.new(p0.distance_to(p1), vmax, amax)
	duration = _profile.duration


func sample(t: float, q_prev: PackedFloat64Array) -> PackedFloat64Array:
	var tcp := _p0.lerp(_p1, _profile.fraction(t))
	return UrKinematics.inverse_closest(flange_pose(tcp, _tool_basis, _tool_length), q_prev)


## Flange pose for a TCP position with the given tool orientation (tool Z = approach direction).
static func flange_pose(tcp: Vector3, tool_basis: Basis, tool_length: float) -> Transform3D:
	return Transform3D(tool_basis, tcp - tool_basis.z * tool_length)
