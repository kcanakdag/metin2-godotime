extends "res://tests/multiplayer_smoke.gd"
## Continue ordinary Wild Dog progression across short, freshly authenticated sessions.

var _token := ""
var _target_kills := 0


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var config_path := ""
	for i in range(args.size() - 1):
		if args[i] == "--progression-config":
			config_path = args[i + 1]
	var config: Variant = JSON.parse_string(FileAccess.get_file_as_string(config_path))
	if not config is Dictionary:
		printerr("Progression combat smoke requires a private config fixture.")
		quit(1)
		return
	_server = str(config.get("server", _server))
	_database = str(config.get("database", _database))
	_report_path = str(config.get("report", "user://progression-combat.json"))
	_token = str(config.get("token", ""))
	_target_kills = int(config.get("target_kills", 0))
	if _token.is_empty() or _target_kills not in [5, 10, 15, 20]:
		printerr("Progression combat smoke config is invalid.")
		quit(1)
		return
	call_deferred("_run")


func _run() -> void:
	var client := _make_client()
	client.connect_account(_server, _database, _token, "progression-%d" % _target_kills)
	if not _check(
		"authenticated_lobby", await _wait_until(func(): return client.state == "lobby", 20.0)
	):
		_finish()
		return
	var character_id := await _select_progression_character(client)
	if character_id.is_empty():
		_finish()
		return
	client.enter_selected()
	if not _check(
		"selected_character_enters",
		await _wait_until(func(): return client.state == "connected", 20.0)
	):
		_finish()
		return
	var expected_before := _expected_progression(_target_kills - 5, _target_kills > 5)
	if not _check(
		"segment_starts_at_expected_progression",
		_matches_progression(client.progression_for(character_id), expected_before)
	):
		_finish()
		return
	if not await _prepare_sword(client, character_id):
		_finish()
		return
	for index in range(5):
		if not await _kill_one_dog(client, character_id, index):
			_finish()
			return
	var expected := _expected_progression(_target_kills, _target_kills > 5)
	_check(
		"segment_reaches_expected_progression",
		await _wait_until(
			func(): return _matches_progression(client.progression_for(character_id), expected)
		)
	)
	_check(
		"automatic_quarter_potions_are_conserved",
		_small_potion_count(client, character_id) == 5 + 2 * (_target_kills / 5)
	)
	if _target_kills == 5:
		await _allocation_checks(client, character_id)
	if _target_kills == 20:
		var row := client.progression_for(character_id)
		_check(
			"level_growth_rolls_and_resources_are_bounded",
			(
				int(row.random_hp) in range(36, 45)
				and int(row.random_sp) in range(18, 23)
				and int(row.current_sp) == int(row.max_sp)
			)
		)
	_finish()


func _kill_one_dog(client: GameConnection, character_id: String, index: int) -> bool:
	if not _check(
		"dog_%d_is_alive" % index,
		await _wait_until(
			func():
				return (
					not client.monsters_for_definition(101).is_empty()
					and int(client.monsters_for_definition(101)[0].health) > 0
				),
			16.0
		)
	):
		return false
	var dog: Dictionary = client.monsters_for_definition(101)[0]
	client.move_to(float(dog.x) - 2.35, float(dog.z))
	if not _check(
		"dog_%d_reached" % index, await _wait_until(_in_dog_reach.bind(client, character_id), 10.0)
	):
		return false
	client.stop_moving()
	while int(client.monsters_for_definition(101)[0].health) > 0:
		var health := int(client.monsters_for_definition(101)[0].health)
		await create_timer(0.9).timeout
		client.perform_attack()
		if not _check(
			"dog_%d_hit_%d" % [index, health],
			await _wait_until(
				func(): return int(client.monsters_for_definition(101)[0].health) < health, 2.0
			)
		):
			return false
	var expected_kills := _target_kills - 4 + index
	return _check(
		"dog_%d_grants_progression" % index,
		await _wait_until(_has_exact_kill_count.bind(client, character_id, expected_kills))
	)


func _allocation_checks(client: GameConnection, character_id: String) -> void:
	await _raw_rejection(client, character_id, "vit", "unknown_stat_rejected", "Stat code")
	client.leave_world()
	_check(
		"allocation_leave_reaches_lobby", await _wait_until(func(): return client.state == "lobby")
	)
	await _raw_rejection(client, character_id, "ht", "stale_lobby_allocation_rejected", "Enter")
	client.enter_selected()
	if not _check(
		"allocation_reenters", await _wait_until(func(): return client.state == "connected", 20.0)
	):
		return
	if not _check(
		"allocation_waits_for_live_dog",
		await _wait_until(func(): return _has_live_dog(client), 16.0)
	):
		return
	var dog: Dictionary = client.monsters_for_definition(101)[0]
	client.move_to(float(dog.x) - 2.35, float(dog.z))
	await _wait_until(_in_dog_reach.bind(client, character_id), 10.0)
	client.stop_moving()
	var max_before := int(_player(client, character_id).max_health)
	if not _check(
		"allocation_waits_for_partial_health",
		await _wait_until(_has_partial_health.bind(client, character_id), 5.0)
	):
		return
	if not _check(
		"allocation_reaches_safe_distance", await _retreat_from_dog(client, character_id)
	):
		return
	var health_before := int(_player(client, character_id).health)
	client.allocate_stat(character_id, "ht")
	_check(
		"vitality_allocation_changes_max_without_current_heal",
		await _wait_until(
			_allocation_matches.bind(client, character_id, max_before + 40, health_before)
		)
	)
	_check(
		"first_quarter_post_allocation_is_exact",
		_matches_progression(client.progression_for(character_id), _expected_progression(5, true))
	)
	await _raw_rejection(client, character_id, "ht", "spent_point_rejected", "No unspent")


func _raw_rejection(
	client: GameConnection, character_id: String, code: String, label: String, reason: String
) -> void:
	var observed := {"done": false, "rejected": false}
	var call := client._client.call_reducer(
		"allocate_stat", [character_id.hex_decode(), code], [&"__identity__", &"String"]
	)
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


func _expected_progression(kills: int, allocated: bool) -> Dictionary:
	if kills < 20:
		return {
			"level": 1,
			"experience": kills * 15,
			"level_step": kills / 5,
			"unspent": kills / 5 - (1 if allocated else 0),
			"vitality": 5 if allocated else 4,
		}
	return {
		"level": 2,
		"experience": 0,
		"level_step": 0,
		"unspent": 2 if allocated else 3,
		"vitality": 5 if allocated else 4,
	}


func _matches_progression(row: Dictionary, expected: Dictionary) -> bool:
	return (
		int(row.get("level", 0)) == int(expected.level)
		and int(row.get("experience", -1)) == int(expected.experience)
		and int(row.get("level_step", -1)) == int(expected.level_step)
		and int(row.get("unspent_stat_points", -1)) == int(expected.unspent)
		and int(row.get("vitality", 0)) == int(expected.vitality)
	)


func _has_exact_kill_count(client: GameConnection, character_id: String, expected: int) -> bool:
	var row := client.progression_for(character_id)
	if expected == 20:
		return int(row.get("level", 0)) == 2 and int(row.get("experience", -1)) == 0
	return int(row.get("level", 0)) == 1 and int(row.get("experience", -1)) == expected * 15


func _sword_equipped(client: GameConnection, character_id: String) -> bool:
	return bool(_owned_sword(client, character_id).get("equipped", false))


func _prepare_sword(client: GameConnection, character_id: String) -> bool:
	var sword := _owned_sword(client, character_id)
	if not _check("owned_sword_exists", not sword.is_empty()):
		return false
	if bool(sword.get("equipped", false)):
		return true
	client.equip_item(int(sword.id))
	return _check(
		"owned_sword_equips", await _wait_until(_sword_equipped.bind(client, character_id))
	)


func _in_dog_reach(client: GameConnection, character_id: String) -> bool:
	return (
		not client.monsters_for_definition(101).is_empty()
		and (
			_position(_player(client, character_id)).distance_to(
				_position(client.monsters_for_definition(101)[0])
			)
			<= 2.6
		)
	)


func _has_partial_health(client: GameConnection, character_id: String) -> bool:
	var row := _player(client, character_id)
	return int(row.get("health", 0)) > 0 and int(row.health) < int(row.max_health)


func _has_live_dog(client: GameConnection) -> bool:
	return (
		not client.monsters_for_definition(101).is_empty()
		and int(client.monsters_for_definition(101)[0].get("health", 0)) > 0
	)


func _retreat_from_dog(client: GameConnection, character_id: String) -> bool:
	var player_position := _position(_player(client, character_id))
	var dog_position := _position(client.monsters_for_definition(101)[0])
	var away := player_position - dog_position
	if away.is_zero_approx():
		away = Vector2.LEFT
	var target := player_position + away.normalized() * 10.0
	client.move_to(target.x, target.y)
	var separated := await _wait_until(
		func(): return _dog_distance(client, character_id) > 8.5, 10.0
	)
	client.stop_moving()
	if not separated:
		return false
	var health := int(_player(client, character_id).health)
	await create_timer(0.5).timeout
	return (
		int(_player(client, character_id).health) == health
		and _dog_distance(client, character_id) > 8.0
	)


func _dog_distance(client: GameConnection, character_id: String) -> float:
	return _position(_player(client, character_id)).distance_to(
		_position(client.monsters_for_definition(101)[0])
	)


func _allocation_matches(
	client: GameConnection, character_id: String, expected_max: int, expected_health: int
) -> bool:
	var progression := client.progression_for(character_id)
	var player := _player(client, character_id)
	return (
		int(progression.get("vitality", 0)) == 5
		and int(progression.get("unspent_stat_points", -1)) == 0
		and int(player.get("max_health", 0)) == expected_max
		and int(player.get("health", 0)) == expected_health
	)


func _owned_sword(client: GameConnection, character_id: String) -> Dictionary:
	for row: Dictionary in client.inventory:
		if str(row.owner) == character_id and int(row.vnum) == 10:
			return row
	return {}


func _character_at_slot(client: GameConnection, slot: int) -> Dictionary:
	for row: Dictionary in client.characters:
		if int(row.slot) == slot:
			return row
	return {}


func _select_progression_character(client: GameConnection) -> String:
	var character := _character_at_slot(client, 1)
	if not _check("dedicated_progression_character_exists", not character.is_empty()):
		return ""
	var character_id := str(character.character_id)
	client.select_character(character_id)
	if not _check(
		"dedicated_progression_character_selected",
		await _wait_until(func(): return client.local_identity == character_id)
	):
		return ""
	return character_id


func _small_potion_count(client: GameConnection, character_id: String) -> int:
	var total := 0
	for row: Dictionary in client.inventory:
		if str(row.owner) == character_id and int(row.vnum) == 27001:
			total += int(row.count)
	return total
