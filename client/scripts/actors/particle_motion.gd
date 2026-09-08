extends RefCounted
## Original particle kinematics in Godot metres, independent of rendering/damage.
## Input recipes must have passed the offline particle importer.

const Emission = preload("res://scripts/actors/particle_emission.gd")


static func source_vector(value: Array) -> Vector3:
	return Vector3(float(value[0]), float(value[2]), -float(value[1])) * 0.01


static func position_at(keys: Array, time: float, controls: Array = []) -> Vector3:
	if not controls.is_empty():
		if time <= float(keys[0][0]):
			return source_vector(keys[0].slice(1))
		for index: int in range(1, keys.size()):
			if time > float(keys[index][0]):
				continue
			var start := source_vector(keys[index - 1].slice(1))
			var end := source_vector(keys[index].slice(1))
			var weight := (
				(time - float(keys[index - 1][0]))
				/ (float(keys[index][0]) - float(keys[index - 1][0]))
			)
			if controls[index - 1].is_empty():
				return start.lerp(end, weight)
			var control := start + source_vector(controls[index - 1])
			return (
				start * pow(1 - weight, 2)
				+ control * (2 * (1 - weight) * weight)
				+ end * weight * weight
			)
		return source_vector(keys.back().slice(1))
	var result: Array = []
	for axis: int in range(1, 4):
		var channel: Array = []
		for key: Array in keys:
			channel.append([key[0], key[axis]])
		result.append(Emission.sample(channel, time))
	return source_vector(result)


static func spawn(
	recipe: Dictionary,
	birth: Dictionary,
	transform: Transform3D,
	rng: RandomNumberGenerator,
	delta: float
) -> Dictionary:
	var emitter: Dictionary = recipe.emitter
	var curves: Dictionary = emitter.curves
	var time := float(birth.emitter_time)
	var attached := int(recipe.particle.AttachEnable) != 0
	var center := position_at(recipe.position_keys_cm, time, recipe.get("position_controls_cm", []))
	var offset := _offset(emitter, time, rng)
	var position := center + source_vector([offset.x, offset.y, offset.z])
	if not attached:
		position = transform * position
		center = transform * center
	var velocity := Vector3.ZERO
	var advanced := int(emitter.EmitterAdvancedType)
	if advanced == 2:
		velocity = -(position - center).normalized()
	elif advanced == 1:
		if int(emitter.EmitterShape) == 0:
			velocity = source_vector(
				[
					rng.randf_range(-100, 100),
					rng.randf_range(-100, 100),
					rng.randf_range(-100, 100),
				]
			)
		else:
			velocity = (position - center).normalized()
	var direction := source_vector(
		[
			Emission.sample(curves.EmittingDirectionX, time),
			Emission.sample(curves.EmittingDirectionY, time),
			Emission.sample(curves.EmittingDirectionZ, time),
		]
	)
	if not attached:
		direction = transform.basis * direction
	velocity += direction
	var dispersion: Array = []
	for value: Variant in emitter.EmittingDirection:
		var spread := float(value)
		dispersion.append(rng.randf_range(-spread / 2, spread / 2) * 1000 if spread > 0 else 0)
	# The original adds dispersion on the simulation axes after transforming direction.
	velocity += source_vector(dispersion)
	velocity *= Emission.sample(curves.EmittingVelocity, time)
	return {
		"id": birth.id,
		"lifetime": birth.lifetime,
		"age": 0.0,
		"position": position,
		"previous_position": position - velocity * delta,
		"center": center,
		"velocity": velocity,
		"attached": attached,
		"half_size":
		Vector2(Emission.sample(curves.SizeX, time), Emission.sample(curves.SizeY, time)) * 0.01,
	}


static func advance(particle: Dictionary, recipe: Dictionary, delta: float) -> void:
	particle.age = float(particle.age) + delta
	var age := float(particle.age) / float(particle.lifetime)
	var curves: Dictionary = recipe.particle.curves
	var velocity: Vector3 = particle.velocity
	# Decorator insertion order applies gravity before air resistance, then movement.
	velocity.y -= Emission.sample(curves.Gravity, age) * 0.01 * delta
	velocity *= 1.0 - Emission.sample(curves.AirResistance, age)
	particle.velocity = velocity
	particle.previous_position = particle.position
	particle.position += velocity * delta


static func orbit(particle: Dictionary, angle_degrees: float, emitter_basis: Basis) -> void:
	if angle_degrees == 0:
		return
	# Original angular velocity is a clockwise angle per update, not per second.
	var axis := Vector3.UP if particle.attached else emitter_basis.y.normalized()
	var relative: Vector3 = particle.position - particle.center
	particle.position = particle.center + relative.rotated(axis, -deg_to_rad(angle_degrees))


static func world_position(particle: Dictionary, transform: Transform3D) -> Vector3:
	return transform * particle.position if particle.attached else particle.position


static func _offset(emitter: Dictionary, time: float, rng: RandomNumberGenerator) -> Vector3:
	var shape := int(emitter.EmitterShape)
	var size := Emission.sample(emitter.curves.EmittingSize, time)
	if shape == 0:
		return Vector3.ZERO
	if shape == 2:
		var extent: Array = emitter.EmittingSize
		return Vector3(
			rng.randf_range(-float(extent[0]) / 2, float(extent[0]) / 2) + size,
			rng.randf_range(-float(extent[1]) / 2, float(extent[1]) / 2) + size,
			rng.randf_range(-float(extent[2]) / 2, float(extent[2]) / 2) + size
		)
	var offset := Vector3(rng.randf_range(-500, 500), rng.randf_range(-500, 500), 0)
	if shape == 3:
		offset.z = rng.randf_range(-500, 500)
	var radius := float(emitter.EmittingRadius)
	if int(emitter.EmitterEmitFromEdgeFlag) == 0:
		radius = rng.randf_range(0, radius)
	return offset.normalized() * (radius + size)
