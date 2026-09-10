class_name MoveDestination
extends Node
## Ground click-to-move reservation; walking stays an ordinary server intent.
##
## The account flow tears the world session down while its signed token
## refreshes, and the server stops a character whose connection left
## (`open_account` calls `stop_character`, which clears the controller). A click
## the player already made must re-issue its authoritative `move_to` once the
## restored session is live, so the character does not silently freeze mid-route
## every time the session is refreshed.

const TIMEOUT_MS := 90000
const ARRIVAL_DISTANCE := 0.75
var _connection: GameConnection
var _point := Vector3.ZERO
var _deadline := 0
var _issued := false
var _active := false


static func attach(parent: Node, connection: GameConnection) -> MoveDestination:
	var driver := MoveDestination.new()
	parent.add_child(driver)
	driver.configure(connection)
	return driver


func configure(connection: GameConnection) -> void:
	_connection = connection
	connection.connection_state_changed.connect(_on_state)


func is_active() -> bool:
	return _active


func start(point: Vector3) -> void:
	_active = true
	_point = point
	_deadline = Time.get_ticks_msec() + TIMEOUT_MS
	_issued = false
	# A click made while the session is rebuilding is issued by the restored
	# session instead of being dropped or sent into a dead generation.
	if _connection.state == "connected":
		_issue()


func cancel(stop := false) -> void:
	var was_active := _active
	_active = false
	_issued = false
	if stop and was_active and _connection.state == "connected":
		_connection.stop_moving()


func _on_state(state: String, _message: String) -> void:
	if not _active:
		return
	if state == "connected":
		# The server dropped the controller with the old connection; the same
		# destination has to be requested again for the restored session.
		_issue()
	else:
		_issued = false


func _process(_delta: float) -> void:
	if not _active:
		return
	if Time.get_ticks_msec() >= _deadline:
		cancel(true)
		return
	if _connection.state != "connected":
		return
	var row := _local_row()
	if not row.is_empty():
		if int(row.health) <= 0:
			# Death already stopped the authoritative character.
			cancel(false)
			return
		if (
			_issued
			and (
				Vector2(float(row.x), float(row.z)).distance_to(Vector2(_point.x, _point.z))
				<= ARRIVAL_DISTANCE
			)
		):
			# The server finished the walk; no extra intent belongs here.
			cancel(false)
			return
	if not _issued:
		_issue()


func _issue() -> void:
	_issued = true
	_connection.move_to(_point.x, _point.z)


func _local_row() -> Dictionary:
	for row: Dictionary in _connection.players:
		if str(row.identity) == _connection.local_identity:
			return row
	return {}
