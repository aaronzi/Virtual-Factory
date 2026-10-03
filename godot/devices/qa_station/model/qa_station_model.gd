extends Fmi3CoSimulation
## Colour inspection: on a rising trigger edge, integrates for `integration_time`, then compares the
## (noisy) measured colour with the taught colour. The result stays valid while `trigger` is true.

var _rng := RandomNumberGenerator.new()
var _meter := EnergyMeter.new()
var _measuring := false
var _elapsed := 0.0
var _last_trigger := false


func _on_initialize() -> void:
	_rng.seed = _get_var("seed")


func _on_step(_t: float, h: float) -> int:
	var trigger: bool = _get_var("trigger")
	if trigger and not _last_trigger:
		_measuring = true
		_elapsed = 0.0
		_set_var("result_valid", false)
	if not trigger:
		_measuring = false
		_set_var("result_valid", false)
	if _measuring:
		_elapsed += h
		if _elapsed >= _get_var("integration_time") - 1e-9:
			_measure()
			_measuring = false
	_last_trigger = trigger
	_set_var("light_on", trigger)
	var power: float = _get_var("sensor_power") + (_get_var("light_power") if trigger else 0.0)
	_meter.integrate(power, h)
	_set_var("power", power)
	_set_var("energy", _meter.energy_kwh)
	_set_var("operating_hours", _meter.operating_hours)
	return Fmi3.Status.OK


func _measure() -> void:
	var sigma: float = _get_var("noise_sigma")
	var rgb := Vector3(
		clampf(_get_var("measured_r") + _rng.randfn(0.0, sigma), 0.0, 1.0),
		clampf(_get_var("measured_g") + _rng.randfn(0.0, sigma), 0.0, 1.0),
		clampf(_get_var("measured_b") + _rng.randfn(0.0, sigma), 0.0, 1.0))
	var taught := Vector3(_get_var("taught_r"), _get_var("taught_g"), _get_var("taught_b"))
	var de := ColorMath.delta_e76(rgb, taught)
	_set_var("r", rgb.x)
	_set_var("g", rgb.y)
	_set_var("b", rgb.z)
	_set_var("hue", ColorMath.hue_degrees(rgb))
	_set_var("delta_e", de)
	_set_var("result_ok", _get_var("object_present") and de <= _get_var("tolerance_delta_e"))
	_set_var("result_valid", true)
	_set_var("measure_count", _get_var("measure_count") + 1)


func _on_reset() -> void:
	_meter = EnergyMeter.new()
	_measuring = false
	_last_trigger = false


func _save_internal_state() -> Dictionary:
	return {"rng": _rng.state, "meter": _meter.save(), "measuring": _measuring,
		"elapsed": _elapsed, "last_trigger": _last_trigger}


func _load_internal_state(s: Dictionary) -> void:
	_rng.state = s.get("rng", _rng.state)
	_meter.load(s.get("meter", {}))
	_measuring = s.get("measuring", false)
	_elapsed = s.get("elapsed", 0.0)
	_last_trigger = s.get("last_trigger", false)
