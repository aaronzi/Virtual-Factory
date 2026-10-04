shader_type spatial;
render_mode cull_back;

// glTF COLOR_0 is linear. Compatibility shades in sRGB; unlike Forward+/Mobile,
// StandardMaterial3D does not provide a vertex colour space conversion there.
uniform float metallic = 0.0;
uniform float roughness = 0.56;
global uniform float vf_surface_detail;
varying vec3 local_position;

void vertex() {
	local_position = VERTEX;
	if (OUTPUT_IS_SRGB) {
		vec3 c = max(COLOR.rgb, vec3(0.0));
		COLOR.rgb = mix(12.92 * c, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055,
			step(vec3(0.0031308), c));
	}
}

void fragment() {
	ALBEDO = COLOR.rgb;
	METALLIC = metallic;
	ROUGHNESS = roughness;
	// Broad, low-contrast machining / coating variation. Derivative filtering avoids distant shimmer.
	float phase = dot(local_position, vec3(170.0, 37.0, 89.0));
	float grain = sin(phase) * exp(-fwidth(phase) * 2.0) * vf_surface_detail;
	ROUGHNESS = clamp(roughness + grain * 0.055, 0.1, 1.0);
	ALBEDO *= 1.0 + grain * 0.025;
}
