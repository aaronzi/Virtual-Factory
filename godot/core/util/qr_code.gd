class_name QrCode
extends RefCounted
## QR code encoder (ISO/IEC 18004): byte mode, error correction level M, versions 1-10 (up to 213 bytes),
## automatic mask selection by the standard penalty rules. Used for the GS1 Digital Link on the part labels.
## `encode()` returns the module matrix (row-major, 1 = dark) without quiet zone; `size` modules per side.

const MAX_VERSION := 10
const ECC_PER_BLOCK := [0, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26]  # level M, per version
const BLOCKS := [0, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5]
const PENALTY_N1 := 3
const PENALTY_N2 := 3
const PENALTY_N3 := 40
const PENALTY_N4 := 10

var version := 0
var size := 0
var mask := -1
var modules := PackedByteArray()
var _function := PackedByteArray()


## Encodes UTF-8 `text`; `forced_mask` 0-7 skips the mask selection (tests). Returns null if too long.
static func encode(text: String, forced_mask := -1) -> QrCode:
	var data := text.to_utf8_buffer()
	var qr := QrCode.new()
	qr.version = _min_version(data.size())
	if qr.version == 0:
		return null
	qr._build(_add_ecc(_data_codewords(data, qr.version), qr.version), forced_mask)
	return qr


func is_dark(x: int, y: int) -> bool:
	return modules[y * size + x] == 1


## Greyscale image (L8, 255 = light) with `quiet` modules of quiet zone, one pixel per module.
func to_image(quiet := 4) -> Image:
	var side := size + 2 * quiet
	var pixels := PackedByteArray()
	pixels.resize(side * side)
	pixels.fill(255)
	for y in size:
		for x in size:
			if modules[y * size + x] == 1:
				pixels[(y + quiet) * side + x + quiet] = 0
	return Image.create_from_data(side, side, false, Image.FORMAT_L8, pixels)


static func capacity_bytes(ver: int) -> int:
	return (_data_capacity(ver) * 8 - 4 - _count_bits(ver)) / 8


static func _min_version(byte_count: int) -> int:
	for ver in range(1, MAX_VERSION + 1):
		if byte_count <= capacity_bytes(ver):
			return ver
	return 0


static func _count_bits(ver: int) -> int:
	return 8 if ver < 10 else 16


static func _raw_codewords(ver: int) -> int:
	var bits := (16 * ver + 128) * ver + 64
	if ver >= 2:
		var align := ver / 7 + 2
		bits -= (25 * align - 10) * align - 55
		if ver >= 7:
			bits -= 36
	return bits / 8


static func _data_capacity(ver: int) -> int:
	return _raw_codewords(ver) - ECC_PER_BLOCK[ver] * BLOCKS[ver]


static func _data_codewords(data: PackedByteArray, ver: int) -> PackedByteArray:
	var bits: Array[int] = []
	_append_bits(bits, 0b0100, 4)
	_append_bits(bits, data.size(), _count_bits(ver))
	for b in data:
		_append_bits(bits, b, 8)
	var capacity := _data_capacity(ver) * 8
	_append_bits(bits, 0, mini(4, capacity - bits.size()))
	_append_bits(bits, 0, (8 - bits.size() % 8) % 8)
	var out := PackedByteArray()
	for i in range(0, bits.size(), 8):
		var byte := 0
		for j in 8:
			byte = (byte << 1) | bits[i + j]
		out.append(byte)
	var pad := 0xEC
	while out.size() < _data_capacity(ver):
		out.append(pad)
		pad = 0x11 if pad == 0xEC else 0xEC
	return out


static func _append_bits(bits: Array[int], value: int, count: int) -> void:
	for i in range(count - 1, -1, -1):
		bits.append((value >> i) & 1)


## Splits into blocks, appends the Reed-Solomon codewords and interleaves.
static func _add_ecc(data: PackedByteArray, ver: int) -> PackedByteArray:
	var blocks_n: int = BLOCKS[ver]
	var ecc_len: int = ECC_PER_BLOCK[ver]
	var raw := _raw_codewords(ver)
	var short_blocks := blocks_n - raw % blocks_n
	var short_len := raw / blocks_n
	var divisor := QrReedSolomon.divisor(ecc_len)
	var blocks := []
	var k := 0
	for i in blocks_n:
		var length := short_len - ecc_len + (0 if i < short_blocks else 1)
		var block := data.slice(k, k + length)
		k += length
		var ecc := QrReedSolomon.remainder(block, divisor)
		if i < short_blocks:
			block.append(0)
		block.append_array(ecc)
		blocks.append(block)
	var out := PackedByteArray()
	for i in (blocks[0] as PackedByteArray).size():
		for j in blocks_n:
			if i != short_len - ecc_len or j >= short_blocks:
				out.append(blocks[j][i])
	return out


func _build(codewords: PackedByteArray, forced_mask: int) -> void:
	size = version * 4 + 17
	modules.resize(size * size)
	_function.resize(size * size)
	QrLayout.draw_function_patterns(self)
	QrLayout.draw_codewords(self, codewords)
	mask = forced_mask
	if mask < 0:
		var best := 1 << 30
		for m in 8:
			QrLayout.apply_mask(self, m)
			QrLayout.draw_format_bits(self, m)
			var penalty := QrPenalty.score(modules, size)
			if penalty < best:
				best = penalty
				mask = m
			QrLayout.apply_mask(self, m)  # XOR again = undo
	QrLayout.apply_mask(self, mask)
	QrLayout.draw_format_bits(self, mask)


func set_function(x: int, y: int, dark: bool) -> void:
	modules[y * size + x] = 1 if dark else 0
	_function[y * size + x] = 1


func is_function(x: int, y: int) -> bool:
	return _function[y * size + x] == 1
