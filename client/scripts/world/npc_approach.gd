class_name NpcApproach
extends Node
## Click reservation follows authoritative position; movement remains ordinary intent.
## A transport reconnect (session refresh, network blip) keeps the reservation and
## re-issues the authoritative move once the world session is restored, so a click
## the player already made does not silently freeze the character mid-route.

const INTERACTION_DISTANCE := 4.5
const TIMEOUT_MS := 20000
const STALL_MS := 3000
const PROGRESS_EPSILON := 0.05
var _actor: NpcActor
var _connection: GameConnection
var _resolve: Callable
var _spawn_id := ""
var _deadline := 0
var _moving := false
var _best_distance := INF
var _stall_at := 0


static func attach(
	parent: Node, connection: GameConnection, resolve_actor := Callable()
) -> NpcApproach:
	var driver := NpcApproach.new()
	parent.add_child(driver)
	driver.configure(connection, resolve_actor)
	return driver


func configure(connection: GameConnection, resolve_actor := Callable()) -> void:
	_connection = connection
	_resolve = resolve_actor
	connection.connection_state_changed.connect(_on_state)
	connection.reducer_failed.connect(func(_message: String): cancel(true))


func start(actor: NpcActor) -> void:
	cancel()
	if _connection.state != "connected" or not is_instance_valid(actor):
		return
	_actor = actor
	_spawn_id = actor.spawn_id
	_deadline = Time.get_ticks_msec() + TIMEOUT_MS
	_best_distance = INF
	_try_interact()


func cancel(stop := false) -> void:
	_actor = null
	_spawn_id = ""
	var was_moving := _moving
	_moving = false
	_best_distance = INF
	if stop and was_moving and _connection.state == "connected":
		_connection.stop_moving()


func _on_state(state: String, _message: String) -> void:
	if _spawn_id.is_empty() or state == "connected":
		return
	# The server stops a character whose connection left. The reservation waits for
	# the restored session instead of dropping a click the player already made.
	_moving = false
	_best_distance = INF


func _process(_delta: float) -> void:
	if _spawn_id.is_empty():
		return
	if Time.get_ticks_msec() >= _deadline:
		cancel(true)
		return
	_try_interact()


func _try_interact() -> void:
	if _connection.state != "connected":
		return
	var actor := _actor_node()
	if actor == null:
		# The presentation is rebuilding after a reconnect or chunk reload; the
		# reservation keeps waiting until its deadline instead of freezing the click.
		return
	for row: Dictionary in _connection.players:
		if str(row.identity) != _connection.local_identity:
			continue
		if int(row.health) <= 0:
			cancel(true)
			return
		var distance := Vector2(float(row.x), float(row.z)).distance_to(
			Vector2(actor.position.x, actor.position.z)
		)
		if distance <= INTERACTION_DISTANCE:
			var id := actor.spawn_id
			cancel(true)
			_connection.interact_npc(id)
			return
		_watch_progress(actor, distance)


func _actor_node() -> NpcActor:
	if is_instance_valid(_actor):
		return _actor
	if not _resolve.is_valid():
		return null
	var found: Variant = _resolve.call(_spawn_id)
	if found is NpcActor:
		_actor = found
		return _actor
	return null


func _watch_progress(actor: NpcActor, distance: float) -> void:
	var now := Time.get_ticks_msec()
	if distance < _best_distance - PROGRESS_EPSILON:
		_best_distance = distance
		_stall_at = now + STALL_MS
	if _moving and now < _stall_at:
		return
	# Either no live intent exists for this connection generation (first click or a
	# reconnect) or the character stopped closing distance (the request was lost).
	_moving = true
	_stall_at = now + STALL_MS
	_connection.move_to(actor.position.x, actor.position.z)
