extends SceneTree
## Ground click reservation survives the 240 s session-refresh reconnect.
##
## The account flow tears the world session down and rebuilds it while the auth
## token refreshes; `open_account` stops the old character, so the server drops a
## walk the player already paid for. The reservation must re-issue its ordinary
## `move_to` intent for the restored session, keep keyboard preemption
## authoritative, and never leak an intent into a dead generation.
const Destination := preload("res://scripts/world/move_destination.gd")
const OWNER := "owner-identity"
const TARGET := Vector3(12.0, 198.5, -4.0)


class ConnectionSpy:
	extends GameConnection
	var moves: Array[Vector2] = []
	var stops := 0

	func _process(_delta: float) -> void:
		pass

	func move_to(x: float, z: float) -> void:
		moves.append(Vector2(x, z))

	func stop_moving() -> void:
		stops += 1

	func enter(next_state: String) -> void:
		state = next_state
		connection_state_changed.emit(next_state, "Offline click-to-move component QA")


var _checks := 0
var _failures: Array[String] = []


func _initialize() -> void:
	create_timer(60).timeout.connect(func(): quit(1))
	_run.call_deferred()


func _run() -> void:
	var connection := ConnectionSpy.new()
	root.add_child(connection)
	connection.local_identity = OWNER
	var driver := Destination.attach(root, connection)
	_check(driver.get("_connection") == connection, "attach keeps the connection")
	_check(not bool(driver.call("is_active")), "attach alone reserves no destination")
	_check_idle_frames(connection, driver)
	_check_click_issues_once(connection, driver)
	_check_reconnect_resumes(connection, driver)
	_check_arrival_releases(connection, driver)
	_check_arrival_tolerance(connection, driver)
	_check_dead_character_releases(connection, driver)
	_check_expired_reservation(connection, driver)
	_check_preemption(connection, driver)
	_check_offline_reservation(connection, driver)
	await _check_automatic_processing(connection, driver)
	_finish(connection)


func _check_idle_frames(connection: ConnectionSpy, driver: MoveDestination) -> void:
	_track(connection)
	connection.enter("connected")
	connection.players = [_player(0.0, 0.0)]
	for _frame in range(3):
		driver.call("_process", 0.0)
	_check(connection.moves.is_empty(), "idle frames issue no movement intent")
	_check(connection.stops == 0, "idle frames issue no stop intent")


func _check_click_issues_once(connection: ConnectionSpy, driver: MoveDestination) -> void:
	_track(connection)
	connection.enter("connected")
	connection.players = [_player(0.0, 0.0)]
	driver.start(TARGET)
	_check(bool(driver.call("is_active")), "a ground click reserves its destination")
	_check(connection.moves.size() == 1, "first click issues one movement intent")
	_check(
		(
			connection.moves.size() == 1
			and connection.moves[0].is_equal_approx(Vector2(TARGET.x, TARGET.z))
		),
		"intent targets the clicked ground point"
	)
	driver.call("_process", 0.0)
	_check(connection.moves.size() == 1, "routine frames do not repeat the intent")
	_check(
		int(driver.get("_deadline")) > Time.get_ticks_msec(),
		"reservation carries a bounded lifetime"
	)
	driver.cancel()


func _check_reconnect_resumes(connection: ConnectionSpy, driver: MoveDestination) -> void:
	_track(connection)
	connection.enter("connected")
	connection.players = [_player(0.0, 0.0)]
	driver.start(TARGET)
	_check(connection.moves.size() == 1, "connected session takes the click")
	# The account flow drops the world session while its signed token refreshes.
	connection.enter("connecting")
	driver.call("_process", 0.0)
	_check(bool(driver.call("is_active")), "reconnect keeps the click reservation")
	_check(connection.moves.size() == 1, "dead generation receives no new intent")
	_check(connection.stops == 0, "reconnect never cancels a player click")
	connection.enter("disconnected")
	driver.call("_process", 0.0)
	_check(connection.moves.size() == 1, "disconnected session holds the intent")
	# The restored session reports the character where the server stopped it.
	connection.players = [_player(3.0, -1.0)]
	connection.enter("connected")
	_check(connection.moves.size() == 2, "restored session re-issues the move once")
	_check(
		(
			connection.moves.size() >= 2
			and connection.moves[1].is_equal_approx(Vector2(TARGET.x, TARGET.z))
		),
		"re-issue reuses the clicked destination"
	)
	driver.call("_process", 0.0)
	_check(connection.moves.size() == 2, "re-issue does not repeat every frame")
	_check(connection.stops == 0, "resumed walk issues no stop intent")
	driver.cancel()


func _check_arrival_releases(connection: ConnectionSpy, driver: MoveDestination) -> void:
	_track(connection)
	connection.enter("connected")
	connection.players = [_player(0.0, 0.0)]
	driver.start(TARGET)
	# The server walks the character itself; approaching is progress, not arrival.
	connection.players = [_player(TARGET.x - 4.0, TARGET.z)]
	driver.call("_process", 0.0)
	_check(bool(driver.call("is_active")), "mid-route progress keeps the reservation")
	_check(connection.moves.size() == 1, "closing distance does not spam the server")
	connection.players = [_player(TARGET.x - 0.5, TARGET.z)]
	driver.call("_process", 0.0)
	_check(not bool(driver.call("is_active")), "arrival releases the reservation")
	_check(connection.stops == 0, "a completed walk sends no stop intent")
	driver.call("_process", 0.0)
	_check(connection.moves.size() == 1, "completed reservation issues no more intents")
	driver.cancel(true)
	_check(connection.stops == 0, "cancelling a finished reservation is inert")


func _check_arrival_tolerance(connection: ConnectionSpy, driver: MoveDestination) -> void:
	_track(connection)
	connection.enter("connected")
	connection.players = [_player(0.0, 0.0)]
	driver.start(TARGET)
	connection.players = [_player(TARGET.x, TARGET.z + Destination.ARRIVAL_DISTANCE + 0.05)]
	driver.call("_process", 0.0)
	_check(bool(driver.call("is_active")), "just outside the epsilon keeps walking")
	connection.players = [_player(TARGET.x, TARGET.z + Destination.ARRIVAL_DISTANCE - 0.05)]
	driver.call("_process", 0.0)
	_check(not bool(driver.call("is_active")), "just inside the epsilon arrives")


func _check_dead_character_releases(connection: ConnectionSpy, driver: MoveDestination) -> void:
	_track(connection)
	connection.enter("connected")
	connection.players = [_player(0.0, 0.0)]
	driver.start(TARGET)
	connection.players = [_player(0.0, 0.0, 0)]
	driver.call("_process", 0.0)
	_check(not bool(driver.call("is_active")), "death releases the click reservation")
	_check(connection.stops == 0, "death needs no stop intent")
	driver.call("_process", 0.0)
	_check(connection.moves.size() == 1, "released reservation issues no more intents")
	_check(connection.stops == 0, "released reservation issues no stop intent")


func _check_expired_reservation(connection: ConnectionSpy, driver: MoveDestination) -> void:
	_track(connection)
	connection.enter("connected")
	connection.players = [_player(0.0, 0.0)]
	driver.start(TARGET)
	driver.set("_deadline", Time.get_ticks_msec() - 1)
	driver.call("_process", 0.0)
	_check(not bool(driver.call("is_active")), "expired reservation releases the click")
	_check(connection.stops == 1, "expired reservation stops the character once")
	driver.call("_process", 0.0)
	_check(connection.stops == 1, "expiry does not repeat the stop intent")


func _check_preemption(connection: ConnectionSpy, driver: MoveDestination) -> void:
	_track(connection)
	connection.enter("connected")
	connection.players = [_player(0.0, 0.0)]
	driver.start(TARGET)
	# Keyboard input, Escape or Space preempts the ground click.
	driver.cancel(true)
	_check(not bool(driver.call("is_active")), "keyboard input releases the reservation")
	_check(connection.stops == 1, "keyboard input stops the walk once")
	driver.call("_process", 0.0)
	_check(connection.moves.size() == 1, "released reservation cannot re-issue")
	# A fresh click replaces the old destination instead of queueing both.
	driver.start(TARGET)
	var second := Vector3(-8.0, 198.5, 20.0)
	driver.start(second)
	_check(
		(
			connection.moves.size() == 3
			and connection.moves[2].is_equal_approx(Vector2(second.x, second.z))
		),
		"a second click replaces the previous destination"
	)
	driver.cancel(true)


func _check_offline_reservation(connection: ConnectionSpy, driver: MoveDestination) -> void:
	_track(connection)
	connection.enter("loading")
	connection.players = [_player(0.0, 0.0)]
	driver.start(TARGET)
	_check(bool(driver.call("is_active")), "a click during loading waits for the session")
	_check(connection.moves.is_empty(), "loading session sends no intent")
	driver.call("_process", 0.0)
	_check(connection.moves.is_empty(), "loading frames send no intent")
	connection.enter("connected")
	_check(connection.moves.size() == 1, "restored session takes the waiting click")
	_check(
		(
			connection.moves.size() == 1
			and connection.moves[0].is_equal_approx(Vector2(TARGET.x, TARGET.z))
		),
		"waiting click kept its destination"
	)
	connection.enter("disconnected")
	driver.call("_process", 0.0)
	driver.cancel(true)
	_check(connection.stops == 0, "offline cancel never sends a movement intent")
	_check(not bool(driver.call("is_active")), "offline cancel releases the reservation")


func _check_automatic_processing(connection: ConnectionSpy, driver: MoveDestination) -> void:
	# Every check above drives _process directly for determinism; confirm the real
	# frame loop resumes a click without any manual pumping.
	_track(connection)
	connection.enter("connected")
	connection.players = [_player(0.0, 0.0)]
	driver.start(TARGET)
	connection.players = [_player(1.0, 2.0)]
	connection.enter("connecting")
	connection.enter("connected")
	for _frame in range(4):
		await process_frame
	_check(connection.moves.size() == 2, "frame loop resumes the click after a reconnect")
	_check(bool(driver.call("is_active")), "resumed walk is still under way")
	driver.cancel(true)
	await process_frame
	_check(connection.stops == 1, "cancelling the resumed walk stops the character")


func _track(connection: ConnectionSpy) -> void:
	connection.moves.clear()
	connection.stops = 0


func _player(x: float, z: float, health := 100) -> Dictionary:
	return {"identity": OWNER, "health": health, "x": x, "z": z}


func _finish(connection: Node) -> void:
	var report := {
		"passed": _failures.is_empty(),
		"checks": _checks,
		"failures": _failures,
		"connection": "offline spy; no multiplayer claim",
	}
	var file := FileAccess.open("user://move-destination.json", FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "\t") + "\n")
	file.close()
	connection.queue_free()
	await process_frame
	print(
		"MOVE_DESTINATION_SMOKE ",
		"PASS" if _failures.is_empty() else "FAIL",
		" ",
		_checks,
		" checks"
	)
	quit(0 if _failures.is_empty() else 1)


func _check(value: bool, message: String) -> void:
	if value:
		_checks += 1
	else:
		_failures.append(message)
		push_error("MOVE_DESTINATION_SMOKE FAIL " + message)
