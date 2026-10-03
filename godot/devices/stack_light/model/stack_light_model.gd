extends Fmi3CoSimulation
## Signal tower: the LED segments and the buzzer follow their inputs (no internal logic, the PLC decides
## the meaning); power = standby + lamp_power per lit segment + buzzer_power.

const SEGMENTS := ["green", "amber", "red", "buzzer"]

var _meter := EnergyMeter.new()


func _on_step(_t: float, h: float) -> int:
	var power: float = _get_var("standby_power")
	var lit := 0
	for segment: String in SEGMENTS:
		var on: bool = _get_var(segment)
		_set_var(segment + "_on", on)
		if on and segment != "buzzer":
			lit += 1
	power += lit * float(_get_var("lamp_power"))
	if _get_var("buzzer"):
		power += _get_var("buzzer_power")
	_meter.integrate(power, h, lit > 0)
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
