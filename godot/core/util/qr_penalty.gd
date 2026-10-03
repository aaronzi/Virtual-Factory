class_name QrPenalty
extends RefCounted
## Mask penalty score of ISO/IEC 18004 (rules N1-N4; finder-like patterns counted with light borders).


static func score(m: PackedByteArray, n: int) -> int:
	var result := 0
	for y in n:
		result += _line(m, n, y * n, 1)
	for x in n:
		result += _line(m, n, x, n)
	for y in n - 1:
		for x in n - 1:
			var c := m[y * n + x]
			if c == m[y * n + x + 1] and c == m[(y + 1) * n + x] and c == m[(y + 1) * n + x + 1]:
				result += QrCode.PENALTY_N2
	var dark := 0
	for v in m:
		dark += v
	var total := n * n
	var k := ceili(absi(dark * 20 - total * 10) / float(total)) - 1
	return result + k * QrCode.PENALTY_N4


## Runs of equal colour (N1) and finder-like 1:1:3:1:1 patterns (N3) along one row or column.
static func _line(m: PackedByteArray, n: int, start: int, step: int) -> int:
	var result := 0
	var color := 0
	var run := 0
	var history := PackedInt32Array([0, 0, 0, 0, 0, 0, 0])
	for i in n:
		var v := m[start + i * step]
		if v == color:
			run += 1
			if run == 5:
				result += QrCode.PENALTY_N1
			elif run > 5:
				result += 1
		else:
			_push(history, run, n)
			if color == 0:
				result += _patterns(history) * QrCode.PENALTY_N3
			color = v
			run = 1
	if color == 1:
		_push(history, run, n)
		run = 0
	_push(history, run + n, n)
	return result + _patterns(history) * QrCode.PENALTY_N3


static func _push(history: PackedInt32Array, run: int, n: int) -> void:
	if history[0] == 0:
		run += n  # light border before the first run
	for i in range(6, 0, -1):
		history[i] = history[i - 1]
	history[0] = run


static func _patterns(h: PackedInt32Array) -> int:
	var w := h[1]
	var core := w > 0 and h[2] == w and h[3] == w * 3 and h[4] == w and h[5] == w
	var left := 1 if core and h[0] >= w * 4 and h[6] >= w else 0
	return left + (1 if core and h[6] >= w * 4 and h[0] >= w else 0)
