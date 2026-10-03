class_name KltSlotManager
extends RefCounted
## Placement counter of one KLT and the exchange request when it is full.

var next_slot := 0
var exchange_request := false
var _delay := IecTon.new()


func is_full(capacity: int) -> bool:
	return next_slot >= capacity


func place() -> int:
	next_slot += 1
	return next_slot - 1


## auto_exchange: request an exchange `delay` s after the KLT became full; the request is held until
## the measured count is zero (empty KLT in place), then the slot counter restarts.
func update(capacity: int, measured_count: int, auto_exchange: bool, delay: float, dt: float) -> void:
	_delay.pt = delay
	if _delay.update(is_full(capacity) and auto_exchange, dt):
		exchange_request = true
	if exchange_request and measured_count == 0:
		exchange_request = false
		next_slot = 0
