class_name IecCtu
extends RefCounted
## IEC 61131-3 CTU (up counter): CV counts rising edges of CU; Q = CV >= PV; R resets.

var pv := 0
var cv := 0
var q := false
var _edge := IecRTrig.new()


func _init(preset_value := 0) -> void:
	pv = preset_value


func update(cu: bool, reset := false) -> bool:
	var rising := _edge.update(cu)
	if reset:
		cv = 0
	elif rising:
		cv += 1
	q = cv >= pv
	return q
