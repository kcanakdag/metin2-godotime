shader_type spatial;
render_mode diffuse_burley, specular_disabled;

uniform sampler2DArray terrain_textures : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D tile_ids : filter_nearest, repeat_disable;
uniform sampler2D attributes : filter_nearest, repeat_disable;
uniform vec4 texture_uv[32];
uniform bool show_attributes = false;
varying vec2 world_xz;

void vertex() {
	world_xz = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xz;
}

vec3 ground_at(vec2 pixel) {
	int id = clamp(int(round(texture(tile_ids, (pixel + 0.5) / 258.0).r * 255.0)), 1, 32) - 1;
	vec4 params = texture_uv[id];
	vec2 uv = world_xz / 32.0 * params.xy + vec2(params.z, -params.w);
	return texture(terrain_textures, vec3(uv, float(id))).rgb;
}

void fragment() {
	// Bilinear categorical layer blending; legacy splat dilation is not reproduced.
	vec2 pixel = UV * 256.0 + 0.5;
	vec2 base = floor(pixel);
	vec2 weight = fract(pixel);
	vec3 a = mix(ground_at(base), ground_at(base + vec2(1.0, 0.0)), weight.x);
	vec3 b = mix(ground_at(base + vec2(0.0, 1.0)), ground_at(base + vec2(1.0)), weight.x);
	ALBEDO = mix(a, b, weight.y);
	if (show_attributes) {
		int flags = int(round(texture(attributes, UV).r * 255.0));
		if (flags != 0) {
			ALBEDO = mix(ALBEDO, (flags & 1) != 0 ? vec3(0.9, 0.15, 0.12) : vec3(0.15, 0.4, 0.9), 0.65);
		}
	}
	ROUGHNESS = 1.0;
}
