extends SceneTree
## Click-to-interact reservation survives the 240 s session-refresh reconnect.
##
## The account flow tears the world session down and rebuilds it while the auth
## token refreshes. A click the player already made must resume once the new
## session is authoritative instead of freezing the character mid-route, and it
## must never leak a movement intent into a generation that no longer exists.
const Approach := preload("res://scripts/world/npc_approach.gd")
const GUARD := "spawn.yongan.city-guard-20354"
const OWNER := "owner-identity"


class ConnectionSpy:
	extends GameConnection
	var moves: Array[Vector2] = []
	var stops := 0
	var interacts: Array[String] = []

	func _process(_delta: float) -> void:
		pass

	func move_to(x: float, z: float) -> void:
		moves.append(Vector2(x, z))

	func stop_moving() -> void:
		stops += 1

	func interact_npc(spawn_id: String) -> void:
		interacts.append(spawn_id)

	func enter(next_state: String) -> void:
		state = next_state
		connection_state_changed.emit(next_state, "Offline reconnect component QA")


class Registry:
	var actors := {}

	func find_actor(spawn_id: String) -> NpcActor:
		var found: Variant = actors.get(spawn_id)
		return found if found is NpcActor else null


var _checks := 0
var _failures: Array[String] = []


func _initialize() -> void:
	create_timer(60).timeout.connect(func(): quit(1))
	_run.call_deferred()


func _run() -> void:
	var connection := ConnectionSpy.new()
	root.add_child(connection)
	connection.local_identity = OWNER
	connection.world_info = {"npc_catalog_hash": "0".repeat(64)}
	var registry := Registry.new()
	var driver := Approach.attach(root, connection, registry.find_actor)
	_check(driver.get("_spawn_id") == "", "attach alone reserves no interaction")
	_check(
		driver.get("_connection") == connection and driver.get("_resolve").is_valid(),
		"attach keeps the connection and the actor resolver"
	)
	_check_click_survives_reconnect(connection, registry, driver)
	_check_rebuilt_presentation(connection, registry, driver)
	_check_stall_reissue(connection, registry, driver)
	_check_dead_character_cancels(connection, registry, driver)
	_check_reducer_failure_cancels(connection, registry, driver)
	_check_deadline_timeout(connection, registry, driver)
	_check_disconnected_start(connection, registry, driver)
	await _check_automatic_processing(connection, registry, driver)
	_finish(connection)


func _check_click_survives_reconnect(
	connection: ConnectionSpy, registry: Registry, driver: NpcApproach
) -> void:
	var actor := _spawn_actor(registry, GUARD, Vector3(0, 198.5, 15))
	_track(connection)
	connection.enter("connected")
	connection.players = [_player(0.0, 0.0)]
	driver.start(actor)
	_check(driver.get("_spawn_id") == GUARD, "click reserves the exact spawn id")
	_check(connection.moves.size() == 1, "first click issues one movement intent")
	_check(
		connection.moves.size() == 1 and connection.moves[0].is_equal_approx(Vector2(0.0, 15.0)),
		"intent targets the authoritative NPC position"
	)
	driver.call("_process", 0.0)
	_check(connection.moves.size() == 1, "routine frames do not repeat the intent")
	# The account flow disconnects the world session and rebuilds it while the
	# token refreshes; the server stops the character for the dead session.
	connection.enter("connecting")
	driver.call("_process", 0.0)
	_check(driver.get("_spawn_id") == GUARD, "reconnect keeps the click reservation")
	_check(connection.moves.size() == 1, "dead generation receives no new intent")
	_check(connection.stops == 0, "reconnect never cancels a player click")
	# The restored session reports the character where the server stopped it.
	connection.players = [_player(0.0, 7.0)]
	connection.enter("connected")
	_check(driver.get("_spawn_id") == GUARD, "restored session keeps the reservation")
	driver.call("_process", 0.0)
	_check(connection.moves.size() == 2, "restored session re-issues the move once")
	_check(
		connection.moves.size() >= 2 and connection.moves[1].is_equal_approx(Vector2(0.0, 15.0)),
		"re-issue reuses the authoritative NPC position"
	)
	driver.call("_process", 0.0)
	_check(connection.moves.size() == 2, "re-issue does not repeat every frame")
	connection.players = [_player(0.0, 9.0)]
	driver.call("_process", 0.0)
	_check(connection.interacts.is_empty(), "out-of-range progress does not interact")
	_check(connection.moves.size() == 2, "closing distance does not spam the server")
	connection.players = [_player(0.0, 11.5)]
	driver.call("_process", 0.0)
	_check(connection.interacts == [GUARD], "arrival requests the interaction exactly once")
	_check(connection.stops == 1, "arrival stops the authoritative character once")
	driver.call("_process", 0.0)
	_check(connection.interacts.size() == 1, "completed reservation cannot re-trigger")
	driver.cancel(true)
	_check(connection.stops == 1, "cancelling a finished reservation is inert")
	_release(registry, GUARD, actor)


func _check_rebuilt_presentation(
	connection: ConnectionSpy, registry: Registry, driver: NpcApproach
) -> void:
	# A reconnect rebuilds the NPC presentation, so the cached node is freed while
	# the reservation is still waiting for the player to arrive.
	var stale := _spawn_actor(registry, GUARD, Vector3(4, 198.5, 4))
	_track(connection)
	connection.enter("connected")
	connection.players = [_player(0.0, 0.0)]
	driver.start(stale)
	root.remove_child(stale)
	stale.free()
	var rebuilt := _spawn_actor(registry, GUARD, Vector3(4, 198.5, 4))
	driver.call("_process", 0.0)
	_check(driver.get("_spawn_id") == GUARD, "freed actor keeps the reservation")
	_check(connection.interacts.is_empty(), "rebuilt actor out of range does not interact")
	_check(connection.stops == 0, "presentation rebuild does not cancel the click")
	connection.players = [_player(4.0, 8.0)]
	driver.call("_process", 0.0)
	_check(connection.interacts == [GUARD], "rebuilt actor resumes the interaction")
	_release(registry, GUARD, rebuilt)


func _check_stall_reissue(
	connection: ConnectionSpy, registry: Registry, driver: NpcApproach
) -> void:
	var actor := _spawn_actor(registry, GUARD, Vector3(20, 198.5, 20))
	_track(connection)
	connection.enter("connected")
	connection.players = [_player(0.0, 0.0)]
	driver.start(actor)
	_check(connection.moves.size() == 1, "stall fixture issues its first intent")
	driver.call("_process", 0.0)
	_check(connection.moves.size() == 1, "live intent is not duplicated")
	# The authoritative position never moved, so the accepted request never arrived.
	driver.set("_stall_at", Time.get_ticks_msec() - 1)
	driver.call("_process", 0.0)
	_check(connection.moves.size() == 2, "stalled approach re-issues the intent")
	_check(
		connection.moves.size() >= 2 and connection.moves[1].is_equal_approx(Vector2(20.0, 20.0)),
		"stall re-issue targets the NPC instead of a stale character position"
	)
	driver.set("_stall_at", Time.get_ticks_msec() + Approach.STALL_MS)
	driver.call("_process", 0.0)
	_check(connection.moves.size() == 2, "refreshed window suppresses another intent")
	_release(registry, GUARD, actor)


func _check_dead_character_cancels(
	connection: ConnectionSpy, registry: Registry, driver: NpcApproach
) -> void:
	var actor := _spawn_actor(registry, GUARD, Vector3(0, 198.5, 15))
	_track(connection)
	connection.enter("connected")
	connection.players = [_player(0.0, 0.0)]
	driver.start(actor)
	connection.players = [_player(0.0, 0.0, 0)]
	driver.call("_process", 0.0)
	_check(connection.interacts.is_empty(), "dead character does not interact")
	_check(driver.get("_spawn_id") == "", "death releases the click reservation")
	_check(connection.stops == 1, "death stops the authoritative character")
	driver.call("_process", 0.0)
	_check(connection.moves.size() == 1, "released reservation issues no more intents")
	_release(registry, GUARD, actor)


func _check_reducer_failure_cancels(
	connection: ConnectionSpy, registry: Registry, driver: NpcApproach
) -> void:
	var actor := _spawn_actor(registry, GUARD, Vector3(0, 198.5, 15))
	_track(connection)
	connection.enter("connected")
	connection.players = [_player(0.0, 0.0)]
	driver.start(actor)
	connection.reducer_failed.emit("Move request rejected.")
	_check(driver.get("_spawn_id") == "", "reducer rejection releases the reservation")
	_check(connection.stops == 1, "reducer rejection stops the character")
	_check(connection.interacts.is_empty(), "rejected reservation cannot interact")
	driver.call("_process", 0.0)
	_check(connection.moves.size() == 1, "rejected reservation issues no more intents")
	_release(registry, GUARD, actor)


func _check_deadline_timeout(
	connection: ConnectionSpy, registry: Registry, driver: NpcApproach
) -> void:
	var actor := _spawn_actor(registry, GUARD, Vector3(0, 198.5, 15))
	_track(connection)
	connection.enter("connected")
	connection.players = [_player(0.0, 0.0)]
	driver.start(actor)
	_check(
		int(driver.get("_deadline")) > Time.get_ticks_msec(),
		"reservation carries a bounded lifetime"
	)
	driver.set("_deadline", Time.get_ticks_msec() - 1)
	driver.call("_process", 0.0)
	_check(driver.get("_spawn_id") == "", "expired reservation releases the click")
	_check(connection.stops == 1, "expired reservation stops the character")
	_check(connection.interacts.is_empty(), "expired reservation does not interact")
	_release(registry, GUARD, actor)


func _check_disconnected_start(
	connection: ConnectionSpy, registry: Registry, driver: NpcApproach
) -> void:
	var actor := _spawn_actor(registry, GUARD, Vector3(0, 198.5, 15))
	_track(connection)
	connection.enter("loading")
	connection.players = [_player(0.0, 0.0)]
	driver.start(actor)
	_check(driver.get("_spawn_id") == "", "loading session refuses a new click")
	driver.call("_process", 0.0)
	_check(connection.moves.is_empty(), "refused click sends no intent")
	# An intent already in flight must never be re-issued for a dead generation.
	connection.enter("connected")
	driver.start(actor)
	_check(connection.moves.size() == 1, "connected session accepts the click")
	connection.enter("disconnected")
	driver.call("_process", 0.0)
	_check(connection.moves.size() == 1, "disconnected session holds the intent")
	driver.cancel(true)
	_check(connection.stops == 0, "offline cancel never sends a movement intent")
	_check(driver.get("_spawn_id") == "", "offline cancel releases the reservation")
	_release(registry, GUARD, actor)


func _check_automatic_processing(
	connection: ConnectionSpy, registry: Registry, driver: NpcApproach
) -> void:
	# Every check above drives _process directly for determinism; confirm the real
	# frame loop resumes a reservation without any manual pumping.
	var actor := _spawn_actor(registry, GUARD, Vector3(0, 198.5, 15))
	_track(connection)
	connection.enter("connected")
	connection.players = [_player(0.0, 0.0)]
	driver.start(actor)
	connection.players = [_player(0.0, 6.0)]
	connection.enter("connecting")
	connection.enter("connected")
	for _frame in range(4):
		await process_frame
	_check(connection.moves.size() == 2, "frame loop resumes the click after a reconnect")
	_check(connection.interacts.is_empty(), "resumed approach still respects range")
	driver.cancel()
	_release(registry, GUARD, actor)


func _track(connection: ConnectionSpy) -> void:
	connection.moves.clear()
	connection.interacts.clear()
	connection.stops = 0


func _spawn_actor(registry: Registry, spawn_id: String, point: Vector3) -> NpcActor:
	var actor := NpcActor.new()
	actor.name = spawn_id
	actor.spawn_id = spawn_id
	actor.position = point
	root.add_child(actor)
	registry.actors[spawn_id] = actor
	return actor


func _release(registry: Registry, spawn_id: String, actor: NpcActor) -> void:
	registry.actors.erase(spawn_id)
	root.remove_child(actor)
	actor.free()


func _player(x: float, z: float, health := 100) -> Dictionary:
	return {"identity": OWNER, "health": health, "x": x, "z": z}


func _finish(connection: Node) -> void:
	var report := {
		"passed": _failures.is_empty(),
		"checks": _checks,
		"failures": _failures,
		"connection": "offline spy; no multiplayer claim",
	}
	var file := FileAccess.open("user://npc-approach-reconnect.json", FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "\t") + "\n")
	file.close()
	connection.queue_free()
	await process_frame
	print(
		"NPC_APPROACH_RECONNECT_SMOKE ",
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
		push_error("NPC_APPROACH_RECONNECT_SMOKE FAIL " + message)
