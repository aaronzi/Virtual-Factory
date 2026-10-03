extends Fmi3CoSimulation
## Belt conveyor behaviour: VFD ramp towards the setpoint, belt travel, electrical power.
## Fault injection: `motor_fault` trips the drive - the belt coasts down with `coast_deceleration`,
## the VFD draws standby power only and `fault` is set until the input is cleared.

var _meter := EnergyMeter.new()


func _on_step(_t: float, h: float) -> int:
	var tripped: bool = _get_var("motor_fault")
	var drive_on: bool = _get_var("run") and not tripped
	var target := 0.0
	if drive_on:
		target = clampf(_get_var("speed_setpoint"), 0.0, _get_var("max_speed"))
		target *= -1.0 if _get_var("reverse") else 1.0
	var rate: float = _get_var("coast_deceleration") if tripped else _get_var("acceleration")
	var v: float = move_toward(_get_var("belt_speed"), target, rate * h)
	var moving := absf(v) > 1e-4
	_set_var("belt_speed", v)
	_set_var("belt_position", _get_var("belt_position") + v * h)
	_set_var("running", moving)
	_set_var("fault", tripped)
	var power: float = _get_var("standby_power")
	if not tripped and (moving or _get_var("run")):
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
