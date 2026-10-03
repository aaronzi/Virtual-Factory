class_name TrapezoidProfile
extends RefCounted
## Trapezoidal (or triangular) velocity profile over a distance; fraction(t) returns progress 0..1.

var distance := 0.0
var duration := 0.0
var _vmax := 0.0
var _amax := 0.0
var _ta := 0.0


func _init(p_distance: float, vmax: float, amax: float) -> void:
	distance = absf(p_distance)
	if distance < 1e-9 or vmax <= 0.0 or amax <= 0.0:
		return
	_amax = amax
	_ta = vmax / amax
	if amax * _ta * _ta >= distance:
		_ta = sqrt(distance / amax)
		_vmax = amax * _ta
		duration = 2.0 * _ta
	else:
		_vmax = vmax
		duration = 2.0 * _ta + (distance - amax * _ta * _ta) / vmax


func fraction(t: float) -> float:
	if duration <= 0.0:
		return 1.0
	t = clampf(t, 0.0, duration)
	var s := 0.0
	if t < _ta:
		s = 0.5 * _amax * t * t
	elif t <= duration - _ta:
		s = 0.5 * _amax * _ta * _ta + _vmax * (t - _ta)
	else:
		var td := duration - t
		s = distance - 0.5 * _amax * td * td
	return s / distance
