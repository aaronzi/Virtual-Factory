extends Fmi3CoSimulation
## Test FMU: integrates `rate` while `enable` is true.


func _on_step(_t: float, h: float) -> int:
	if _get_var("enable"):
		_set_var("value", _get_var("value") + _get_var("rate") * h)
	_set_var("enabled_out", _get_var("enable"))
	return Fmi3.Status.OK
