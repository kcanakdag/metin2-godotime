extends RefCounted
## Imported particle appearance timing, separate from geometry and gameplay.

const Emission = preload("res://scripts/actors/particle_emission.gd")


static func initialize(
	particle: Dictionary, recipe: Dictionary, rng: RandomNumberGenerator
) -> void:
	var style: Dictionary = recipe.particle
	particle.rotation = rng.randf_range(
		style.RotationRandomStartingBegin, style.RotationRandomStartingEnd
	)
	particle.frame = 0
	particle.frame_type = int(style.TexAniType)
	particle.frame_remaining = float(style.TexAniDelay)
	var count: int = style.textures.size()
	if count > 1:
		if particle.frame_type == 4:
			particle.frame_type = 1 if rng.randi_range(0, 1) else 2
			particle.frame = 0 if particle.frame_type == 1 else count - 1
		if int(style.TexAniRandomStartFrameEnable) != 0:
			particle.frame = rng.randi_range(0, count - 1)
	particle.scale = Vector2(style.curves.ScaleX[0][1], style.curves.ScaleY[0][1])
	particle.color = packed_color(style.packed_color_keys, 0)


static func batch_rotation(style: Dictionary, rng: RandomNumberGenerator) -> float:
	var kind := int(style.RotationType)
	if kind in [0, 1]:
		return 0.0
	var speed := float(style.RotationSpeed)
	if kind == 4:
		return speed if rng.randi_range(0, 1) else -speed
	return -speed if kind == 3 else speed


static func advance(
	particle: Dictionary, recipe: Dictionary, delta: float, rng: RandomNumberGenerator
) -> void:
	var style: Dictionary = recipe.particle
	var age := (float(particle.age) + delta) / float(particle.lifetime)
	particle.scale = Vector2(
		Emission.sample(style.curves.ScaleX, age), Emission.sample(style.curves.ScaleY, age)
	)
	particle.color = packed_color(style.packed_color_keys, age)
	var speed := float(particle.rotation_speed)
	if int(style.RotationType) == 1:
		speed = Emission.sample(style.curves.Rotation, age)
	particle.rotation += speed * delta
	var count: int = style.textures.size()
	var delay := float(style.TexAniDelay)
	if count <= 1 or delay <= 0.000001 or int(particle.frame_type) == 0:
		return
	particle.frame_remaining -= delta
	if int(particle.frame_type) == 3 and particle.frame_remaining < 0:
		particle.frame = rng.randi_range(0, count - 1)
	while particle.frame_remaining < 0:
		particle.frame_remaining += delay
		if int(particle.frame_type) in [1, 2]:
			particle.frame = posmod(
				int(particle.frame) + (1 if particle.frame_type == 1 else -1), count
			)


static func packed_color(keys: Array, time: float) -> Color:
	if keys.is_empty():
		return Color(0, 0, 0, 0)
	var values: Array = keys[0].slice(1)
	for i: int in range(1, keys.size()):
		if time >= float(keys[i][0]):
			values = keys[i].slice(1)
			continue
		if time > float(keys[i - 1][0]):
			var weight := (
				(time - float(keys[i - 1][0])) / (float(keys[i][0]) - float(keys[i - 1][0]))
			)
			# Original DWORDCOLOR uses 8-bit fixed-point weights, truncating each term.
			for channel: int in range(4):
				values[channel] = (
					((int(keys[i - 1][channel + 1]) * int((1 - weight) * 256)) >> 8)
					+ ((int(keys[i][channel + 1]) * int(weight * 256)) >> 8)
				)
		break
	return Color(
		float(values[0]) / 255,
		float(values[1]) / 255,
		float(values[2]) / 255,
		float(values[3]) / 255
	)
