class_name IecTon
extends RefCounted
## IEC 61131-3 TON (on-delay timer): Q becomes true after IN has been true for PT seconds.

var pt := 0.0
var q := false
var et := 0.0


func _init(preset_time := 0.0) -> void:
	pt = preset_time


func update(input: bool, dt: float) -> bool:
	if input:
		et = minf(et + dt, pt)
		q = et >= pt
	else:
		et = 0.0
		q = false
	return q
