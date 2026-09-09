extends SceneTree
## Exercise the real input adapter with captured ordinary reducer intents.
var _checks := 0
var _failed := false
var _loaded_limit := 10.0
var _blocked_ahead := false


class CapturingConnection:
	extends GameConnection
	var calls: Array = []

	func _call_reducer(
		name: String, args: Array = [], _types: Array = [], _joining := false, _lobby := false
	) -> void:
		calls.append({"name": name, "args": args})


func _initialize() -> void:
	var client := CapturingConnection.new()
	client.state = "connected"
	client.local_identity = "owner"
	client.account_identity = "account"
	client.players = [{"identity": "owner", "life_sequence": 0, "health": 100, "x": 0, "z": 0}]
	client.monsters = [{"id": 1, "life_sequence": 2, "health": 100, "x": 12, "z": 0}]
	client.combat_target = {
		"account": "account", "character_id": "owner", "target_id": 1, "target_life_sequence": 2
	}
	var driver := ChargeSkillInput.new()
	driver.configure(client)
	driver.movement_ready = _ready_at
	_check(driver.request(5), "charge input handled")
	_check(client.calls.is_empty(), "unloaded target spends no charge")
	client.monsters[0].x = 8
	driver.request(5)
	_check(client.calls.back().name == "begin_charge", "loaded target begins")
	client.charges = [{"character_id": "owner", "skill_vnum": 5}]
	driver._process(0.1)
	_check(client.calls.back().args == [8.0, 0.0], "approach uses current destination")
	client.monsters[0].x = 9
	driver._approach._next_move_ms = 0
	driver._process(0.1)
	_check(client.calls.back().args == [9.0, 0.0], "moving target updates destination")
	client.monsters[0].x = 11
	driver._process(0.1)
	_check(client.calls.back().name == "stop_moving", "unloaded target stops movement")
	_check(driver._approach.phase == "idle", "unloaded target clears reservation")
	var count := client.calls.size()
	driver._process(0.1)
	_check(client.calls.size() == count, "no delayed strike after stream cancellation")
	client.monsters[0].x = 8
	driver.request(5)
	_check(client.calls.size() == count, "loaded retry reuses existing paid charge")
	driver._process(0.1)
	_check(client.calls.back().name == "move_to", "retry resumes ordinary movement")
	_loaded_limit = -1
	driver._process(0.1)
	_check(client.calls.back().name == "stop_moving", "lost owner terrain cancels")
	_loaded_limit = 10
	_blocked_ahead = true
	count = client.calls.size()
	driver.request(5)
	_check(client.calls.size() == count, "unloaded lookahead blocks loaded endpoints")
	_blocked_ahead = false
	client.monsters[0].x = NAN
	driver.request(5)
	_check(client.calls.size() == count, "invalid coordinates never send movement or charge")
	driver.free()
	client.free()
	if not _failed:
		print("CHARGE_INPUT_STREAM_SMOKE PASS ", _checks, " checks")
	quit(1 if _failed else 0)


func _ready_at(point: Vector3) -> bool:
	return point.x <= _loaded_limit and not (_blocked_ahead and is_equal_approx(point.x, 2.0))


func _check(passed: bool, label: String) -> void:
	_checks += 1
	if not passed:
		_failed = true
		push_error("CHARGE_INPUT_STREAM_SMOKE FAIL " + label)
