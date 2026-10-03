class_name IecFTrig
extends RefCounted
## IEC 61131-3 F_TRIG: Q is true for one scan on a falling edge of CLK.

var q := false
var _last := false


func update(clk: bool) -> bool:
	q = _last and not clk
	_last = clk
	return q
