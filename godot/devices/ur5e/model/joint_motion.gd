class_name Ur5eJointMotion
extends RefCounted
## movej: synchronised joint-space motion; the joint with the largest travel follows a trapezoidal
## profile and all others are scaled to finish at the same time.

var duration := 0.0
var _q0: PackedFloat64Array
var _q1: PackedFloat64Array
var _profile: TrapezoidProfile


func _init(q0: PackedFloat64Array, q1: PackedFloat64Array, vmax: float, amax: float) -> void:
	_q0 = q0
	_q1 = q1
	var lead := 0.0
	for i in 6:
		lead = maxf(lead, absf(q1[i] - q0[i]))
	_profile = TrapezoidProfile.new(lead, vmax, amax)
	duration = _profile.duration


## Joint angles at time t; empty array on failure (never for movej).
func sample(t: float, _q_prev: PackedFloat64Array) -> PackedFloat64Array:
	var s := _profile.fraction(t)
	var q := PackedFloat64Array()
	for i in 6:
		q.append(lerpf(_q0[i], _q1[i], s))
	return q
