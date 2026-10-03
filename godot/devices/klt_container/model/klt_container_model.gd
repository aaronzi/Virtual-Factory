extends Fmi3CoSimulation
## KLT container: fill level from the presence sensor, full flag, exchange events.

var _last_exchange := false


func _on_step(_t: float, _h: float) -> int:
	var count: int = _get_var("item_count_measured")
	_set_var("fill_count", count)
	_set_var("full", count >= _get_var("capacity"))
	var exchange: bool = _get_var("exchange")
	if exchange and not _last_exchange:
		_set_var("exchange_count", _get_var("exchange_count") + 1)
	_last_exchange = exchange
	return Fmi3.Status.OK


func _on_reset() -> void:
	_last_exchange = false


func _save_internal_state() -> Dictionary:
	return {"last_exchange": _last_exchange}


func _load_internal_state(s: Dictionary) -> void:
	_last_exchange = s.get("last_exchange", false)
