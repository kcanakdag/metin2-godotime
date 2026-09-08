extends SceneTree

const Flight = preload("res://scripts/actors/projectile_flight.gd")
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
	var inventory: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var count := 0
	for entry: Dictionary in inventory.flight_definitions:
		count += 1
		for target: Vector3 in [Vector3(0, 0, 20), Vector3(12, 5, -4), Vector3(0, 20, 0)]:
			var flight := Flight.new()
			_check("original configure", flight.configure(entry.flight, Vector3.ZERO, target))
			_check(
				"original launch speed",
				is_equal_approx(
					flight.velocity.length(), float(entry.flight.InitialVelocity) * 0.01
				)
			)
			_check(
				"original launch direction",
				flight.velocity.normalized().is_equal_approx(target.normalized())
			)
			var event := ""
			var hits := 0
			for unused: int in range(1200):
				var step: Dictionary = flight.advance(1.0 / 60.0, target)
				event = step.event
				if event == "target_hit":
					hits += 1
				if not flight.alive:
					break
			_check("original target reached", event == "target_hit" and hits == 1)
			_check(
				"dead projectile cannot hit twice", flight.advance(0.1, target).event == "inactive"
			)
	_check("all four original flight definitions", count == 4)
	var definition: Dictionary = inventory.flight_definitions[3].flight.duplicate(true)
	definition.HomingFlag = false
	definition.BombRange = 25
	var target := Vector3(0, 0, 10)
	var flight := Flight.new()
	_check("crossing setup", flight.configure(definition, Vector3.ZERO, target))
	_check(
		"segment hit despite endpoint overshoot", flight.advance(0.5, target).event == "target_hit"
	)
	definition.Range = 1999
	_check("short range setup", flight.configure(definition, Vector3.ZERO, target))
	_check("range expiry precedes hit", flight.advance(0.5, target).event == "out_of_range")
	definition.Range = 2000
	_check("exact range setup", flight.configure(definition, Vector3.ZERO, target))
	_check("zero range remaining still hits", flight.advance(0.5, target).event == "target_hit")
	definition.Range = 5000
	_check("tangent setup", flight.configure(definition, Vector3.ZERO, target))
	_check(
		"strict radius tangent misses",
		flight.advance(0.5, target + Vector3(0.25, 0, 0), false).event == "flying"
	)
	definition.InitialVelocity = 1000
	definition.Acceleration = [0, -100, 0]
	definition.Gravity = 100
	_check("force setup", flight.configure(definition, Vector3.ZERO, target))
	flight.advance(0.25, target)
	_check("positive flight gravity", flight.velocity.is_equal_approx(Vector3(0, 0.25, 10.25)))
	_check("force before movement", flight.position.is_equal_approx(Vector3(0, 0.0625, 2.5625)))
	definition.Gravity = 0
	definition.HomingFlag = true
	definition.HomingStartTime = 0.25
	_check("homing setup", flight.configure(definition, Vector3.ZERO, target))
	var changed_target := Vector3(10, 0, 10)
	flight.advance(0.25, changed_target)
	_check("strict homing deadline", is_zero_approx(flight.velocity.x))
	var direction := (changed_target - flight.position).normalized()
	flight.advance(0.25, changed_target)
	_check("homing redirects velocity", flight.velocity.normalized().is_equal_approx(direction))
	_check(
		"homing redirects acceleration", flight.acceleration.normalized().is_equal_approx(direction)
	)
	var before := flight.position
	_check("reject nonfinite step", flight.advance(NAN, target).has("error"))
	_check("failed step preserves position", flight.position == before)
	definition.HitOnBackground = true
	_check(
		"unsupported background collisions reject",
		not flight.configure(definition, Vector3.ZERO, target)
	)
	_check("failed configuration preserves state", flight.position == before)
	print(JSON.stringify({"checks": _checks, "failures": _failures}))
	quit(0 if _failures.is_empty() else 1)
