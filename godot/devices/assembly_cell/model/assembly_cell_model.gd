extends Fmi3CoSimulation
## Black-box assembly cell: assembles one cylinder per takt and releases it onto the conveyor when
## the infeed is free. Internal process is not modelled; only interface-visible results are produced.

enum CellState { IDLE, ASSEMBLING, BLOCKED }
enum CapVariant { RED, MISSING, WRONG }

const ComponentLots := preload("res://devices/assembly_cell/model/component_lots.gd")

var _rng := RandomNumberGenerator.new()
var _meter := EnergyMeter.new()
var _timer := 0.0


func _on_initialize() -> void:
	_rng.seed = _get_var("seed")


func _on_step(_t: float, h: float) -> int:
	var state: int = _get_var("state")
	var takt: float = _get_var("takt_time")
	if not _get_var("enable"):
		state = CellState.IDLE
	elif state == CellState.BLOCKED:
		if _get_var("infeed_free"):
			_release()
			state = CellState.ASSEMBLING
	else:
		state = CellState.ASSEMBLING
		_timer += h
		if _timer >= takt - 1e-9:
			if _get_var("infeed_free"):
				_release()
			else:
				state = CellState.BLOCKED
	_set_var("state", state)
	_set_var("cycle_progress", clampf(_timer / takt, 0.0, 1.0))
	_update_power(state, takt, h)
	return Fmi3.Status.OK


func _release() -> void:
	_timer = 0.0
	var count: int = _get_var("release_count") + 1
	var serial_no: int = _get_var("serial_start") + count - 1
	var roll := _rng.randf()
	var missing: float = _get_var("defect_rate_missing_cap")
	var variant := CapVariant.RED
	if roll < missing:
		variant = CapVariant.MISSING
	elif roll < missing + _get_var("defect_rate_wrong_cap"):
		variant = CapVariant.WRONG
	_set_var("release_count", count)
	_set_var("last_serial", "%s-%04d-%06d" % [_get_var("type_code"), _get_var("production_year"), serial_no])
	_set_var("last_cap_variant", variant)
	_set_var("last_leak_rate", absf(_rng.randfn(0.4, 0.15)))
	_set_var("last_stroke_time", _rng.randfn(0.32, 0.01))
	_set_var("last_lots", ComponentLots.lots_for(serial_no))


func _update_power(state: int, takt: float, h: float) -> void:
	var power: float = _get_var("idle_power")
	if state == CellState.ASSEMBLING:
		var air_per_s: float = _get_var("air_per_cycle") / takt
		power += _get_var("working_power") + air_per_s * _get_var("air_specific_energy") * 3600.0
		_set_var("air_consumption", _get_var("air_consumption") + air_per_s * h)
	_meter.integrate(power, h, state == CellState.ASSEMBLING)
	_set_var("power", power)
	_set_var("energy", _meter.energy_kwh)
	_set_var("operating_hours", _meter.operating_hours)


func _on_reset() -> void:
	_meter = EnergyMeter.new()
	_timer = 0.0


func _save_internal_state() -> Dictionary:
	return {"rng": _rng.state, "meter": _meter.save(), "timer": _timer}


func _load_internal_state(s: Dictionary) -> void:
	_rng.state = s.get("rng", _rng.state)
	_meter.load(s.get("meter", {}))
	_timer = s.get("timer", 0.0)
