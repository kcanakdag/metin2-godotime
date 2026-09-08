# gdlint: disable=max-public-methods
class_name GameConnection
extends Node
## Application boundary for SpacetimeDB. Gameplay only receives plain dictionaries.
## Never log identity tokens or package user:// files in a client distribution.
# One typed action facade covers account, movement, combat and inventory intents.

signal connection_state_changed(state: String, message: String)
signal players_changed(rows: Array)
signal obstacles_changed(rows: Array)
signal chat_changed(rows: Array)
signal world_info_changed(info: Dictionary)
signal reducer_failed(message: String)
signal reducer_completed(name: String, succeeded: bool, server_timestamp_us: int)
signal monsters_changed(rows: Array)
signal loot_changed(rows: Array)
signal inventory_changed(rows: Array)
signal item_drops_changed(rows: Array)
signal content_load_requested(info: Dictionary)
signal roster_changed(rows: Array)
signal account_changed(info: Dictionary)
signal lobby_ready
signal lobby_action_completed(action: String)
signal account_reconnect_requested
signal appearances_changed(rows: Array)
signal server_clock_changed(server_time_us: int)
signal progression_changed(rows: Array)
signal command_feedback_changed(rows: Array)
signal skills_changed(rows: Array)
signal combat_target_changed(info: Dictionary)
signal npc_interaction_changed(info: Dictionary)
signal npc_spawns_changed(rows: Array)

const BINDINGS_PATH := "res://spacetime_bindings/schema/module_game_client.gd"
const EXPECTED_PROTOCOL_VERSION := 18
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
	"item_drop",
	"account_character",
	"account_state",
	"player_appearance",
	"simulation_clock",
	"character_progression",
	"character_skill",
	"command_feedback",
	"combat_target_view",
	"npc_interaction",
	"npc_spawn",
]
const LOBBY_QUERIES := [
	"SELECT * FROM account_character",
	"SELECT * FROM account_state",
	"SELECT * FROM character_progression",
	"SELECT * FROM character_skill",
	"SELECT * FROM command_feedback",
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
	"SELECT * FROM player_appearance",
	"SELECT * FROM simulation_clock",
	"SELECT * FROM combat_target_view",
	"SELECT * FROM npc_interaction",
	"SELECT * FROM npc_spawn",
]

var local_identity := ""
var account_identity := ""
var characters: Array = []
var account_state: Dictionary = {}
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
var appearances: Array = []
var server_time_us := 0
var progression: Array = []
var skills: Array = []
var command_feedback: Array = []
var combat_target: Dictionary = {}
var npc_interaction: Dictionary = {}
var npc_spawns: Array = []

var _client: SpacetimeDBClient
var _session := 0
var _player_name := ""
var _profile := "default"
var _token_path := ""
var _connection_deadline := 0
var _pending_calls: Dictionary = {}
var _dirty_tables: Dictionary = {}
var _account_mode := false
var _auth_token := ""
var _world_subscription: SpacetimeDBSubscription


func connect_game(
	server_url: String, database_name: String, player_name: String, profile := "default"
) -> void:
	_account_mode = false
	_auth_token = ""
	_connect(server_url, database_name, player_name, profile)


func connect_account(
	server_url: String, database_name: String, token: String, profile := "default"
) -> void:
	_account_mode = true
	_auth_token = token
	_connect(server_url, database_name, "", profile)


func _connect(
	server_url: String, database_name: String, player_name: String, profile: String
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
	if _account_mode:
		options.token = _auth_token
	elif FileAccess.file_exists(_token_path):
		options.token = FileAccess.get_file_as_string(_token_path).strip_edges()
	_connection_deadline = Time.get_ticks_msec() + CONNECTION_TIMEOUT_MS
	_set_state("connecting", "Connecting to %s / %s…" % [endpoint, database])
	_client.connect_db(endpoint, database, options)


func disconnect_game() -> void:
	_retire_client()
	_clear_snapshots()
	_set_state("disconnected", "Disconnected.")


func reconnect_game() -> void:
	if _account_mode:
		account_reconnect_requested.emit()
	else:
		connect_game(endpoint, database, _player_name, _profile)


func create_character(slot: int, character_name: String, character_class := 0, sex := 0) -> void:
	if slot < 0 or slot >= 4:
		reducer_failed.emit("Choose one of the four character slots.")
		return
	if character_class not in [0, 1, 2, 3] or sex not in [0, 1]:
		reducer_failed.emit("Choose a valid character class and appearance.")
		return
	_call_lobby(
		"create_character",
		[slot, character_name, character_class, sex],
		[&"U8", &"String", &"U8", &"U8"]
	)


func select_character(character_id: String) -> void:
	if character_id.length() != 64 or not character_id.is_valid_hex_number(false):
		return
	_call_lobby("select_character", [character_id.hex_decode()], [&"__identity__"])


func enter_selected() -> void:
	if state != "lobby" or local_identity.is_empty():
		return
	_connection_deadline = Time.get_ticks_msec() + CONNECTION_TIMEOUT_MS
	_set_state("subscribing", "Loading your character's world…")
	_subscribe_world(_session)


func leave_world() -> void:
	if not _account_mode:
		disconnect_game()
		return
	if state == "connected":
		_set_state("leaving", "Returning to character selection…")
		_call_lobby("leave_world")


func uses_account() -> bool:
	return _account_mode


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


func select_combat_target(target_id: int, target_life_sequence: int) -> void:
	if target_id <= 0 or target_id > 0xFFFFFFFF:
		reducer_failed.emit("Choose a valid combat target.")
		return
	if target_life_sequence < 0 or target_life_sequence > 0xFFFFFFFF:
		reducer_failed.emit("The selected target generation is invalid.")
		return
	_call_reducer("select_combat_target", [target_id, target_life_sequence], [&"U32", &"U32"])


func interact_npc(spawn_id: String) -> void:
	_call_reducer(
		"interact_npc",
		[spawn_id, str(world_info.get("npc_catalog_hash", ""))],
		[&"String", &"String"]
	)


func close_npc_interaction(session_id: int) -> void:
	_call_reducer("close_npc_interaction", [session_id], [&"U64"])


func clear_combat_target() -> void:
	_call_reducer("clear_combat_target")


func pickup_loot(id: int) -> void:
	_call_reducer("pickup_loot", [id], [&"U64"])


func pickup_item_drop(id: int) -> void:
	_call_reducer("pickup_item_drop", [id], [&"U64"])


func move_item(id: int, cell: int) -> void:
	if _valid_inventory_cell(cell):
		_call_item_reducer("move_item", id, [cell], [&"U8"])


func equip_item(id: int) -> void:
	_call_item_reducer("equip_item", id)


func unequip_item(id: int, cell: int) -> void:
	if _valid_inventory_cell(cell):
		_call_item_reducer("unequip_item", id, [cell], [&"U8"])


func use_item(id: int) -> void:
	_call_item_reducer("use_item", id)


func _call_item_reducer(name: String, id: int, args: Array = [], types: Array = []) -> void:
	for item: Dictionary in own_inventory():
		if int(item.id) == id:
			_call_reducer(name, [id] + args + [int(item.revision)], [&"U64"] + types + [&"U32"])
			return
	reducer_failed.emit("That item is unavailable. Wait for the inventory update.")


func own_inventory() -> Array:
	return inventory.filter(func(row: Dictionary): return str(row.owner) == local_identity)


func appearance_for(character_id: String) -> Dictionary:
	for row: Dictionary in appearances:
		if str(row.character_id) == character_id:
			return row
	return {}


func progression_for(character_id: String) -> Dictionary:
	for row: Dictionary in progression:
		if str(row.get("character_id", "")) == character_id:
			return row
	return {}


func selected_progression() -> Dictionary:
	return progression_for(local_identity)


func monsters_for_definition(vnum: int) -> Array:
	return monsters.filter(func(row: Dictionary): return int(row.get("definition_vnum", 0)) == vnum)


func selected_combat_target() -> Dictionary:
	if _is_own_combat_target(combat_target):
		return combat_target
	return {}


func allocate_stat(character_id: String, stat_code: String) -> void:
	if not _is_lower_hex(character_id, 64):
		reducer_failed.emit("Choose a valid character before allocating a stat.")
		return
	if stat_code not in ["st", "ht", "dx", "iq"]:
		reducer_failed.emit("Choose STR, VIT, DEX, or INT.")
		return
	_call_reducer(
		"allocate_stat", [character_id.hex_decode(), stat_code], [&"__identity__", &"String"]
	)


func request_command_help(request_id: String) -> void:
	_call_command("request_command_help", request_id)


func admin_grant_progression_xp(request_id: String, amount_text: String) -> void:
	_call_command("admin_grant_progression_xp", request_id, amount_text)


func admin_raise_progression_level(request_id: String, target_text: String) -> void:
	_call_command("admin_raise_progression_level", request_id, target_text)


func _call_command(reducer_name: String, request_id: String, argument: String = "") -> void:
	if not _is_lower_hex(request_id, 32):
		reducer_failed.emit("Could not create a secure command request.")
		return
	if reducer_name == "request_command_help":
		_call_reducer(reducer_name, [request_id], [&"String"])
	else:
		_call_reducer(reducer_name, [request_id, argument], [&"String", &"String"])


func _is_lower_hex(value: String, length: int) -> bool:
	return (
		value.length() == length and value == value.to_lower() and value.is_valid_hex_number(false)
	)


func _valid_inventory_cell(cell: int) -> bool:
	# Reject before U8 encoding can wrap; the server independently checks footprint/ownership.
	if cell < 0 or cell >= 90:
		reducer_failed.emit("Choose a slot inside the inventory.")
		return false
	return true


func send_chat(message: String) -> void:
	if message.strip_edges().begins_with("/"):
		reducer_failed.emit("Use /help for private commands.")
		return
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
	account_identity = identity.hex_encode()
	if _account_mode:
		_set_state("subscribing", "Loading your characters…")
		var lobby := _client.subscribe(PackedStringArray(LOBBY_QUERIES))
		if lobby.error != OK:
			_fail("Could not load character selection.")
			return
		lobby.applied.connect(_on_lobby_applied.bind(session))
		return
	local_identity = account_identity
	_save_token(token)
	_set_state("subscribing", "Loading the shared development map…")
	_subscribe_world(session)


func _on_lobby_applied(session: int) -> void:
	if session != _session:
		return
	_dirty_tables["account_character"] = true
	_dirty_tables["account_state"] = true
	_dirty_tables["character_progression"] = true
	_dirty_tables["character_skill"] = true
	_dirty_tables["command_feedback"] = true
	_flush_snapshots()
	_set_state("opening", "Opening your account…")
	_call_lobby("open_account")


func _subscribe_world(session: int) -> void:
	_world_subscription = _client.subscribe(PackedStringArray(QUERIES))
	if _world_subscription.error != OK:
		_fail("Unable to subscribe to the world.")
		return
	_world_subscription.applied.connect(_on_subscription_applied.bind(session))


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
	if _account_mode:
		_call_reducer("enter_selected_character", [], [], true)
	else:
		_call_reducer("enter_world", [_player_name], [&"String"], true)


func _call_lobby(reducer_name: String, args: Array = [], types: Array = []) -> void:
	if state in ["lobby", "opening", "leaving"]:
		_call_reducer(reducer_name, args, types, false, true)


func _call_reducer(
	reducer_name: String, args: Array = [], types: Array = [], joining := false, lobby := false
) -> void:
	if not is_instance_valid(_client) or (state != "connected" and not joining and not lobby):
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
		"name": reducer_name, "started": Time.get_ticks_msec(), "joining": joining, "lobby": lobby
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
		reducer_completed.emit(str(pending.name), false, int(response.timestamp))
		if pending["joining"]:
			_fail(message)
		else:
			if pending.get("lobby", false):
				_connection_deadline = 0
				_set_state("lobby", message)
			reducer_failed.emit(message)
		return
	if outcome.value == ReducerOutcomeEnum.Options.internalError:
		reducer_completed.emit(str(pending.name), false, int(response.timestamp))
		_fail("The server reported an internal error. Check the server logs before reconnecting.")
		return
	reducer_completed.emit(str(pending.name), true, int(response.timestamp))
	if pending["joining"]:
		_connection_deadline = 0
		connected_at_msec = Time.get_ticks_msec()
		_set_state("connected", "Connected to %s." % world_info.get("map_name", database))
	elif pending.get("lobby", false):
		_on_lobby_result(str(pending.name), session)


func _on_lobby_result(action: String, session: int) -> void:
	if action == "open_account":
		_connection_deadline = 0
		_set_state("lobby", "Choose your character.")
		lobby_ready.emit()
	elif action == "leave_world":
		if is_instance_valid(_world_subscription) and _world_subscription.active:
			_world_subscription.end.connect(_on_world_left.bind(session), CONNECT_ONE_SHOT)
			if _world_subscription.unsubscribe() != OK:
				_fail("Could not leave the world. Please reconnect.")
		else:
			_on_world_left(session)
	lobby_action_completed.emit(action)


func _on_world_left(session: int) -> void:
	if session != _session:
		return
	_clear_world_snapshots()
	_connection_deadline = 0
	_set_state("lobby", "Choose your character.")
	lobby_ready.emit()


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
			"account_character":
				rows.sort_custom(
					func(a: Dictionary, b: Dictionary): return int(a.slot) < int(b.slot)
				)
				characters = rows
				roster_changed.emit(characters)
			"account_state":
				account_state = rows[0] if not rows.is_empty() else {}
				if _account_mode:
					var selected := str(account_state.get("selected_character", ""))
					local_identity = "" if selected == "0".repeat(64) else selected
				account_changed.emit(account_state)
			"character_progression":
				rows.sort_custom(
					func(a: Dictionary, b: Dictionary):
						return str(a.character_id) < str(b.character_id)
				)
				progression = rows
				progression_changed.emit(progression)
			"character_skill":
				skills = rows
				skills_changed.emit(skills)
			"command_feedback":
				rows.sort_custom(func(a: Dictionary, b: Dictionary): return int(a.id) < int(b.id))
				command_feedback = rows
				command_feedback_changed.emit(command_feedback)
			"npc_spawn":
				npc_spawns = rows
				npc_spawns_changed.emit(npc_spawns)
			"npc_interaction":
				npc_interaction = {}
				for row: Dictionary in rows:
					if _is_own_combat_target(row):
						npc_interaction = row
						break
				npc_interaction_changed.emit(npc_interaction)
			"combat_target_view":
				combat_target = {}
				for row: Dictionary in rows:
					if _is_own_combat_target(row):
						combat_target = row
						break
				combat_target_changed.emit(combat_target)
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
			"player_appearance":
				appearances = rows
				appearances_changed.emit(appearances)
			"simulation_clock":
				server_time_us = int(rows[0].last_tick) if not rows.is_empty() else 0
				server_clock_changed.emit(server_time_us)
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
						or (
							next_info.get("npc_catalog_hash", "")
							!= world_info.get("npc_catalog_hash", "")
						)
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


func _is_own_combat_target(row: Dictionary) -> bool:
	return (
		not account_identity.is_empty()
		and not local_identity.is_empty()
		and str(row.get("account", "")) == account_identity
		and str(row.get("character_id", "")) == local_identity
	)


func _on_disconnected(session: int) -> void:
	if session == _session:
		_fail("Connection closed. Check the server and reconnect.")


func _on_connection_error(_code: int, _reason: String, session: int) -> void:
	if session == _session:
		_fail("Could not connect to the game server. Please log in again or try shortly.")


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
	_world_subscription = null


func _clear_snapshots() -> void:
	local_identity = ""
	account_identity = ""
	characters = []
	account_state = {}
	progression = []
	skills = []
	skills_changed.emit(skills)
	command_feedback = []
	roster_changed.emit(characters)
	account_changed.emit(account_state)
	progression_changed.emit(progression)
	command_feedback_changed.emit(command_feedback)
	connected_at_msec = 0
	last_snapshot_msec = 0
	rx_messages = 0
	tx_messages = 0
	rx_bytes = 0
	tx_bytes = 0
	last_reducer_rtt_ms = 0
	_clear_world_snapshots()


func _clear_world_snapshots() -> void:
	players = []
	obstacles = []
	chat = []
	world_info = {}
	monsters = []
	loot = []
	inventory = []
	item_drops = []
	appearances = []
	combat_target = {}
	npc_interaction = {}
	npc_interaction_changed.emit(npc_interaction)
	npc_spawns = []
	npc_spawns_changed.emit(npc_spawns)
	server_time_us = 0
	inventory_changed.emit(inventory)
	item_drops_changed.emit(item_drops)
	appearances_changed.emit(appearances)
	combat_target_changed.emit(combat_target)
	server_clock_changed.emit(server_time_us)
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


func selected_skills() -> Array:
	return skills.filter(func(row): return str(row.get("character_id", "")) == local_identity)


func skill_revision(vnum: int) -> int:
	for row: Dictionary in selected_skills():
		if int(row.skill_vnum) == vnum:
			return int(row.revision)
	return 0


func learn_skill(vnum: int) -> void:
	if vnum < 1 or vnum > 255:
		return
	_call_reducer("learn_skill", [vnum, skill_revision(vnum)], [&"U16", &"U32"])


func cast_skill(vnum: int) -> void:
	if vnum < 1 or vnum > 255:
		return
	_call_reducer("cast_skill", [vnum, skill_revision(vnum)], [&"U16", &"U32"])


func admin_set_skill(request_id: String, argument: String) -> void:
	_call_command("admin_set_skill", request_id, argument)
