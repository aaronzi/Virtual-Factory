extends Fmi3CoSimulation
## Light barrier behaviour: response-time filtered switching output with dark-on/light-on logic.

var _state := false
var _pending_time := 0.0
var _meter := EnergyMeter.new()


func _on_step(_t: float, h: float) -> int:
	var blocked: bool = _get_var("beam_blocked")
	var raw: bool = blocked if _get_var("dark_on") else not blocked
	if raw != _state:
		_pending_time += h
		if _pending_time >= _get_var("response_time") - 1e-9:
			_state = raw
			_pending_time = 0.0
			if _state:
				_set_var("switch_count", _get_var("switch_count") + 1)
	else:
		_pending_time = 0.0
	_set_var("signal", _state)
	var power: float = _get_var("rated_power")
	_meter.integrate(power, h)
	_set_var("power", power)
	_set_var("energy", _meter.energy_kwh)
	_set_var("operating_hours", _meter.operating_hours)
	return Fmi3.Status.OK


func _on_reset() -> void:
	_state = false
	_pending_time = 0.0
	_meter = EnergyMeter.new()


func _save_internal_state() -> Dictionary:
	return {"state": _state, "pending": _pending_time, "meter": _meter.save()}


func _load_internal_state(s: Dictionary) -> void:
	_state = s.get("state", false)
	_pending_time = s.get("pending", 0.0)
	_meter.load(s.get("meter", {}))
