class_name GameConnection
extends Node
## Application boundary for SpacetimeDB. Gameplay only receives plain dictionaries.
## Never log identity tokens or package user:// files in a client distribution.

signal connection_state_changed(state: String, message: String)
signal players_changed(rows: Array)
signal obstacles_changed(rows: Array)
signal chat_changed(rows: Array)
signal world_info_changed(info: Dictionary)
signal reducer_failed(message: String)
signal monsters_changed(rows: Array)
signal loot_changed(rows: Array)
signal inventory_changed(rows: Array)
signal item_drops_changed(rows: Array)
signal content_load_requested(info: Dictionary)

const BINDINGS_PATH := "res://spacetime_bindings/schema/module_game_client.gd"
const EXPECTED_PROTOCOL_VERSION := 2
const CONNECTION_TIMEOUT_MS := 12000
const REDUCER_TIMEOUT_MS := 8000
const TABLES := [
	"player",
	"obstacle",
	"world_info",
	"chat_message",
	"monster",
	"loot",
	"inventory_item",
	"item_drop"
]
const QUERIES := [
	"SELECT * FROM player WHERE online = true",
	"SELECT * FROM obstacle",
	"SELECT * FROM world_info",
	"SELECT * FROM chat_message",
	"SELECT * FROM monster",
	"SELECT * FROM loot",
	"SELECT * FROM inventory_item",
	"SELECT * FROM item_drop",
]

var local_identity := ""
var state := "disconnected"
var state_message := "Disconnected."
var endpoint := ""
var database := ""
var connected_at_msec := 0
var last_snapshot_msec := 0
var rx_messages := 0
var tx_messages := 0
var rx_bytes := 0
var tx_bytes := 0
var last_reducer_rtt_ms := 0
var players: Array = []
var obstacles: Array = []
var chat: Array = []
var world_info: Dictionary = {}
var monsters: Array = []
var loot: Array = []
var inventory: Array = []
var item_drops: Array = []
var require_content := false

var _client: SpacetimeDBClient
var _session := 0
var _player_name := ""
var _profile := "default"
var _token_path := ""
var _connection_deadline := 0
var _pending_calls: Dictionary = {}
var _dirty_tables: Dictionary = {}


func connect_game(
	server_url: String, database_name: String, player_name: String, profile := "default"
) -> void:
	_retire_client()
	_clear_snapshots()
	endpoint = server_url.strip_edges().trim_suffix("/")
	database = database_name.strip_edges().to_lower()
	_player_name = player_name.strip_edges()
	_profile = _safe_profile(profile)
	var host_pattern := RegEx.create_from_string("^https?://[^/?#@\\s]+$")
	if host_pattern.search(endpoint) == null:
		_set_state("error", "Use a server address such as http://127.0.0.1:3210 or https://host.")
		return
	if database.is_empty() or "/" in database or "?" in database or "#" in database:
		_set_state("error", "Enter a valid SpacetimeDB database name.")
		return
	if not ResourceLoader.exists(BINDINGS_PATH):
		_set_state(
			"error", "Client bindings are missing. Publish the server and run make bindings."
		)
		return
	_token_path = (
		"user://identities/%s_%s.token"
		% [(endpoint + "/" + database).sha256_text().left(16), _profile]
	)
	var client_script: Script = load(BINDINGS_PATH)
	_client = client_script.new() as SpacetimeDBClient
	if _client == null:
		_set_state(
			"error", "Client bindings failed to load. Run make bindings and check the build."
		)
		return
	var session := _session
	_client.name = "SpacetimeSession%d" % session
	_client.connected.connect(_on_connected.bind(session))
	_client.disconnected.connect(_on_disconnected.bind(session))
	_client.connection_error.connect(_on_connection_error.bind(session))
	_client.protocol_error.connect(_on_protocol_error.bind(session))
	_client.subscription_error.connect(_on_subscription_error.bind(session))
	_client.row_inserted.connect(_on_row_changed.bind(session))
	_client.row_deleted.connect(_on_row_changed.bind(session))
	_client.row_updated.connect(_on_row_updated.bind(session))
	_client.transaction_update_received.connect(_on_transaction.bind(session))
	add_child(_client)
	var options := SpacetimeDBConnectionOptions.new()
	options.threading = false
	options.one_time_token = true
	options.save_token = false
	options.debug_mode = false
	options.confirmed_reads = false
	options.compression = SpacetimeDBConnection.CompressionPreference.NONE
	if FileAccess.file_exists(_token_path):
		options.token = FileAccess.get_file_as_string(_token_path).strip_edges()
	_connection_deadline = Time.get_ticks_msec() + CONNECTION_TIMEOUT_MS
	_set_state("connecting", "Connecting to %s / %s…" % [endpoint, database])
	_client.connect_db(endpoint, database, options)


func disconnect_game() -> void:
	_retire_client()
	_clear_snapshots()
	_set_state("disconnected", "Disconnected.")


func reconnect_game() -> void:
	connect_game(endpoint, database, _player_name, _profile)


func reset_identity() -> void:
	## Explicit user action: the next connection creates a new character identity.
	disconnect_game()
	if not _token_path.is_empty() and FileAccess.file_exists(_token_path):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(_token_path))
	_set_state("disconnected", "Saved identity reset. Connect to create a new character.")


func set_move_input(x: float, z: float) -> void:
	_call_reducer("set_move_input", [x, z], [&"F32", &"F32"])


func move_to(x: float, z: float) -> void:
	_call_reducer("move_to", [x, z], [&"F32", &"F32"])


func stop_moving() -> void:
	_call_reducer("stop_moving")


func perform_attack() -> void:
	_call_reducer("perform_attack")


func pickup_loot(id: int) -> void:
	_call_reducer("pickup_loot", [id], [&"U64"])


func pickup_item_drop(id: int) -> void:
	_call_reducer("pickup_item_drop", [id], [&"U64"])


func move_item(id: int, cell: int) -> void:
	if _valid_inventory_cell(cell):
		_call_reducer("move_item", [id, cell], [&"U64", &"U8"])


func equip_item(id: int) -> void:
	_call_reducer("equip_item", [id], [&"U64"])


func unequip_item(id: int, cell: int) -> void:
	if _valid_inventory_cell(cell):
		_call_reducer("unequip_item", [id, cell], [&"U64", &"U8"])


func use_item(id: int) -> void:
	_call_reducer("use_item", [id], [&"U64"])


func own_inventory() -> Array:
	return inventory.filter(func(row: Dictionary): return str(row.owner) == local_identity)


func _valid_inventory_cell(cell: int) -> bool:
	# Reject before U8 encoding can wrap; the server independently checks footprint/ownership.
	if cell < 0 or cell >= 90:
		reducer_failed.emit("Choose a slot inside the inventory.")
		return false
	return true


func send_chat(message: String) -> void:
	_call_reducer("send_chat", [message], [&"String"])


func _process(_delta: float) -> void:
	var now := Time.get_ticks_msec()
	if _connection_deadline > 0 and now >= _connection_deadline:
		_fail("Connection timed out. Check the server address, database publication, and firewall.")
		return
	for request_id: int in _pending_calls.keys():
		if now - int(_pending_calls[request_id]["started"]) >= REDUCER_TIMEOUT_MS:
			_fail("The server stopped acknowledging requests. Reconnect before continuing.")
			return
	if is_instance_valid(_client) and is_instance_valid(_client._connection):
		var transport := _client._connection
		rx_messages = transport.get_received_packets()
		tx_messages = transport.get_sent_packets()
		rx_bytes = transport._total_bytes_received
		tx_bytes = transport._total_bytes_send


func _on_connected(identity: PackedByteArray, token: String, session: int) -> void:
	if session != _session:
		return
	local_identity = identity.hex_encode()
	_save_token(token)
	_set_state("subscribing", "Loading the shared development map…")
	var subscription := _client.subscribe(PackedStringArray(QUERIES))
	if subscription.error != OK:
		_fail("Unable to subscribe to the map: %s" % error_string(subscription.error))
		return
	subscription.applied.connect(_on_subscription_applied.bind(session))


func _on_subscription_applied(session: int) -> void:
	if session != _session:
		return
	for table: String in TABLES:
		_dirty_tables[table] = true
	_flush_snapshots()
	if world_info.is_empty():
		_fail(
			"The database has no world configuration. Publish and initialize the matching server."
		)
		return
	if int(world_info.get("protocol_version", -1)) != EXPECTED_PROTOCOL_VERSION:
		_fail("Client/server protocol mismatch. Install a client built for this server.")
		return
	if require_content:
		_connection_deadline = Time.get_ticks_msec() + 120000
		_set_state("loading", "Loading the starting area…")
		content_load_requested.emit(world_info)
	else:
		enter_loaded_world()


func enter_loaded_world() -> void:
	if state not in ["subscribing", "loading"]:
		return
	_set_state("joining", "Entering %s…" % world_info.get("map_name", "the map"))
	_call_reducer("enter_world", [_player_name], [&"String"], true)


func _call_reducer(
	reducer_name: String, args: Array = [], types: Array = [], joining := false
) -> void:
	if not is_instance_valid(_client) or (state != "connected" and not joining):
		return
	var call := _client.call_reducer(reducer_name, args, types)
	if call.error != OK:
		var message := "%s could not be sent: %s" % [reducer_name, error_string(call.error)]
		if joining:
			_fail(message)
		else:
			reducer_failed.emit(message)
		return
	_pending_calls[call.request_id] = {
		"name": reducer_name, "started": Time.get_ticks_msec(), "joining": joining
	}
	call.response.connect(_on_reducer_response.bind(_session))


func _on_reducer_response(response: ReducerResultMessage, session: int) -> void:
	if session != _session or not _pending_calls.has(response.request_id):
		return
	var pending: Dictionary = _pending_calls[response.request_id]
	_pending_calls.erase(response.request_id)
	last_reducer_rtt_ms = Time.get_ticks_msec() - int(pending["started"])
	var outcome := response.reducer_result
	if outcome.value == ReducerOutcomeEnum.Options.err:
		var message: String = outcome.get_err()
		if pending["joining"]:
			_fail(message)
		else:
			reducer_failed.emit(message)
		return
	if outcome.value == ReducerOutcomeEnum.Options.internalError:
		_fail("The server reported an internal error. Check the server logs before reconnecting.")
		return
	if pending["joining"]:
		_connection_deadline = 0
		connected_at_msec = Time.get_ticks_msec()
		_set_state("connected", "Connected to %s." % world_info.get("map_name", database))


func _on_row_changed(table_name: String, _row: Resource, session: int) -> void:
	if session == _session:
		_dirty_tables[table_name] = true


func _on_row_updated(
	table_name: String, _old_row: Resource, _new_row: Resource, session: int
) -> void:
	if session == _session:
		_dirty_tables[table_name] = true


func _on_transaction(_update: Resource, session: int) -> void:
	if session == _session:
		_flush_snapshots()


func _flush_snapshots() -> void:
	if not is_instance_valid(_client):
		return
	var local_db := _client.get_local_database()
	for table_name: String in _dirty_tables:
		if table_name not in TABLES:
			continue
		var rows: Array = []
		for row: Resource in local_db.get_all_rows(table_name):
			var values: Dictionary = {}
			for field: String in row.get("BSATN_TYPES"):
				var value: Variant = row.get(field)
				values[field] = value.hex_encode() if value is PackedByteArray else value
			rows.append(values)
		match table_name:
			"inventory_item":
				inventory = rows
				inventory_changed.emit(own_inventory())
			"item_drop":
				item_drops = rows
				item_drops_changed.emit(item_drops)
			"monster":
				monsters = rows
				monsters_changed.emit(monsters)
			"loot":
				loot = rows
				loot_changed.emit(loot)
			"player":
				players = rows
				players_changed.emit(players)
			"obstacle":
				obstacles = rows
				obstacles_changed.emit(obstacles)
			"chat_message":
				rows.sort_custom(func(a: Dictionary, b: Dictionary): return a["id"] < b["id"])
				chat = rows
				chat_changed.emit(chat)
			"world_info":
				var next_info: Dictionary = rows[0] if not rows.is_empty() else {}
				if (
					require_content
					and state in ["loading", "joining", "connected"]
					and (
						next_info.get("content_hash", "") != world_info.get("content_hash", "")
						or next_info.get("map_id", "") != world_info.get("map_id", "")
					)
				):
					_fail(
						"The map has been updated. Refresh the page or restart the client to update."
					)
					return
				world_info = next_info
				world_info_changed.emit(world_info)
	if not _dirty_tables.is_empty():
		last_snapshot_msec = Time.get_ticks_msec()
	_dirty_tables.clear()


func _on_disconnected(session: int) -> void:
	if session == _session:
		_fail("Connection closed. Check the server and reconnect.")


func _on_connection_error(_code: int, _reason: String, session: int) -> void:
	if session == _session:
		_fail(
			(
				"Connection failed. Check the address, database, and server version. "
				+ "If the server was reset, use Reset identity and reconnect."
			)
		)


func _on_protocol_error(_message: String, session: int) -> void:
	if session == _session:
		_fail("Could not decode server data. Update the client and regenerate matching bindings.")


func _on_subscription_error(message: String, session: int) -> void:
	if session == _session:
		_fail("Map subscription failed: %s. Check the client/server schema." % message)


func _fail(message: String) -> void:
	_retire_client()
	_clear_snapshots()
	_set_state("error", message)


func _retire_client() -> void:
	_session += 1
	_connection_deadline = 0
	_pending_calls.clear()
	_dirty_tables.clear()
	if is_instance_valid(_client):
		# The SDK temporarily disables the OS close button while closing a socket.
		# We retire that socket immediately, so its later reset would never execute.
		var scene_tree := get_tree() if is_inside_tree() else null
		var previous_quit_policy := scene_tree.auto_accept_quit if scene_tree else true
		if is_instance_valid(_client._connection):
			_client._connection.disconnect_from_server()
		_client.queue_free()
		if scene_tree:
			scene_tree.auto_accept_quit = previous_quit_policy
	_client = null


func _clear_snapshots() -> void:
	local_identity = ""
	connected_at_msec = 0
	last_snapshot_msec = 0
	rx_messages = 0
	tx_messages = 0
	rx_bytes = 0
	tx_bytes = 0
	last_reducer_rtt_ms = 0
	players = []
	obstacles = []
	chat = []
	world_info = {}
	monsters = []
	loot = []
	inventory = []
	item_drops = []
	inventory_changed.emit(inventory)
	item_drops_changed.emit(item_drops)
	monsters_changed.emit(monsters)
	loot_changed.emit(loot)
	players_changed.emit(players)
	obstacles_changed.emit(obstacles)
	chat_changed.emit(chat)
	world_info_changed.emit(world_info)


func _set_state(value: String, message: String) -> void:
	state = value
	state_message = message
	connection_state_changed.emit(value, message)


func _save_token(token: String) -> void:
	var directory := ProjectSettings.globalize_path("user://identities")
	if DirAccess.make_dir_recursive_absolute(directory) != OK:
		reducer_failed.emit(
			"Could not save this identity. Reconnecting may create a new character."
		)
		return
	var file := FileAccess.open(_token_path, FileAccess.WRITE)
	if file == null:
		reducer_failed.emit(
			"Could not save this identity. Reconnecting may create a new character."
		)
		return
	file.store_string(token)
	file.close()
	if OS.get_name() not in ["Windows", "Web"]:
		FileAccess.set_unix_permissions(
			_token_path, FileAccess.UNIX_READ_OWNER | FileAccess.UNIX_WRITE_OWNER
		)


func _safe_profile(profile: String) -> String:
	var safe := ""
	for character: String in profile.to_lower():
		if character in "abcdefghijklmnopqrstuvwxyz0123456789_-":
			safe += character
	return safe.left(40) if not safe.is_empty() else "default"


func _exit_tree() -> void:
	_retire_client()
