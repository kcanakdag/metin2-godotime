class_name NpcApproach
extends Node
## Click reservation follows authoritative position; movement remains ordinary intent.

const INTERACTION_DISTANCE := 4.5
const TIMEOUT_MS := 20000
var _actor: NpcActor
var _connection: GameConnection
var _deadline := 0
var _moving := false


func configure(connection: GameConnection) -> void:
	_connection = connection
	connection.connection_state_changed.connect(func(_state: String, _message: String): cancel())
	connection.reducer_failed.connect(func(_message: String): cancel(true))


func start(actor: NpcActor) -> void:
	cancel()
	_actor = actor
	_deadline = Time.get_ticks_msec() + TIMEOUT_MS
	if not _try_interact():
		_moving = true
		_connection.move_to(actor.position.x, actor.position.z)


func cancel(stop := false) -> void:
	_actor = null
	var was_moving := _moving
	_moving = false
	if stop and was_moving and _connection.state == "connected":
		_connection.stop_moving()


func _process(_delta: float) -> void:
	if _actor == null:
		return
	if not is_instance_valid(_actor) or Time.get_ticks_msec() >= _deadline:
		cancel(true)
		return
	_try_interact()


func _try_interact() -> bool:
	if not is_instance_valid(_actor) or _connection.state != "connected":
		cancel(true)
		return true
	for row: Dictionary in _connection.players:
		if str(row.identity) != _connection.local_identity:
			continue
		if int(row.health) <= 0:
			cancel(true)
			return true
		var distance := Vector2(float(row.x), float(row.z)).distance_to(
			Vector2(_actor.position.x, _actor.position.z)
		)
		if distance <= INTERACTION_DISTANCE:
			var id := _actor.spawn_id
			cancel(true)
			_connection.interact_npc(id)
			return true
	return false
