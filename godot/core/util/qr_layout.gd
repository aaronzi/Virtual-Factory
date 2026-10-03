class_name QrLayout
extends RefCounted
## Module placement of a QR code: function patterns, format/version information, codeword zig-zag, masks.

const ALIGNMENT := [[], [], [6, 18], [6, 22], [6, 26], [6, 30], [6, 34], [6, 22, 38], [6, 24, 42],
	[6, 26, 46], [6, 28, 50]]


static func draw_function_patterns(qr: QrCode) -> void:
	var n := qr.size
	for i in n:
		qr.set_function(6, i, i % 2 == 0)
		qr.set_function(i, 6, i % 2 == 0)
	_finder(qr, 3, 3)
	_finder(qr, n - 4, 3)
	_finder(qr, 3, n - 4)
	var pos: Array = ALIGNMENT[qr.version]
	var last := pos.size() - 1
	for i in pos.size():
		for j in pos.size():
			if not (i == 0 and j == 0 or i == 0 and j == last or i == last and j == 0):
				_alignment(qr, pos[i], pos[j])
	draw_format_bits(qr, 0)  # reserve
	_version_bits(qr)


## 15 format bits (level M = 00, mask), BCH(15,5), two copies plus the dark module.
static func draw_format_bits(qr: QrCode, mask: int) -> void:
	var data := mask  # level M: 0b00 << 3
	var rem := data
	for i in 10:
		rem = (rem << 1) ^ ((rem >> 9) * 0x537)
	var bits := ((data << 10) | rem) ^ 0x5412
	var n := qr.size
	for i in 6:
		qr.set_function(8, i, _bit(bits, i))
	qr.set_function(8, 7, _bit(bits, 6))
	qr.set_function(8, 8, _bit(bits, 7))
	qr.set_function(7, 8, _bit(bits, 8))
	for i in range(9, 15):
		qr.set_function(14 - i, 8, _bit(bits, i))
	for i in 8:
		qr.set_function(n - 1 - i, 8, _bit(bits, i))
	for i in range(8, 15):
		qr.set_function(8, n - 15 + i, _bit(bits, i))
	qr.set_function(8, n - 8, true)


static func draw_codewords(qr: QrCode, data: PackedByteArray) -> void:
	var n := qr.size
	var i := 0
	var right := n - 1
	while right >= 1:
		if right == 6:
			right = 5
		for vert in n:
			for j in 2:
				var x := right - j
				var upward := ((right + 1) & 2) == 0
				var y := n - 1 - vert if upward else vert
				if not qr.is_function(x, y) and i < data.size() * 8:
					qr.modules[y * n + x] = (data[i >> 3] >> (7 - (i & 7))) & 1
					i += 1
		right -= 2


## XORs the mask pattern onto all non-function modules (applying twice undoes it).
static func apply_mask(qr: QrCode, mask: int) -> void:
	var n := qr.size
	for y in n:
		for x in n:
			if not qr.is_function(x, y) and _masked(mask, x, y):
				qr.modules[y * n + x] ^= 1


static func _masked(mask: int, x: int, y: int) -> bool:
	match mask:
		0:
			return (x + y) % 2 == 0
		1:
			return y % 2 == 0
		2:
			return x % 3 == 0
		3:
			return (x + y) % 3 == 0
		4:
			return (x / 3 + y / 2) % 2 == 0
		5:
			return x * y % 2 + x * y % 3 == 0
		6:
			return (x * y % 2 + x * y % 3) % 2 == 0
	return ((x + y) % 2 + x * y % 3) % 2 == 0


static func _version_bits(qr: QrCode) -> void:
	if qr.version < 7:
		return
	var rem := qr.version
	for i in 12:
		rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
	var bits := (qr.version << 12) | rem
	for i in 18:
		var a := qr.size - 11 + i % 3
		var b := i / 3
		qr.set_function(a, b, _bit(bits, i))
		qr.set_function(b, a, _bit(bits, i))


static func _finder(qr: QrCode, cx: int, cy: int) -> void:
	for dy in range(-4, 5):
		for dx in range(-4, 5):
			var x := cx + dx
			var y := cy + dy
			if x >= 0 and x < qr.size and y >= 0 and y < qr.size:
				var dist := maxi(absi(dx), absi(dy))
				qr.set_function(x, y, dist != 2 and dist != 4)


static func _alignment(qr: QrCode, cx: int, cy: int) -> void:
	for dy in range(-2, 3):
		for dx in range(-2, 3):
			qr.set_function(cx + dx, cy + dy, maxi(absi(dx), absi(dy)) != 1)


static func _bit(value: int, i: int) -> bool:
	return (value >> i) & 1 == 1
