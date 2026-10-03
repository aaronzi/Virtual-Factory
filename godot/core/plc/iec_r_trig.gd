class_name IecRTrig
extends RefCounted
## IEC 61131-3 R_TRIG: Q is true for one scan on a rising edge of CLK.

var q := false
var _last := false


func update(clk: bool) -> bool:
	q = clk and not _last
	_last = clk
	return q
