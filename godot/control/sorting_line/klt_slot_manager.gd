class_name KltSlotManager
extends RefCounted
## Placement counter of one KLT and its exchange request (automatic when full, or manual).
## An exchange is only requested while no robot job to this KLT is in progress (`placing`), so the
## last part always lands in the container it was reported for.

var next_slot := 0
var exchange_request := false
var _manual_pending := false
var _delay := IecTon.new()


func is_full(capacity: int) -> bool:
	return next_slot >= capacity


func place() -> int:
	next_slot += 1
	return next_slot - 1


## Manual exchange (operator/MES); honoured once no job is placing into this KLT and it holds parts.
func request_exchange() -> void:
	_manual_pending = true


## auto_exchange: request an exchange `delay` s after the KLT became full (and the last job finished);
## the request is held until the measured count is zero (empty KLT in place), then the slots restart.
func update(capacity: int, measured_count: int, auto_exchange: bool, delay: float, dt: float,
		placing := false) -> void:
	_delay.pt = delay
	if _delay.update(is_full(capacity) and auto_exchange and not placing, dt):
		exchange_request = true
	if _manual_pending and not placing:
		_manual_pending = false
		exchange_request = exchange_request or measured_count > 0
	if exchange_request and measured_count == 0:
		exchange_request = false
		next_slot = 0
