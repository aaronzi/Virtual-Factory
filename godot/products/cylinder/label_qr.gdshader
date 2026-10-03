// Type plate of the cylinder with the part's QR code (ADR-0023): the printed label texture (shared) plus a
// per-part QR texture (1 texel per module incl. quiet zone, nearest filtering) in the label's QR area.
// Replaces the imported label material on the same surface - no extra draw call per part.
shader_type spatial;
render_mode cull_back;

uniform sampler2D label_texture : source_color, filter_linear_mipmap;
uniform sampler2D qr_texture : filter_nearest_mipmap, repeat_disable;
uniform vec4 qr_rect = vec4(0.6235, 0.25, 0.353, 0.706); // UV origin and size of the QR area (square on the label)
uniform float roughness = 0.45;

void fragment() {
	vec3 color = texture(label_texture, UV).rgb;
	vec2 q = (UV - qr_rect.xy) / qr_rect.zw;
	if (q.x >= 0.0 && q.x <= 1.0 && q.y >= 0.0 && q.y <= 1.0) {
		color = vec3(mix(0.004, 0.86, texture(qr_texture, q).r));
	}
	ALBEDO = color;
	ROUGHNESS = roughness;
}
