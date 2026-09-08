extends SceneTree

const HeldInput = preload("res://scripts/actors/attack_input.gd")
var _checks := 0
var _failures: Array[String] = []


func _initialize() -> void:
	var input := HeldInput.new()
	var idle := {"health": 100, "attack_sequence": 0, "life_sequence": 0, "action_ends_at_us": 0}
	_check("first press sends", input.pressed(idle, 1000))
	_check("second press cannot overlap pending request", not input.pressed(idle, 1100))
	for ticks in [1150, 1300, 1450, 1600]:
		_check("stale idle pending %d" % ticks, not _send(input, idle, ticks))
	input.on_reducer_completed("move_to", true, 1700000)
	_check("unrelated acknowledgement cannot unlock", not _send(input, idle, 1700))
	input.completed(true)
	_check("acceptance waits for authoritative action", not _send(input, idle, 1800))
	idle.attack_sequence = 1
	_check("next idle action permits restart", _send(input, idle, 2000))
	input.release()
	_check("release preserves pending gate", not input.pressed(idle, 2200))
	input.completed(false)
	_check("rejection permits retry", _send(input, idle, 2400))
	input.completed(true)
	input.release()
	idle.attack_sequence = 2
	_check("released key does not restart", not _send(input, idle, 2600))
	input.reset()
	_check("connection reset clears held input", not _send(input, idle, 2800))
	_check("new connection permits press", input.pressed(idle, 3000))
	input.completed(true)
	idle.health = 0
	_check("dead player cannot repeat", not _send(input, idle, 3200))
	idle.health = 100
	idle.life_sequence = 1
	_check("new life permits restart with same sequence", _send(input, idle, 3400))
	input.reset()
	_check("reset pending request permits new session", input.pressed(idle, 3600))
	print(JSON.stringify({"checks": _checks, "failures": _failures}))
	quit(0 if _failures.is_empty() else 1)


func _send(input: RefCounted, row: Dictionary, ticks: int) -> bool:
	return input.should_send(row, null, ticks * 1000, ticks, "actor.player.warrior-male")


func _check(label: String, condition: bool) -> void:
	_checks += 1
	if not condition:
		_failures.append(label)
