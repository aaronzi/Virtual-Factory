class_name StuckSignal
extends RefCounted
## Detects a sensor that stays active while it should change (e.g. a light barrier that is blocked
## while the belt runs for longer than any part needs to pass). Latched until the signal drops.

var stuck := false
var _ton := IecTon.new()


func _init(timeout: float) -> void:
	_ton.pt = timeout


## `watching`: the plausibility window (e.g. belt running); returns the latched state.
func update(signal_on: bool, watching: bool, dt: float) -> bool:
	if _ton.update(signal_on and watching, dt):
		stuck = true
	if not signal_on:
		stuck = false
	return stuck
