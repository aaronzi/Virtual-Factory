class_name PlcProcessImage
extends RefCounted
## Process image of a controller FMU as seen by its communication module: every input, output and
## parameter. changes() returns the values that changed since the last call (all values if `full`).

var _fmu: Fmi3CoSimulation
var _points: Array[Point] = []


func _init(fmu: Fmi3CoSimulation) -> void:
	_fmu = fmu
	for v in fmu.model_description.variables:
		if v.causality in [Fmi3.Causality.INPUT, Fmi3.Causality.OUTPUT, Fmi3.Causality.PARAMETER]:
			_points.append(Point.new(v.name, v.value_reference))


## {variable: JSON-safe value} of the changed (or all) variables.
func changes(full := false) -> Dictionary:
	var out := {}
	for p in _points:
		var value: Variant = _fmu.get_value_by_vr(p.vr)
		if full or not p.sent or value != p.last:
			out[p.name] = UnsConfig.json_value(value)
			p.last = value
			p.sent = true
	return out


func size() -> int:
	return _points.size()


## One variable of the image.
class Point:
	var name := ""
	var vr := 0
	var last: Variant
	var sent := false

	func _init(p_name: String, p_vr: int) -> void:
		name = p_name
		vr = p_vr
