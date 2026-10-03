shader_type spatial;
// Scrolling conveyor belt surface; `offset` is the belt travel in metres.

uniform vec3 base_color : source_color = vec3(0.10, 0.20, 0.16);
uniform vec3 stripe_color : source_color = vec3(0.12, 0.24, 0.19);
uniform float length_m = 3.0;
uniform float offset = 0.0;
uniform float stripes_per_m = 8.0;

void fragment() {
	float s = step(0.5, fract((UV.x * length_m - offset) * stripes_per_m));
	ALBEDO = mix(base_color, stripe_color, s);
	ROUGHNESS = 0.85;
}
