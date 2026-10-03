extends Fmi3CoSimulation
## Light barrier behaviour: response-time filtered switching output with dark-on/light-on logic.
## Fault injection: `misalignment` (0..1) makes the received light marginal - the beam drops out
## randomly (Poisson rate misalignment * dropout_rate, seeded RNG, so runs stay deterministic); at 1
## the beam is permanently lost (signal stuck). The RNG is only used while misaligned.

const STABILITY_LIMIT := 0.2

var _state := false
var _pending_time := 0.0
var _dropout_left := 0.0
var _rng := RandomNumberGenerator.new()
var _meter := EnergyMeter.new()


func _on_initialize() -> void:
	_rng.seed = _get_var("seed")


func _on_step(_t: float, h: float) -> int:
	var blocked: bool = _beam_lost(h) or _get_var("beam_blocked")
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
	_set_var("stability_ok", _get_var("misalignment") < STABILITY_LIMIT)
	var power: float = _get_var("rated_power")
	_meter.integrate(power, h)
	_set_var("power", power)
	_set_var("energy", _meter.energy_kwh)
	_set_var("operating_hours", _meter.operating_hours)
	return Fmi3.Status.OK


## True while the receiver gets no usable light because of misalignment.
func _beam_lost(h: float) -> bool:
	var m := clampf(_get_var("misalignment"), 0.0, 1.0)
	if m >= 1.0:
		return true
	if m <= 0.0:
		_dropout_left = 0.0
		return false
	if _dropout_left > 0.0:
		_dropout_left -= h
		return true
	if _rng.randf() < 1.0 - exp(-m * float(_get_var("dropout_rate")) * h):
		_dropout_left = _get_var("dropout_duration") - h
		return true
	return false


func _on_reset() -> void:
	_state = false
	_pending_time = 0.0
	_dropout_left = 0.0
	_meter = EnergyMeter.new()


func _save_internal_state() -> Dictionary:
	return {"state": _state, "pending": _pending_time, "meter": _meter.save(), "rng": _rng.state,
		"dropout": _dropout_left}


func _load_internal_state(s: Dictionary) -> void:
	_state = s.get("state", false)
	_pending_time = s.get("pending", 0.0)
	_meter.load(s.get("meter", {}))
	_rng.state = s.get("rng", _rng.state)
	_dropout_left = s.get("dropout", 0.0)
