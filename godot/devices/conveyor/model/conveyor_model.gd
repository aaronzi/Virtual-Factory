extends Fmi3CoSimulation
## Belt conveyor behaviour: VFD ramp towards the setpoint, belt travel, electrical power.

var _meter := EnergyMeter.new()


func _on_step(_t: float, h: float) -> int:
	var target := 0.0
	if _get_var("run"):
		target = clampf(_get_var("speed_setpoint"), 0.0, _get_var("max_speed"))
		target *= -1.0 if _get_var("reverse") else 1.0
	var v: float = _get_var("belt_speed")
	v = move_toward(v, target, _get_var("acceleration") * h)
	var moving := absf(v) > 1e-4
	_set_var("belt_speed", v)
	_set_var("belt_position", _get_var("belt_position") + v * h)
	_set_var("running", moving)
	var power: float = _get_var("standby_power")
	if moving or _get_var("run"):
		power += _get_var("no_load_power") + _get_var("speed_power_coefficient") * absf(v)
	_meter.integrate(power, h, moving)
	_set_var("power", power)
	_set_var("energy", _meter.energy_kwh)
	_set_var("operating_hours", _meter.operating_hours)
	return Fmi3.Status.OK


func _on_reset() -> void:
	_meter = EnergyMeter.new()


func _save_internal_state() -> Dictionary:
	return {"meter": _meter.save()}


func _load_internal_state(s: Dictionary) -> void:
	_meter.load(s.get("meter", {}))
