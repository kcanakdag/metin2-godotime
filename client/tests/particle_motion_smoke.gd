extends SceneTree

const Simulation = preload("res://scripts/actors/particle_simulation.gd")
const Motion = preload("res://scripts/actors/particle_motion.gd")
var _checks := 0
var _failures: Array[String] = []


func _init() -> void:
	call_deferred("_run")


func _check(label: String, condition: bool) -> void:
	_checks += 1
	if not condition:
		_failures.append(label)


func _run() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 1:
		quit(1)
		return
	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var recipe: Dictionary = catalog.effects[0].systems[0].duplicate(true)
	recipe.start_seconds = 0
	recipe.position_keys_cm = [[0, 100, 200, 300]]
	var emitter: Dictionary = recipe.emitter
	emitter.MaxEmissionCount = 30
	emitter.CycleLength = 1
	emitter.CycleLoopEnable = 1
	emitter.LoopCount = 0
	emitter.EmitterShape = 0
	emitter.EmitterAdvancedType = 0
	emitter.EmittingDirection = [0, 0, 0]
	emitter.EmittingRadius = 100
	emitter.EmitterEmitFromEdgeFlag = 1
	for key: String in emitter.curves:
		emitter.curves[key] = [[0, 0]]
	emitter.curves.EmissionCountPerSecond = [[0, 4]]
	emitter.curves.LifeTime = [[0, 2]]
	emitter.curves.EmittingDirectionY = [[0, 100]]
	emitter.curves.EmittingVelocity = [[0, 1]]
	emitter.curves.SizeX = [[0, 50]]
	emitter.curves.SizeY = [[0, 25]]
	recipe.particle.AttachEnable = 0
	recipe.particle.curves.Gravity = [[0, 100]]
	recipe.particle.curves.AirResistance = [[0, 0.5]]
	var system := Simulation.new()
	_check("configure", system.configure(recipe, 42))
	var transform := Transform3D(Basis.IDENTITY, Vector3(10, 0, 0))
	system.advance(0.25, transform)
	var first: Dictionary = system.particles[1]
	_check("source axes and centimetres", first.position.is_equal_approx(Vector3(11, 3, -2)))
	_check("original half extents", first.half_size.is_equal_approx(Vector2(0.5, 0.25)))
	_check(
		"initial stretch history", first.previous_position.is_equal_approx(Vector3(11, 3, -1.75))
	)
	transform.origin.x = 20
	system.advance(0.25, transform)
	first = system.particles[1]
	_check("gravity then drag", first.velocity.is_equal_approx(Vector3(0, -0.125, -0.5)))
	_check(
		"world particle stays behind", first.position.is_equal_approx(Vector3(11, 2.96875, -2.125))
	)
	_check("new world birth follows emitter", system.particles[2].position.x == 21)
	var before: Dictionary = system.particles.duplicate(true)
	_check("reject nonfinite step", system.advance(NAN, transform).has("error"))
	_check("rejected step unchanged", before == system.particles)
	var scaled := Transform3D(Basis.IDENTITY.scaled(Vector3.ONE * 2), Vector3.ZERO)
	_check("reject unsupported scaling", system.advance(0.25, scaled).has("error"))
	recipe.particle.AttachEnable = 1
	_check("attached configuration", system.configure(recipe, 42))
	system.advance(0.25, Transform3D.IDENTITY)
	_check(
		"attached follows current transform",
		Motion.world_position(system.particles[1], transform).x == 21
	)
	emitter.curves.EmittingAngularVelocity = [[0, 1]]
	_check("unimplemented orbit rejected", not system.configure(recipe, 42))
	emitter.curves.EmittingAngularVelocity = [[0, 0]]
	emitter.curves.EmittingDirectionY = [[0, 0]]
	emitter.EmitterAdvancedType = 1
	for shape: int in [1, 3]:
		emitter.EmitterShape = shape
		_check("shape configuration", system.configure(recipe, 42))
		system.advance(0.25, Transform3D.IDENTITY)
		var particle: Dictionary = system.particles[1]
		_check("edge radius", is_equal_approx(particle.position.distance_to(particle.center), 1.0))
		_check(
			"outward source speed",
			particle.velocity.is_equal_approx((particle.position - particle.center).normalized())
		)
		if shape == 1:
			_check("ellipse source XY plane", particle.position.y == particle.center.y)
	emitter.EmitterAdvancedType = 2
	_check("inward configuration", system.configure(recipe, 42))
	system.advance(0.25, Transform3D.IDENTITY)
	first = system.particles[1]
	_check(
		"inward source speed",
		first.velocity.is_equal_approx(-(first.position - first.center).normalized())
	)
	_exercise_catalog(catalog)
	print(JSON.stringify({"checks": _checks, "failures": _failures}))
	quit(0 if _failures.is_empty() else 1)


func _exercise_catalog(catalog: Dictionary) -> void:
	var count := 0
	for effect: Dictionary in catalog.effects:
		for recipe: Dictionary in effect.systems:
			count += 1
			var first := Simulation.new()
			var repeat := Simulation.new()
			_check(
				"original supported", first.configure(recipe, 81) and repeat.configure(recipe, 81)
			)
			var finite := true
			var consistent := true
			for frame: int in range(600):
				var transform := Transform3D(
					Basis(Vector3.UP, frame * 0.001), Vector3(frame * 0.002, 0, 0)
				)
				var result: Dictionary = first.advance(1.0 / 60.0, transform)
				repeat.advance(1.0 / 60.0, transform)
				consistent = consistent and first.particles == repeat.particles
				consistent = consistent and first.particles.size() == int(result.alive)
				for particle: Dictionary in first.particles.values():
					finite = (
						finite and particle.position.is_finite() and particle.velocity.is_finite()
					)
			_check("original finite trajectories", finite)
			_check("seeded replay and lifecycle agreement", consistent)
	_check("all original systems", count == 22)
