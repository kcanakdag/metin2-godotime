extends SceneTree

const Emission = preload("res://scripts/actors/particle_emission.gd")
var _checks := 0
var _failures: Array[String] = []


func _init() -> void:
	call_deferred("_run")


func _check(label: String, condition: bool) -> void:
	_checks += 1
	if not condition:
		_failures.append(label)


func _recipe() -> Dictionary:
	return {
		"start_seconds": 0.0,
		"emitter":
		{
			"MaxEmissionCount": 2,
			"CycleLength": 1.0,
			"CycleLoopEnable": 1,
			"LoopCount": 0,
			"curves": {"EmissionCountPerSecond": [[0, 8]], "LifeTime": [[0, 0.25]]},
		}
	}


func _run() -> void:
	var system := Emission.new()
	var recipe := _recipe()
	_check("configure", system.configure(recipe))
	var first: Dictionary = system.advance(0.125)
	_check("one birth", first.births.size() == 1)
	_check("second birth", system.advance(0.125).alive == 2)
	_check("exact zero life survives", system.advance(0.125).deaths.is_empty())
	var replaced: Dictionary = system.advance(0.125)
	_check("new IDs after death", replaced.deaths == [1] and replaced.births[0].id == 3)
	_check("invalid step", system.advance(NAN).has("error"))
	_check("inactive emitter", system.advance(0.125, false).births.is_empty())
	_check("empty curve", Emission.sample([], 1.0) == 0.0)
	_check("interpolation", Emission.sample([[0, 2], [1, 6]], 0.5) == 4.0)
	recipe.start_seconds = 0.2
	_check("delay configuration", system.configure(recipe))
	_check("delay before start", system.advance(0.125).alive == 0)
	_check("activation frame emits nothing", system.advance(0.125).alive == 0)
	_check("first active frame", system.advance(0.125).alive == 1)
	recipe = _recipe()
	recipe.emitter.CycleLength = 0.25
	recipe.emitter.LoopCount = 2
	_check("finite loops", system.configure(recipe))
	for i: int in range(10):
		var state: Dictionary = system.advance(0.125)
		if i == 9:
			_check("finite effect completes", state.finished and state.alive == 0)
	recipe.emitter.LoopCount = 0
	_check("infinite loops", system.configure(recipe))
	for unused: int in range(20):
		system.advance(0.125)
	_check("zero loop count stays active", not system.advance(0.125).finished)
	recipe = _recipe()
	recipe.emitter.MaxEmissionCount = 1
	recipe.emitter.curves.EmissionCountPerSecond = [[0, 16], [0.375, 0]]
	recipe.emitter.curves.LifeTime = [[0, 0.125]]
	_check("capacity configuration", system.configure(recipe))
	system.advance(0.125)
	system.advance(0.125)
	_check("clipped births never queue", system.advance(0.125).alive == 0)
	for bad: Variant in [NAN, -1, true, 5000]:
		recipe.emitter.MaxEmissionCount = bad
		_check("reject invalid capacity", not system.configure(recipe))
	var args := OS.get_cmdline_user_args()
	if args.size() != 1:
		_check("requires converted catalog", false)
	else:
		_exercise_catalog(args[0])
	print(JSON.stringify({"checks": _checks, "failures": _failures}))
	quit(0 if _failures.is_empty() else 1)


func _exercise_catalog(path: String) -> void:
	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	var systems := 0
	for effect: Dictionary in catalog.effects:
		for recipe: Dictionary in effect.systems:
			systems += 1
			var system := Emission.new()
			if not system.configure(recipe):
				_check("original recipe rejected", false)
				continue
			var bounded := true
			var births := 0
			var state: Dictionary = {}
			for unused: int in range(1200):
				state = system.advance(1.0 / 60.0)
				bounded = bounded and state.alive <= int(recipe.emitter.MaxEmissionCount)
				births += state.births.size()
			_check("original effect emits", births > 0)
			_check("original capacity respected", bounded)
			if int(recipe.emitter.CycleLoopEnable) == 0 or int(recipe.emitter.LoopCount) > 0:
				_check("original finite emitter drains", state.finished and state.alive == 0)
	_check("all selected original systems exercised", systems == 22)
