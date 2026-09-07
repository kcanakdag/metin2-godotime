extends "res://tests/multiplayer_smoke.gd"
## Prove source non-party EXP sharing with two authenticated contributors.

var _tokens: Array = []


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var config_path := ""
	for i in range(args.size() - 1):
		if args[i] == "--progression-config":
			config_path = args[i + 1]
	var config: Variant = JSON.parse_string(FileAccess.get_file_as_string(config_path))
	if not config is Dictionary:
		printerr("Shared progression smoke requires a private config fixture.")
		quit(1)
		return
	_server = str(config.get("server", _server))
	_database = str(config.get("database", _database))
	_report_path = str(config.get("report", "user://progression-shared.json"))
	_tokens = config.get("tokens", [])
	if _tokens.size() != 2 or _tokens.any(func(value: Variant): return str(value).is_empty()):
		printerr("Shared progression smoke config is invalid.")
		quit(1)
		return
	call_deferred("_run")


func _run() -> void:
	var first := _make_client()
	var second := _make_client()
	first.connect_account(_server, _database, str(_tokens[0]), "progression-shared-a")
	second.connect_account(_server, _database, str(_tokens[1]), "progression-shared-b")
	if not _check(
		"shared_authenticated_lobbies",
		await _wait_until(func(): return first.state == "lobby" and second.state == "lobby", 20.0)
	):
		_finish()
		return
	# Slot 0 receives the base account smoke's ordinary +15 reward and slot 1 is
	# reserved for the segmented level-up proof. Keep shared attribution isolated.
	var first_id := await _select_slot(first, 2)
	var second_id := await _select_slot(second, 0)
	if first_id.is_empty() or second_id.is_empty():
		_finish()
		return
	first.enter_selected()
	second.enter_selected()
	if not _check(
		"shared_characters_enter",
		await _wait_until(func(): return first.state == "connected" and second.state == "connected")
	):
		_finish()
		return
	if not await _prepare_contributors(first, second, first_id, second_id):
		_finish()
		return
	if not await _execute_shared_kills(first, second, first_id, second_id):
		_finish()
		return
	first.disconnect_game()
	second.disconnect_game()
	_tokens.clear()
	_finish()


func _execute_shared_kills(
	first: GameConnection, second: GameConnection, first_id: String, second_id: String
) -> bool:
	var first_before := int(first.progression_for(first_id).experience)
	var second_before := int(second.progression_for(second_id).experience)
	if not _check("shared_uses_untouched_progression", first_before == 0 and second_before == 0):
		return false
	if not await _execute_70_35_life(first, second, first_id, second_id):
		return false
	if not await _reconnect_first(first, second, first_id, first_before + 11):
		return false
	if not await _prepare_fresh_life(first, second, first_id, second_id):
		return false
	if not await _unequip_sword(first, first_id):
		return false
	return await _execute_75_35_life(first, second, first_id, second_id)


func _execute_70_35_life(
	first: GameConnection, second: GameConnection, first_id: String, second_id: String
) -> bool:
	var first_before := int(first.progression_for(first_id).experience)
	var second_before := int(second.progression_for(second_id).experience)
	if not await _shared_attack(first, second, 65, "shared_first_registered_35"):
		return false
	if not await _shared_attack(second, first, 30, "shared_second_registered_35"):
		return false
	if not await _shared_attack(first, second, 0, "shared_overkill_registered_35"):
		return false
	if not _check(
		"shared_70_35_float32_split",
		await _wait_until(
			func():
				return (
					int(first.progression_for(first_id).experience) == first_before + 11
					and int(second.progression_for(second_id).experience) == second_before + 4
				),
			5.0
		)
	):
		return false
	return _check(
		"shared_first_life_progression_remains_owner_private",
		first.progression_for(second_id).is_empty() and second.progression_for(first_id).is_empty()
	)


func _execute_75_35_life(
	first: GameConnection, second: GameConnection, first_id: String, second_id: String
) -> bool:
	var first_before := int(first.progression_for(first_id).experience)
	var second_before := int(second.progression_for(second_id).experience)
	for expected_health in [75, 50, 25]:
		if not await _shared_attack(
			first, second, expected_health, "shared_first_unarmed_reaches_%d" % expected_health
		):
			return false
	if not await _shared_attack(second, first, 0, "shared_second_sword_overkill_registered_35"):
		return false
	var split_valid := _check(
		"shared_75_35_float32_split",
		await _wait_until(
			func():
				return (
					int(first.progression_for(first_id).experience) == first_before + 11
					and int(second.progression_for(second_id).experience) == second_before + 3
				),
			5.0
		)
	)
	_check(
		"shared_old_life_credit_is_not_reused",
		(
			int(first.progression_for(first_id).experience) == first_before + 11
			and int(second.progression_for(second_id).experience) == second_before + 3
		)
	)
	_check(
		"shared_second_life_progression_remains_owner_private",
		first.progression_for(second_id).is_empty() and second.progression_for(first_id).is_empty()
	)
	return split_valid


func _reconnect_first(
	first: GameConnection, second: GameConnection, first_id: String, expected_experience: int
) -> bool:
	first.disconnect_game()
	if not _check(
		"shared_disconnect_removes_presence",
		await _wait_until(func(): return _player(second, first_id).is_empty())
	):
		return false
	first.connect_account(_server, _database, str(_tokens[0]), "progression-shared-reconnect")
	if not _check(
		"shared_reconnect_reaches_lobby",
		await _wait_until(func(): return first.state == "lobby", 20.0)
	):
		return false
	if not _check(
		"shared_reconnect_preserves_private_progression",
		await _wait_until(
			func():
				return (
					(
						int(first.progression_for(first_id).get("experience", -1))
						== expected_experience
					)
					and first.progression_for(second.local_identity).is_empty()
				),
			5.0
		)
	):
		return false
	first.enter_selected()
	return _check(
		"shared_reconnect_enters_same_character",
		await _wait_until(
			func():
				return (
					first.state == "connected"
					and first.local_identity == first_id
					and not _player(second, first_id).is_empty()
				),
			20.0
		)
	)


func _prepare_fresh_life(
	first: GameConnection, second: GameConnection, first_id: String, second_id: String
) -> bool:
	if not _check(
		"shared_second_life_is_fresh",
		await _wait_until(
			func(): return not first.monsters.is_empty() and int(first.monsters[0].health) == 100,
			16.0
		)
	):
		return false
	var dog: Dictionary = first.monsters[0]
	first.move_to(float(dog.x) - 2.35, float(dog.z))
	second.move_to(float(dog.x), float(dog.z) - 2.35)
	if not _check(
		"shared_second_life_contributors_in_range",
		await _wait_until(_both_in_range.bind(first, first_id, second_id), 10.0)
	):
		return false
	first.stop_moving()
	second.stop_moving()
	return true


func _select_slot(client: GameConnection, slot: int) -> String:
	for row: Dictionary in client.characters:
		if int(row.slot) == slot:
			var character_id := str(row.character_id)
			client.select_character(character_id)
			if _check(
				"shared_slot_%d_selected" % slot,
				await _wait_until(func(): return client.local_identity == character_id)
			):
				return character_id
			return ""
	_check("shared_slot_%d_exists" % slot, false)
	return ""


func _prepare_contributors(
	first: GameConnection, second: GameConnection, first_id: String, second_id: String
) -> bool:
	if not _check(
		"shared_dog_is_fresh",
		await _wait_until(
			func(): return not first.monsters.is_empty() and int(first.monsters[0].health) == 100,
			16.0
		)
	):
		return false
	if not await _equip_sword(first, first_id) or not await _equip_sword(second, second_id):
		return false
	var dog: Dictionary = first.monsters[0]
	first.move_to(float(dog.x) - 2.35, float(dog.z))
	second.move_to(float(dog.x), float(dog.z) - 2.35)
	if not _check(
		"shared_both_contributors_in_range",
		await _wait_until(_both_in_range.bind(first, first_id, second_id), 10.0)
	):
		return false
	first.stop_moving()
	second.stop_moving()
	return true


func _equip_sword(client: GameConnection, character_id: String) -> bool:
	for row: Dictionary in client.inventory:
		if str(row.owner) == character_id and int(row.vnum) == 10:
			if not bool(row.equipped):
				client.equip_item(int(row.id))
			return _check(
				"shared_sword_equipped",
				await _wait_until(func(): return _sword_is_equipped(client, character_id))
			)
	return _check("shared_sword_exists", false)


func _unequip_sword(client: GameConnection, character_id: String) -> bool:
	for row: Dictionary in client.inventory:
		if str(row.owner) == character_id and int(row.vnum) == 10:
			var destination := _free_sword_cell(client, character_id)
			var snapshot := {
				"destination": destination,
				"dog": client.monsters[0] if not client.monsters.is_empty() else {},
				"player": _player(client, character_id),
				"sword": row,
			}
			print("SHARED_UNEQUIP_PRECONDITION ", JSON.stringify(snapshot))
			if not _check(
				"shared_first_sword_unequip_precondition", bool(row.equipped) and destination >= 0
			):
				return false
			if bool(row.equipped):
				client.unequip_item(int(row.id), destination)
			return _check(
				"shared_first_sword_unequipped",
				await _wait_until(func(): return not _sword_is_equipped(client, character_id))
			)
	return _check("shared_first_sword_exists", false)


func _free_sword_cell(client: GameConnection, character_id: String) -> int:
	var occupied: Array[int] = []
	for item: Dictionary in client.inventory:
		if str(item.owner) != character_id or bool(item.equipped):
			continue
		var cell := int(item.cell)
		occupied.append(cell)
		if int(item.vnum) == 10:
			occupied.append(cell + 5)
	for cell in range(90):
		var row := int((cell % 45) / 5)
		if row + 2 <= 9 and cell not in occupied and cell + 5 not in occupied:
			return cell
	return -1


func _sword_is_equipped(client: GameConnection, character_id: String) -> bool:
	for row: Dictionary in client.inventory:
		if str(row.owner) == character_id and int(row.vnum) == 10:
			return bool(row.equipped)
	return false


func _both_in_range(client: GameConnection, first_id: String, second_id: String) -> bool:
	if client.monsters.is_empty():
		return false
	var dog_position := _position(client.monsters[0])
	return (
		_position(_player(client, first_id)).distance_to(dog_position) <= 2.6
		and _position(_player(client, second_id)).distance_to(dog_position) <= 2.6
	)


func _shared_attack(
	attacker: GameConnection, observer: GameConnection, expected_health: int, label: String
) -> bool:
	await create_timer(0.9).timeout
	attacker.perform_attack()
	return _check(
		label,
		await _wait_until(func(): return int(observer.monsters[0].health) == expected_health, 2.0)
	)
