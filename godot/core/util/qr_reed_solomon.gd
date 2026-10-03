class_name QrReedSolomon
extends RefCounted
## Reed-Solomon error correction over GF(2^8) with the QR code polynomial x^8 + x^4 + x^3 + x^2 + 1.


## Generator polynomial of the given degree (coefficients highest first, leading 1 omitted).
static func divisor(degree: int) -> PackedByteArray:
	var result := PackedByteArray()
	result.resize(degree)
	result[degree - 1] = 1
	var root := 1
	for i in degree:
		for j in degree:
			result[j] = multiply(result[j], root)
			if j + 1 < degree:
				result[j] ^= result[j + 1]
		root = multiply(root, 0x02)
	return result


## Remainder of data * x^degree divided by the generator = the error correction codewords.
static func remainder(data: PackedByteArray, gen: PackedByteArray) -> PackedByteArray:
	var result := PackedByteArray()
	result.resize(gen.size())
	for b in data:
		var factor := b ^ result[0]
		result.remove_at(0)
		result.append(0)
		for i in gen.size():
			result[i] ^= multiply(gen[i], factor)
	return result


static func multiply(x: int, y: int) -> int:
	var z := 0
	for i in range(7, -1, -1):
		z = (z << 1) ^ ((z >> 7) * 0x11D)
		z ^= ((y >> i) & 1) * x
	return z & 0xFF
