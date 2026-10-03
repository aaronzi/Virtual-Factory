class_name ColorMath
extends RefCounted
## sRGB -> CIELAB (D65) conversion and CIE76 colour difference.


static func srgb_to_lab(rgb: Vector3) -> Vector3:
	var lin := Vector3(_linearize(rgb.x), _linearize(rgb.y), _linearize(rgb.z))
	var x := (0.4124 * lin.x + 0.3576 * lin.y + 0.1805 * lin.z) / 0.95047
	var y := 0.2126 * lin.x + 0.7152 * lin.y + 0.0722 * lin.z
	var z := (0.0193 * lin.x + 0.1192 * lin.y + 0.9505 * lin.z) / 1.08883
	var fx := _f(x)
	var fy := _f(y)
	var fz := _f(z)
	return Vector3(116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


static func delta_e76(rgb_a: Vector3, rgb_b: Vector3) -> float:
	return srgb_to_lab(rgb_a).distance_to(srgb_to_lab(rgb_b))


static func hue_degrees(rgb: Vector3) -> float:
	return Color(rgb.x, rgb.y, rgb.z).h * 360.0


static func _linearize(c: float) -> float:
	c = clampf(c, 0.0, 1.0)
	return c / 12.92 if c <= 0.04045 else pow((c + 0.055) / 1.055, 2.4)


static func _f(t: float) -> float:
	return pow(t, 1.0 / 3.0) if t > 0.008856 else 7.787 * t + 16.0 / 116.0
