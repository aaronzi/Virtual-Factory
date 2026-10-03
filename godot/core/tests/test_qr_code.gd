extends GutTest
## QR encoder against reference vectors of Project Nayuki's qrcodegen (byte mode, level M, no ECC boost):
## SHA-256 of the module rows as "0"/"1" text, version and automatically chosen mask.

const ITEM := "https://virtual-factory.example/01/04099999032808/21/PC3280-2026-000134"
const HELLO_ROWS := ["111111101101001111111", "100000100110101000001", "101110100111101011101",
	"101110101001001011101", "101110101000101011101", "100000101011001000001", "111111101010101111111",
	"000000001111100000000", "100010111111011111001", "000111001011100101111", "101100101011001110010",
	"111001000100011010000", "001011100100111000110", "000000001110111001011", "111111101100110001010",
	"100000100001100100010", "101110101001001110101", "101110100001100001011", "101110100111001111000",
	"100000100100011000000", "111111101000111110101"]


func _rows(qr: QrCode) -> String:
	var text := ""
	for y in qr.size:
		for x in qr.size:
			text += "1" if qr.is_dark(x, y) else "0"
	return text


func test_short_text_matches_the_reference_matrix() -> void:
	var qr := QrCode.encode("HELLO")
	assert_eq([qr.version, qr.mask, qr.size], [1, 4, 21])
	assert_eq(_rows(qr), "".join(HELLO_ROWS))


func test_item_digital_link_is_version_5() -> void:
	var qr := QrCode.encode(ITEM)
	assert_eq([qr.version, qr.mask, qr.size], [5, 2, 37])
	assert_eq(_rows(qr).sha256_text(), "535bb9d9110abce7397824629c3cb449494aa420f246e9e096f477a0dec82cc3")


func test_product_digital_link_and_multi_block_version() -> void:
	var product := QrCode.encode("https://virtual-factory.example/01/04099999032808")
	assert_eq([product.version, product.mask], [4, 5])
	assert_eq(_rows(product).sha256_text(), "bd5b3cec1b184dce90720005d496c035811171c084637120863f6e3a1da54c62")
	var long := QrCode.encode("x".repeat(150))  # version 8: two block lengths, version information
	assert_eq([long.version, long.mask], [8, 2])
	assert_eq(_rows(long).sha256_text(), "1336208e161628515a3ac797a4b047f50e23d84e84231684e6f31c281d616932")


func test_capacity_limit_and_image_with_quiet_zone() -> void:
	assert_eq(QrCode.capacity_bytes(5), 84)
	assert_null(QrCode.encode("x".repeat(QrCode.capacity_bytes(QrCode.MAX_VERSION) + 1)))
	var qr := QrCode.encode("HELLO")
	var image := qr.to_image(4)
	assert_eq(image.get_size(), Vector2i(29, 29))
	assert_eq(image.get_pixel(0, 0).r, 1.0)  # quiet zone light
	assert_eq(image.get_pixel(4, 4).r, 0.0)  # finder corner dark


func test_reed_solomon_codewords() -> void:
	# ISO/IEC 18004 Annex I example (1-M "01234567"): data codewords -> 10 EC codewords
	var data := PackedByteArray([16, 32, 12, 86, 97, 128, 236, 17, 236, 17, 236, 17, 236, 17, 236, 17])
	var ecc := QrReedSolomon.remainder(data, QrReedSolomon.divisor(10))
	assert_eq(Array(ecc), [165, 36, 212, 193, 237, 54, 199, 135, 44, 85])
