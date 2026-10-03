class_name IecTof
extends RefCounted
## IEC 61131-3 TOF (off-delay timer): Q stays true for PT seconds after IN becomes false.

var pt := 0.0
var q := false
var et := 0.0


func _init(preset_time := 0.0) -> void:
	pt = preset_time


func update(input: bool, dt: float) -> bool:
	if input:
		et = 0.0
		q = true
	elif q:
		et = minf(et + dt, pt)
		q = et < pt
	return q
