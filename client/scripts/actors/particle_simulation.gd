extends RefCounted
## One imported particle system; presentation state never grants gameplay damage.

const Emission = preload("res://scripts/actors/particle_emission.gd")
const Motion = preload("res://scripts/actors/particle_motion.gd")
const Style = preload("res://scripts/actors/particle_style.gd")

var particles: Dictionary = {}
var _recipe: Dictionary = {}
var _emission: RefCounted
var _rng := RandomNumberGenerator.new()


func configure(recipe: Dictionary, random_seed: int) -> bool:
	# Only trusted, importer-validated recipes belong here. Angular orbit is a
	# separate original mechanic, absent from the currently selected 22 systems.
	for key: Array in recipe.emitter.curves.EmittingAngularVelocity:
		if float(key[1]) != 0.0:
			return false
	var candidate := Emission.new()
	if not candidate.configure(recipe):
		return false
	_recipe = recipe.duplicate(true)
	_emission = candidate
	_rng.seed = random_seed
	particles.clear()
	return true


func advance(delta: float, transform: Transform3D, emitting: bool = true) -> Dictionary:
	if (
		_emission == null
		or not transform.is_finite()
		or not transform.basis.is_equal_approx(transform.basis.orthonormalized())
		or not is_equal_approx(transform.basis.determinant(), 1.0)
	):
		return {"error": "Particle simulation requires a configured recipe and rigid transform"}
	var result: Dictionary = _emission.advance(delta, emitting)
	if result.has("error"):
		return result
	for id: int in result.deaths:
		particles.erase(id)
	for particle: Dictionary in particles.values():
		Style.advance(particle, _recipe, delta, _rng)
		Motion.advance(particle, _recipe, delta)
	var rotation_speed := 0.0
	var first := true
	for birth: Dictionary in result.births:
		var particle := Motion.spawn(_recipe, birth, transform, _rng, delta)
		Style.initialize(particle, _recipe, _rng)
		if int(_recipe.particle.BillboardType) == 3:
			# Original ground-plane rotation is captured at birth, including attached particles.
			var cosine := sqrt(maxf(0.0, 1.0 - transform.basis.y.z * transform.basis.y.z))
			if cosine >= 0.00001:
				particle.rotation += rad_to_deg(atan2(transform.basis.x.z, transform.basis.z.z))
		if first:
			rotation_speed = Style.batch_rotation(_recipe.particle, _rng)
			first = false
		particle.rotation_speed = rotation_speed
		particles[int(birth.id)] = particle
	return result
