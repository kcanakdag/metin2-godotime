extends "res://tests/multiplayer_smoke.gd"
## Real subscriptions and validated intents. Fixture secrets never enter reports.

var _tokens: Array = []
var _name_suffix := ""


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var config_path := ""
	for i in range(args.size() - 1):
		if args[i] == "--account-config":
			config_path = args[i + 1]
	var config: Variant = JSON.parse_string(FileAccess.get_file_as_string(config_path))
	if not config is Dictionary or not config.get("tokens") is Array:
		printerr("Account smoke requires a private --account-config JSON fixture.")
		quit(1)
		return
	_server = str(config.get("server", _server))
	_database = str(config.get("database", _database))
	_report_path = str(config.get("report", "user://account-smoke.json"))
	_tokens = config.tokens
	_name_suffix = Crypto.new().generate_random_bytes(6).hex_encode()
	if _tokens.size() != 2 or str(_tokens[0]).is_empty() or str(_tokens[1]).is_empty():
		printerr("Account smoke requires two signed account credentials.")
		quit(1)
		return
	call_deferred("_run")


func _run() -> void:
	var first := _make_client()
	var second := _make_client()
	if not await _create_rosters(first, second):
		_finish()
		return
	var first_id := str(first.characters[0].character_id)
	var alternative_id := str(first.characters[1].character_id)
	var second_id := str(second.characters[0].character_id)
	_check(
		"characters_have_separate_identity",
		first_id != first.account_identity and second_id != second.account_identity
	)
	_check("rosters_are_private", _private_roster(first, 4) and _private_roster(second, 1))
	_check("account_state_is_private", _private_state(first) and _private_state(second))
	_check("inventory_access_is_private", _private_access(first, 4) and _private_access(second, 1))
	_check("warrior_male_empire_one", first.characters.all(_valid_warrior))
	await _raw_rejection(
		first, "create_character", [4, "Outside"], [&"U8", &"String"], "fifth_slot_rejected", "slot"
	)
	await _raw_rejection(
		first,
		"create_character",
		[0, "Occupied"],
		[&"U8", &"String"],
		"occupied_slot_rejected",
		"occupied"
	)
	await _raw_rejection(
		second,
		"create_character",
		[1, "ac0_%s" % _name_suffix],
		[&"U8", &"String"],
		"case_insensitive_name_rejected",
		"taken"
	)
	await _raw_rejection(
		second,
		"create_character",
		[1, "bad name"],
		[&"U8", &"String"],
		"invalid_name_rejected",
		"letters"
	)
	await _raw_rejection(
		second,
		"select_character",
		[first_id.hex_decode()],
		[&"__identity__"],
		"other_account_character_rejected",
		"belong"
	)
	await _raw_rejection(
		first, "set_move_input", [1.0, 0.0], [&"F32", &"F32"], "lobby_cannot_move", "Enter"
	)
	first.select_character(first_id)
	if not _check(
		"selected_character_replicates",
		await _wait_until(func(): return first.local_identity == first_id)
	):
		_finish()
		return
	first.enter_selected()
	second.enter_selected()
	if not _check(
		"both_enter_selected_world",
		await _wait_until(
			func(): return first.state == "connected" and second.state == "connected", 20.0
		)
	):
		print(
			"ACCOUNT_ENTRY_STATE ",
			JSON.stringify(
				[
					{"state": first.state, "message": first.state_message},
					{"state": second.state, "message": second.state_message}
				]
			)
		)
		_finish()
		return
	_check(
		"selected_identity_is_character",
		first.local_identity == first_id and second.local_identity == second_id
	)
	_check(
		"mutual_subscribed_presence",
		await _wait_until(_mutual_presence.bind(first, second, first_id, second_id))
	)
	if not _check(
		"owned_inventory_subscribes",
		await _wait_until(
			func(): return first.inventory.size() == 8 and second.inventory.size() == 2
		)
	):
		_finish()
		return
	_check(
		"inventory_server_read_privacy", _private_inventory(first) and _private_inventory(second)
	)
	var sword: Dictionary = _owned_sword(first, first_id)
	if not _check("selected_starter_sword", not sword.is_empty()):
		_finish()
		return
	await _raw_rejection(
		second, "equip_item", [int(sword.id)], [&"U64"], "other_account_item_rejected", "another"
	)
	first.equip_item(int(sword.id))
	_check(
		"equipping_changes_owned_character",
		await _wait_until(func(): return bool(_owned_sword(first, first_id).get("equipped", false)))
	)
	await _movement(first, second, first_id, 1.0, "first")
	await _movement(second, first, second_id, -1.0, "second")
	await _raw_rejection(
		first,
		"set_move_input",
		[2.0, 0.0],
		[&"F32", &"F32"],
		"invalid_movement_rejected",
		"between"
	)
	var duplicate := _make_client()
	var before := _errors.size()
	duplicate.connect_account(_server, _database, str(_tokens[0]), "account-smoke-duplicate")
	_check(
		"duplicate_session_rejected",
		await _wait_until(
			func(): return _errors.size() > before and "another connection" in _errors[-1]
		)
	)
	duplicate.disconnect_game()
	await _movement(first, second, first_id, 1.0, "original_after_duplicate")
	var saved_player := _player(second, first_id).duplicate(true)
	var saved_inventory := first.inventory.duplicate(true)
	first.leave_world()
	_check("leave_returns_lobby", await _wait_until(func(): return first.state == "lobby"))
	_check(
		"leave_removes_presence",
		await _wait_until(func(): return _player(second, first_id).is_empty())
	)
	await _raw_rejection(first, "perform_attack", [], [], "lobby_cannot_attack", "Enter")
	first.select_character(alternative_id)
	_check(
		"switch_selection_replicates",
		await _wait_until(func(): return first.local_identity == alternative_id)
	)
	first.enter_selected()
	_check(
		"alternative_character_enters",
		await _wait_until(
			func():
				return first.state == "connected" and not _player(second, alternative_id).is_empty(),
			20.0
		)
	)
	_check("switch_keeps_old_character_offline", _player(second, first_id).is_empty())
	_check(
		"equipment_is_per_character",
		not bool(_owned_sword(first, alternative_id).get("equipped", true))
	)
	await _raw_rejection(
		first,
		"equip_item",
		[int(sword.id)],
		[&"U64"],
		"inactive_character_item_rejected",
		"another"
	)
	first.leave_world()
	_check("alternative_leaves", await _wait_until(func(): return first.state == "lobby"))
	first.select_character(first_id)
	_check(
		"original_reselected", await _wait_until(func(): return first.local_identity == first_id)
	)
	first.enter_selected()
	_check(
		"original_returns",
		await _wait_until(
			func(): return first.state == "connected" and not _player(second, first_id).is_empty(),
			20.0
		)
	)
	_check(
		"switch_preserves_character_state",
		_same_character_state(saved_player, _player(second, first_id))
	)
	_check(
		"switch_preserves_inventory",
		await _wait_until(func(): return _same_inventory(saved_inventory, first.inventory))
	)
	first.disconnect_game()
	_check(
		"disconnect_removes_presence",
		await _wait_until(func(): return _player(second, first_id).is_empty())
	)
	first.connect_account(_server, _database, str(_tokens[0]), "account-smoke-reconnect")
	_check(
		"account_reconnects_to_lobby",
		await _wait_until(func(): return first.state == "lobby", 20.0)
	)
	_check("reconnect_preserves_selection", first.local_identity == first_id)
	_check("reconnect_preserves_roster_privacy", _private_roster(first, 4))
	_check(
		"reconnect_preserves_access_privacy",
		await _subscribe_access(first, "reconnect") and _private_access(first, 4)
	)
	first.enter_selected()
	_check(
		"reconnect_enters_same_character",
		await _wait_until(
			func(): return first.state == "connected" and not _player(second, first_id).is_empty(),
			20.0
		)
	)
	_check(
		"reconnect_preserves_character_state",
		_same_character_state(saved_player, _player(second, first_id))
	)
	_check(
		"reconnect_preserves_inventory_without_duplicate_starters",
		await _wait_until(func(): return _same_inventory(saved_inventory, first.inventory))
	)
	second.disconnect_game()
	_check(
		"other_account_disconnect_removes_presence",
		await _wait_until(func(): return _player(first, second_id).is_empty())
	)
	_tokens.clear()
	_finish()


func _create_rosters(first: GameConnection, second: GameConnection) -> bool:
	first.connect_account(_server, _database, str(_tokens[0]), "account-smoke-a")
	second.connect_account(_server, _database, str(_tokens[1]), "account-smoke-b")
	if not _check(
		"two_authenticated_lobbies",
		await _wait_until(func(): return first.state == "lobby" and second.state == "lobby", 20.0)
	):
		return false
	_check("independent_accounts", first.account_identity != second.account_identity)
	_check("fresh_empty_rosters", first.characters.is_empty() and second.characters.is_empty())
	if not await _subscribe_access(first, "first") or not await _subscribe_access(second, "second"):
		return false
	for slot in range(4):
		first.create_character(slot, "Ac%d_%s" % [slot, _name_suffix])
		if not _check(
			"create_slot_%d" % slot,
			await _wait_until(func(): return first.characters.size() == slot + 1)
		):
			return false
	second.create_character(0, "Bc_%s" % _name_suffix)
	if not _check(
		"second_account_character", await _wait_until(func(): return second.characters.size() == 1)
	):
		return false
	return true


func _subscribe_access(client: GameConnection, label: String) -> bool:
	var subscription := client._client.subscribe(
		PackedStringArray(["SELECT * FROM inventory_access"])
	)
	if subscription.error != OK:
		return _check(label + "_access_subscription", false)
	var observed := {"applied": false}
	subscription.applied.connect(func(): observed.applied = true)
	return _check(
		label + "_access_subscription", await _wait_until(func(): return observed.applied)
	)


func _raw_rejection(
	client: GameConnection,
	reducer: String,
	args: Array,
	types: Array,
	label: String,
	reason: String
) -> void:
	var observed := {"done": false, "rejected": false}
	var call := client._client.call_reducer(reducer, args, types)
	if call.error != OK:
		_check(label, false)
		return
	call.response.connect(
		func(response: ReducerResultMessage):
			observed.done = true
			observed.rejected = (
				response.reducer_result.value == ReducerOutcomeEnum.Options.err
				and reason in response.reducer_result.get_err()
			)
	)
	_check(label, await _wait_until(func(): return observed.done) and observed.rejected)


func _movement(
	actor: GameConnection,
	observer: GameConnection,
	identity: String,
	direction: float,
	label: String
) -> void:
	var start := _position(_player(observer, identity))
	actor.set_move_input(direction, 0.0)
	await create_timer(0.3).timeout
	actor.stop_moving()
	_check(
		label + "_movement_replicates",
		await _wait_until(
			func(): return _position(_player(observer, identity)).distance_to(start) > 0.2
		)
	)
	await create_timer(0.2).timeout


func _mutual_presence(
	first: GameConnection, second: GameConnection, first_id: String, second_id: String
) -> bool:
	return not _player(first, second_id).is_empty() and not _player(second, first_id).is_empty()


func _valid_warrior(row: Dictionary) -> bool:
	return row.empire == 1 and row.character_class == 0 and row.sex == 0


func _private_roster(client: GameConnection, expected_count: int) -> bool:
	var rows := client._client.get_local_database().get_all_rows("account_character")
	return (
		rows.size() == expected_count
		and rows.all(
			func(row: Resource): return row.account.hex_encode() == client.account_identity
		)
	)


func _private_state(client: GameConnection) -> bool:
	var rows := client._client.get_local_database().get_all_rows("account_state")
	return rows.size() == 1 and rows[0].account.hex_encode() == client.account_identity


func _private_access(client: GameConnection, expected_count: int) -> bool:
	var rows := client._client.get_local_database().get_all_rows("inventory_access")
	var owned := client.characters.map(func(row: Dictionary): return str(row.character_id))
	if rows.size() != expected_count:
		return false
	for row: Resource in rows:
		if row.account.hex_encode() != client.account_identity:
			return false
		if row.character_id.hex_encode() not in owned:
			return false
	return true


func _private_inventory(client: GameConnection) -> bool:
	var owned := client.characters.map(func(row: Dictionary): return str(row.character_id))
	var rows := client._client.get_local_database().get_all_rows("inventory_item")
	if rows.is_empty():
		return false
	for row: Resource in rows:
		if row.owner.hex_encode() not in owned:
			return false
		if row.account.hex_encode() != client.account_identity:
			return false
	return true


func _owned_sword(client: GameConnection, identity: String) -> Dictionary:
	for row: Dictionary in client.inventory:
		if str(row.owner) == identity and int(row.vnum) == 10:
			return row
	return {}


func _same_character_state(first: Dictionary, second: Dictionary) -> bool:
	for field in ["identity", "name", "x", "y", "z", "health", "max_health", "gold"]:
		if first.get(field) != second.get(field):
			return false
	return true


func _same_inventory(first: Array, second: Array) -> bool:
	var a := first.duplicate(true)
	var b := second.duplicate(true)
	a.sort_custom(func(left: Dictionary, right: Dictionary): return int(left.id) < int(right.id))
	b.sort_custom(func(left: Dictionary, right: Dictionary): return int(left.id) < int(right.id))
	return a == b
