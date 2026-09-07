extends "res://tests/combo_smoke.gd"
## Eight original appearances, two private accounts, actual authoritative actions.

const INITIAL := [
	[6, 4, 3, 3, 760, 260],
	[4, 3, 6, 3, 770, 260],
	[5, 3, 3, 5, 770, 300],
	[3, 4, 3, 6, 860, 320],
]
var _catalog: Dictionary = {}
var _base_catalog: Dictionary = {}
var _class_actions: Array = []
var _last_class_id := 3


func _run() -> void:
	_catalog = JSON.parse_string(
		FileAccess.get_file_as_string("res://tests/character-catalog.json")
	)
	_base_catalog = JSON.parse_string(
		FileAccess.get_file_as_string("res://tests/base-catalog.json")
	)
	var male := _make_client()
	var female := _make_client()
	var ready := await _create_class_rosters(male, female)
	var selected_classes: Array = range(4)
	var args := OS.get_cmdline_user_args()
	if "--class-id" in args:
		var class_id := int(args[args.find("--class-id") + 1])
		if class_id in range(4):
			selected_classes = [class_id]
	_last_class_id = int(selected_classes.back())
	for class_id: int in selected_classes:
		if not ready:
			break
		ready = await _exercise_class_pair(male, female, class_id)
	if ready:
		ready = await _class_reconnect(male, female)
	_check("classes_scenario_completed", ready)
	print("CLASS_ACTION_EVIDENCE ", JSON.stringify(_class_actions))
	_tokens.clear()
	_finish()


func _create_class_rosters(male: GameConnection, female: GameConnection) -> bool:
	male.connect_account(_server, _database, str(_tokens[0]), "classes-male")
	female.connect_account(_server, _database, str(_tokens[1]), "classes-female")
	if not _check(
		"two_independent_class_lobbies",
		(
			await _wait_until(
				func(): return male.state == "lobby" and female.state == "lobby", 20.0
			)
			and male.account_identity != female.account_identity
		)
	):
		return false
	if not await _subscribe_class_items(male) or not await _subscribe_class_items(female):
		return false
	for invalid in [[255, 0], [0, 255]]:
		await _raw_rejection(
			male,
			"create_character",
			[0, "Invalid", invalid[0], invalid[1]],
			[&"U8", &"String", &"U8", &"U8"],
			"invalid_appearance_%s" % str(invalid),
			"appearance"
		)
	_check(
		"invalid_creation_grants_no_roster_progression_or_items",
		male.characters.is_empty() and male.progression.is_empty() and male.inventory.is_empty()
	)
	for sex in 2:
		var client: GameConnection = male if sex == 0 else female
		for class_id in 4:
			client.create_character(
				class_id, "C%d%d_%s" % [sex, class_id, _name_suffix], class_id, sex
			)
			if not _check(
				"create_class_%d_sex_%d" % [class_id, sex],
				await _wait_until(func(): return client.characters.size() == class_id + 1)
			):
				return false
		if not _check(
			"complete_private_roster_%d" % sex,
			await _wait_until(
				func():
					return (
						_private_roster(client, 4)
						and _private_progression(client, 4)
						and client.inventory.size() == 8
						and _private_inventory(client)
					),
				5.0
			)
		):
			return false
		for class_id in 4:
			if not _initial_class(client, class_id, sex):
				return false
	return true


func _subscribe_class_items(client: GameConnection) -> bool:
	var subscription := client._client.subscribe(
		PackedStringArray(["SELECT * FROM inventory_item"])
	)
	if subscription.error != OK:
		return _check("class_inventory_subscription", false)
	var observed := {"applied": false}
	subscription.applied.connect(func(): observed.applied = true)
	return _check(
		"class_inventory_subscription", await _wait_until(func(): return observed.applied)
	)


func _character(client: GameConnection, class_id: int) -> Dictionary:
	for row: Dictionary in client.characters:
		if int(row.slot) == class_id:
			return row
	return {}


func _owned_starter_weapon(client: GameConnection, owner: String, class_id: int) -> Dictionary:
	var vnum := int(_catalog.classes[class_id].starter_weapon_vnum)
	for item: Dictionary in client.inventory:
		if str(item.owner) == owner and int(item.vnum) == vnum:
			return item
	return {}


func _initial_class(client: GameConnection, class_id: int, sex: int) -> bool:
	var character := _character(client, class_id)
	var row := client.progression_for(str(character.character_id))
	var expected: Array = INITIAL[class_id]
	var actual := [int(row.strength), int(row.vitality), int(row.dexterity), int(row.intelligence)]
	return _check(
		"source_stats_and_starters_%d_%d" % [class_id, sex],
		(
			actual == expected.slice(0, 4)
			and int(row.character_class) == class_id
			and int(character.character_class) == class_id
			and int(character.sex) == sex
			and int(row.level) == 1
			and int(row.experience) == 0
			and int(row.max_sp) == expected[5]
			and int(row.current_sp) == expected[5]
			and not _owned_starter_weapon(client, str(character.character_id), class_id).is_empty()
		)
	)


func _exercise_class_pair(male: GameConnection, female: GameConnection, class_id: int) -> bool:
	var male_id := str(_character(male, class_id).character_id)
	var female_id := str(_character(female, class_id).character_id)
	male.select_character(male_id)
	female.select_character(female_id)
	if not _check(
		"select_pair_%d" % class_id,
		await _wait_until(
			func(): return male.local_identity == male_id and female.local_identity == female_id
		)
	):
		return false
	male.enter_selected()
	female.enter_selected()
	if not _check(
		"mutual_class_presence_%d" % class_id,
		await _wait_until(
			func():
				return (
					male.state == "connected"
					and female.state == "connected"
					and _mutual_presence(male, female, male_id, female_id)
					and not male.appearance_for(female_id).is_empty()
					and not female.appearance_for(male_id).is_empty()
				),
			20.0
		)
	):
		return false
	_check(
		"class_catalog_and_protocol_%d" % class_id,
		(
			male.world_info == female.world_info
			and int(male.world_info.protocol_version) == GameConnection.EXPECTED_PROTOCOL_VERSION
			and (
				str(male.world_info.character_catalog_hash)
				== FileAccess.get_sha256("res://tests/character-catalog.json")
			)
		)
	)
	for sex in 2:
		var client: GameConnection = male if sex == 0 else female
		var observer: GameConnection = female if sex == 0 else male
		if not await _exercise_appearance(client, observer, class_id, sex):
			return false
	if class_id == _last_class_id:
		return true
	male.leave_world()
	female.leave_world()
	return _check(
		"class_switch_removes_previous_presence_%d" % class_id,
		await _wait_until(
			func():
				return (
					male.state == "lobby"
					and female.state == "lobby"
					and _player(male, female_id).is_empty()
					and _player(female, male_id).is_empty()
				),
			5.0
		)
	)


func _exercise_appearance(
	client: GameConnection, observer: GameConnection, class_id: int, sex: int
) -> bool:
	var id := client.local_identity
	var appearance := observer.appearance_for(id)
	if not _check(
		"remote_appearance_and_hp_%d_%d" % [class_id, sex],
		(
			int(appearance.character_class) == class_id
			and int(appearance.sex) == sex
			and int(_player(observer, id).max_health) == INITIAL[class_id][4]
		)
	):
		return false
	# Keep targetless chain checks outside the real dogs' aggro/leash area.
	# Earlier test players can leave a returning dog near the default spawn.
	client.clear_combat_target()
	client.move_to(640.0, 575.0)
	if not _check(
		"class_safe_action_position_%d_%d" % [class_id, sex],
		await _wait_until(
			func(): return _position(_player(observer, id)).distance_to(Vector2(640, 575)) < 0.1,
			12.0
		)
	):
		return false
	await _movement(client, observer, id, -1.0 if sex else 1.0, "class_%d_%d" % [class_id, sex])
	if not await _class_attack(client, observer, class_id, sex, false):
		return false
	if not await _equip_and_combo(client, observer, class_id, sex):
		return false
	return await _class_mob_hit(client, observer, class_id, sex)


func _equip_and_combo(
	client: GameConnection, observer: GameConnection, class_id: int, sex: int
) -> bool:
	var id := client.local_identity
	var weapon := _owned_starter_weapon(client, id, class_id)
	var vnum := int(weapon.vnum)
	client.equip_item(int(weapon.id))
	if not _check(
		"class_weapon_replication_%d_%d" % [class_id, sex],
		await _wait_until(func(): return observer.appearance_for(id).weapon_vnum == vnum)
	):
		return false
	await _raw_rejection(
		observer,
		"equip_item",
		[int(weapon.id), int(weapon.revision)],
		[&"U64", &"U32"],
		"foreign_weapon_%d_%d" % [class_id, sex],
		"another player"
	)
	await _raw_rejection(
		client,
		"equip_item",
		[int(weapon.id), int(weapon.revision)],
		[&"U64", &"U32"],
		"stale_weapon_%d_%d" % [class_id, sex],
		"changed"
	)
	if not await _class_attack(client, observer, class_id, sex, true):
		return false
	return await _class_combo(client, observer, class_id, sex)


func _motion(class_id: int, sex: int, armed: bool, step: int = 1) -> Dictionary:
	var definition: Dictionary = _catalog.classes[class_id]
	var actor_id := str(definition.variants[sex].actor_id)
	var actors: Array = _base_catalog.actors if class_id == 0 and sex == 0 else _catalog.actors
	for actor: Dictionary in actors:
		if actor.id != actor_id:
			continue
		for mode: Dictionary in actor.modes:
			if mode.id != (("fan" if class_id == 3 else "onehand") if armed else "general"):
				continue
			for motion: Dictionary in mode.motions:
				if motion.action == ("combo_%d" % step if armed else "normal_attack"):
					return motion
	return {}


func _class_combo(
	client: GameConnection, observer: GameConnection, class_id: int, sex: int
) -> bool:
	var id := client.local_identity
	var label := "class_combo_%d_%d" % [class_id, sex]
	var first := _motion(class_id, sex, true)
	var sequence := int(_player(observer, id).attack_sequence)
	if not await _raw_success(client, "perform_attack", [], [], label + "_start"):
		return false
	var action := await _wait_action_after(observer, id, sequence, str(first.action_id))
	if action.is_empty():
		return _check(label + "_first_step_replicates", false)
	_check(
		label + "_source_duration",
		int(action.action_ends_at_us) - int(action.action_started_at_us) == int(first.duration_us)
	)
	for step in range(1, 4):
		var motion := _motion(class_id, sex, true, step)
		var input: Dictionary = motion.combo
		var start := int(action.action_started_at_us)
		# Exercise both queued and immediate links at the authored class windows.
		var offset := int(input.pre_input_us) + 60000
		if step == 2:
			offset = int(input.direct_input_us) + 40000
		if not await _wait_server_time(observer, start + offset):
			return _check(label + "_input_window", false)
		if not await _raw_success(client, "perform_attack", [], [], label + "_link_%d" % step):
			return false
		if step == 1:
			await _raw_rejection(
				client, "perform_attack", [], [], label + "_duplicate_queue", "queued"
			)
		var next := _motion(class_id, sex, true, step + 1)
		var previous := int(action.attack_sequence)
		action = await _wait_action_after(observer, id, previous, str(next.action_id))
		if not _check(label + "_step_%d" % (step + 1), not action.is_empty()):
			return false
		_check(
			label + "_duration_%d" % (step + 1),
			(
				int(action.action_ends_at_us) - int(action.action_started_at_us)
				== int(next.duration_us)
			)
		)
		_class_actions.append(
			{"class_id": class_id, "sex": sex, "step": step + 1, "action": action}
		)
	return _check(
		label + "_finishes", await _wait_action_end(observer, id, int(action.action_ends_at_us))
	)


func _class_attack(
	client: GameConnection, observer: GameConnection, class_id: int, sex: int, armed: bool
) -> bool:
	var id := client.local_identity
	var motion := _motion(class_id, sex, armed)
	var before := int(_player(observer, id).attack_sequence)
	var result := await _raw_result(client, "perform_attack", [], [])
	var label := "class_action_%d_%d_%s" % [class_id, sex, "weapon" if armed else "unarmed"]
	_record_raw_result(label, "perform_attack", result)
	if not _check(label + "_accepted", bool(result.accepted)):
		return false
	var action := await _wait_action_after(observer, id, before, str(motion.action_id))
	if not _check(label + "_remote_source_action", not action.is_empty()):
		return false
	_check(
		label + "_source_duration",
		int(action.action_ends_at_us) - int(action.action_started_at_us) == int(motion.duration_us)
	)
	_class_actions.append({"class_id": class_id, "sex": sex, "armed": armed, "action": action})
	return _check(
		label + "_finishes", await _wait_action_end(observer, id, int(action.action_ends_at_us))
	)


func _class_mob_hit(
	client: GameConnection, observer: GameConnection, class_id: int, sex: int
) -> bool:
	# Population homes are actual server rows. No admin teleport or damage fixture.
	if not _check(
		"class_mobs_subscribe", await _wait_until(func(): return observer.monsters.size() == 6)
	):
		return false
	var start := _position(_player(observer, client.local_identity))
	if not await _approach_dog(client, observer, client.local_identity, 120):
		return false
	var dog := _monster(observer)
	client.select_combat_target(int(dog.id), int(dog.life_sequence))
	if not _check(
		"class_target_%d_%d" % [class_id, sex],
		await _wait_until(func(): return not client.selected_combat_target().is_empty())
	):
		return false
	var health := int(dog.health)
	if not await _class_attack(client, observer, class_id, sex, true):
		return false
	if not _check(
		"class_damage_seen_by_both_%d_%d" % [class_id, sex],
		await _wait_until(
			func():
				return (
					int(_monster(observer).health) < health
					and int(_monster(observer).health) == int(_monster(client).health)
				),
			5.0
		)
	):
		return false
	client.clear_combat_target()
	client.move_to(start.x, start.y)
	return _check(
		"class_returns_safely_%d_%d" % [class_id, sex],
		await _wait_until(
			func():
				return _position(_player(observer, client.local_identity)).distance_to(start) < 0.1,
			24.0
		)
	)


func _monster(client: GameConnection) -> Dictionary:
	# Separate dogs avoid a respawn dependency across the eight character checks.
	var class_id := int(client.appearance_for(client.local_identity).get("character_class", 0))
	for row: Dictionary in client.monsters:
		if int(row.id) == class_id + 1:
			return row
	return {}


func _class_reconnect(male: GameConnection, female: GameConnection) -> bool:
	var id := male.local_identity
	var inventory := male.inventory.duplicate(true)
	var roster := male.characters.duplicate(true)
	var appearance := female.appearance_for(id).duplicate(true)
	male.disconnect_game()
	if not _check(
		"class_disconnect_clears_presence_and_appearance",
		await _wait_until(
			func(): return _player(female, id).is_empty() and female.appearance_for(id).is_empty()
		)
	):
		return false
	if not await _reconnect_idle(male, female, id):
		return false
	_check(
		"class_reconnect_preserves_appearance_and_private_inventory",
		(
			await _wait_until(
				func():
					return (
						female.appearance_for(id) == appearance
						and male.characters == roster
						and _same_inventory(male.inventory, inventory)
					),
				5.0
			)
			and _private_roster(male, 4)
			and _private_progression(male, 4)
		)
	)
	var peer_id := female.local_identity
	female.disconnect_game()
	return _check(
		"class_peer_disconnect_removes_presence",
		await _wait_until(func(): return _player(male, peer_id).is_empty())
	)
