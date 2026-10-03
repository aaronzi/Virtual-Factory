class_name IecTp
extends RefCounted
## IEC 61131-3 TP (pulse timer): a rising edge on IN produces a pulse of PT seconds.

var pt := 0.0
var q := false
var et := 0.0
var _last_in := false


func _init(preset_time := 0.0) -> void:
	pt = preset_time


func update(input: bool, dt: float) -> bool:
	if input and not _last_in and not q:
		q = true
		et = 0.0
	if q:
		et = minf(et + dt, pt)
		q = et < pt
	elif not input:
		et = 0.0
	_last_in = input
	return q
