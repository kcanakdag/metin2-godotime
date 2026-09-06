extends SceneTree
## Exercises actual GameConnection instances over WebSockets against the real module.

const ConnectionScript := preload("res://scripts/net/game_connection.gd")
var _server := "http://127.0.0.1:3210"
var _database := "mt2-dev-world"
var _report_path := "user://multiplayer-report.json"
var _profile_prefix := "smoke"
var _checks: Array = []
var _clients: Array[GameConnection] = []
var _errors: Array[String] = []
var _finished := false


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	for i in range(0, args.size() - 1, 2):
		match args[i]:
			"--server":
				_server = args[i + 1]
			"--database":
				_database = args[i + 1]
			"--report":
				_report_path = args[i + 1]
			"--profile-prefix":
				_profile_prefix = args[i + 1]
	call_deferred("_run")


func _run() -> void:
	var first := _make_client()
	var second := _make_client()
	first.connect_game(_server, _database, "SmokeA", _profile_prefix + "-a")
	second.connect_game(_server, _database, "SmokeB", _profile_prefix + "-b")
	var ready := await _wait_until(
		func(): return first.state == "connected" and second.state == "connected", 15.0
	)
	if not _check("two_clients_connected", ready):
		_finish()
		return
	_check("distinct_identities", first.local_identity != second.local_identity)
	_check(
		"world_configuration", not first.world_info.is_empty() and not second.world_info.is_empty()
	)
	_check(
		"obstacles_replicated",
		(
			first.obstacles == second.obstacles
			and (
				not first.obstacles.is_empty() or first.world_info.get("map_id") == "metin2_map_a1"
			)
		)
	)
	var first_id := first.local_identity
	var second_id := second.local_identity
	var mutual := await _wait_until(
		func():
			return (
				not _player(second, first_id).is_empty()
				and not _player(first, second_id).is_empty()
			)
	)
	_check("mutual_visibility", mutual)
	if not mutual:
		_finish()
		return
	var start := _position(_player(second, first_id))
	first.set_move_input(1.0, 0.0)
	await create_timer(0.3).timeout
	first.stop_moving()
	var moved := await _wait_until(
		func(): return _position(_player(second, first_id)).distance_to(start) > 0.25
	)
	_check("movement_replicates", moved)
	var second_start := _position(_player(first, second_id))
	second.set_move_input(-1.0, 0.0)
	await create_timer(0.3).timeout
	second.stop_moving()
	_check(
		"second_player_movement_replicates",
		await _wait_until(
			func(): return _position(_player(first, second_id)).distance_to(second_start) > 0.25
		)
	)
	await create_timer(0.15).timeout
	var stopped := _position(_player(second, first_id))
	await create_timer(0.2).timeout
	_check(
		"stop_is_authoritative", _position(_player(second, first_id)).distance_to(stopped) < 0.02
	)
	var click_target := stopped + Vector2(0.0, 1.0)
	first.move_to(click_target.x, click_target.y)
	_check(
		"click_target_reached",
		await _wait_until(
			func(): return _position(_player(second, first_id)).distance_to(click_target) < 0.05
		)
	)
	var attack_before := int(_player(second, first_id).get("attack_sequence", 0))
	first.perform_attack()
	_check(
		"attack_replicates",
		await _wait_until(
			func(): return int(_player(second, first_id).get("attack_sequence", 0)) > attack_before
		)
	)
	var chat_text := "Smoke-%s" % _profile_prefix
	first.send_chat(chat_text)
	_check("chat_replicates", await _wait_until(_has_chat.bind(second, chat_text)))
	var errors_before := _errors.size()
	first.set_move_input(2.0, 0.0)
	_check(
		"invalid_input_returns_error",
		await _wait_until(func(): return _errors.size() > errors_before)
	)
	_check("reducer_rejection_keeps_connection", first.state == "connected")
	var duplicate := _make_client()
	duplicate.connect_game(_server, _database, "Duplicate", _profile_prefix + "-a")
	_check(
		"duplicate_identity_rejected", await _wait_until(func(): return duplicate.state == "error")
	)
	_check("duplicate_rejection_reason", "already playing" in duplicate.state_message)
	await create_timer(1.1).timeout
	first.send_chat(chat_text + "-original")
	_check(
		"original_session_survives_duplicate",
		await _wait_until(_has_chat.bind(second, chat_text + "-original"))
	)
	first.disconnect_game()
	_check("disconnect_preserves_window_close", auto_accept_quit)
	_check(
		"disconnect_removes_presence",
		await _wait_until(func(): return _player(second, first_id).is_empty())
	)
	first.reconnect_game()
	_check("reconnect_succeeds", await _wait_until(func(): return first.state == "connected", 15.0))
	_check("reconnect_preserves_identity", first.local_identity == first_id)
	_check(
		"reconnect_restores_presence",
		await _wait_until(func(): return not _player(second, first_id).is_empty())
	)
	_check("network_counters", first.rx_messages > 0 and first.tx_messages > 0)
	_finish()


func _make_client() -> GameConnection:
	var client: GameConnection = ConnectionScript.new()
	root.add_child(client)
	client.reducer_failed.connect(func(message: String): _errors.append(message))
	_clients.append(client)
	return client


func _player(client: GameConnection, identity: String) -> Dictionary:
	for row: Dictionary in client.players:
		if row.get("identity") == identity:
			return row
	return {}


func _has_chat(client: GameConnection, message: String) -> bool:
	for row: Dictionary in client.chat:
		if row.get("message") == message:
			return true
	return false


func _position(row: Dictionary) -> Vector2:
	return Vector2(float(row.get("x", 0.0)), float(row.get("z", 0.0)))


func _wait_until(predicate: Callable, timeout_seconds := 5.0) -> bool:
	var deadline := Time.get_ticks_msec() + int(timeout_seconds * 1000.0)
	while Time.get_ticks_msec() < deadline:
		if predicate.call():
			return true
		await create_timer(0.025).timeout
	return bool(predicate.call())


func _check(check_name: String, passed: bool) -> bool:
	_checks.append({"name": check_name, "passed": passed})
	print("MT2_CHECK ", check_name, " ", "PASS" if passed else "FAIL")
	return passed


func _finish() -> void:
	if _finished:
		return
	_finished = true
	var client_states: Array = []
	for client: GameConnection in _clients:
		client_states.append({"state": client.state, "message": client.state_message})
		client.disconnect_game()
	await create_timer(0.1).timeout
	var passed := _checks.all(func(check: Dictionary): return check["passed"])
	var report := {
		"passed": passed,
		"database": _database,
		"checks": _checks,
		"client_states": client_states,
		"reducer_errors_observed": _errors.size()
	}
	var file := FileAccess.open(_report_path, FileAccess.WRITE)
	if file:
		file.store_string(JSON.stringify(report, "\t"))
		file.close()
	else:
		printerr("Cannot write multiplayer report: ", _report_path)
		passed = false
	print("MT2_MULTIPLAYER_SMOKE ", "PASS" if passed else "FAIL")
	quit(0 if passed else 1)
