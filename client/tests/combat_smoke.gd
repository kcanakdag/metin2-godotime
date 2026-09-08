extends "res://tests/multiplayer_smoke.gd"
## Shared PvE evidence using two independent actual subscriptions and validated intents.


func _run() -> void:
	var first := _make_client()
	var second := _make_client()
	first.connect_game(_server, _database, "Slayer", _profile_prefix + "-a")
	second.connect_game(_server, _database, "Witness", _profile_prefix + "-b")
	if not _check(
		"two_pve_clients",
		await _wait_until(
			func(): return first.state == "connected" and second.state == "connected", 15
		)
	):
		_finish()
		return
	var first_id := first.local_identity
	second.move_to(660, 581)
	first.move_to(671, 575)
	if not _check(
		"approach_monster",
		await _wait_until(
			func():
				return (
					not first.monsters_for_definition(101).is_empty()
					and (
						_position(_player(first, first_id)).distance_to(
							_position(first.monsters_for_definition(101)[0])
						)
						< 2.6
					)
				),
			8
		)
	):
		_finish()
		return
	first.stop_moving()
	var before := _errors.size()
	first.perform_attack()
	first.perform_attack()
	_check("attack_cooldown_rejected", await _wait_until(func(): return _errors.size() > before))
	_check(
		"damage_replicates_to_witness",
		await _wait_until(func(): return int(second.monsters_for_definition(101)[0].health) == 75)
	)
	for i in 3:
		await create_timer(0.95).timeout
		first.perform_attack()
	_check(
		"monster_death_replicates",
		await _wait_until(func(): return int(second.monsters_for_definition(101)[0].health) == 0)
	)
	if not _check("one_reward_created", await _wait_until(func(): return second.loot.size() == 1)):
		_finish()
		return
	var loot_id := int(second.loot[0].id)
	var drop := _position(second.loot[0])
	before = _errors.size()
	second.pickup_loot(loot_id)
	_check(
		"loot_reservation_rejected",
		await _wait_until(func(): return _errors.size() > before and "reserved" in _errors[-1])
	)
	first.move_to(drop.x - 4, drop.y)
	await _wait_until(func(): return _position(_player(first, first_id)).distance_to(drop) > 3, 3)
	before = _errors.size()
	first.pickup_loot(loot_id)
	_check(
		"distant_pickup_rejected",
		await _wait_until(func(): return _errors.size() > before and "closer" in _errors[-1])
	)
	first.move_to(drop.x, drop.y)
	await _wait_until(func(): return _position(_player(first, first_id)).distance_to(drop) < 1.5, 4)
	first.pickup_loot(loot_id)
	_check(
		"loot_removed_from_both_clients",
		await _wait_until(func(): return first.loot.is_empty() and second.loot.is_empty())
	)
	_check("gold_is_server_granted", int(_player(second, first_id).get("gold", 0)) == 5)
	before = _errors.size()
	first.pickup_loot(loot_id)
	_check("duplicate_pickup_rejected", await _wait_until(func(): return _errors.size() > before))
	_check(
		"monster_respawns",
		await _wait_until(
			func(): return int(second.monsters_for_definition(101)[0].health) == 100, 15
		)
	)
	_check(
		"monster_can_defeat_player",
		await _wait_until(func(): return int(_player(second, first_id).get("health", 100)) == 0, 15)
	)
	before = _errors.size()
	first.set_move_input(1, 0)
	_check(
		"dead_player_action_rejected",
		await _wait_until(func(): return _errors.size() > before and "defeated" in _errors[-1])
	)
	first.disconnect_game()
	await _wait_until(func(): return _player(second, first_id).is_empty())
	first.reconnect_game()
	_check(
		"death_reconnect_does_not_heal",
		await _wait_until(func(): return first.state == "connected")
	)
	_check("reconnecting_keeps_death", int(_player(second, first_id).get("health", 100)) == 0)
	_check(
		"player_respawns_on_server",
		await _wait_until(func(): return int(_player(second, first_id).get("health", 0)) == 100, 10)
	)
	_check(
		"respawn_restores_safe_position",
		_position(_player(second, first_id)).distance_to(Vector2(660, 575)) < 0.1
	)
	_check("gold_survives_death_and_reconnect", int(_player(second, first_id).get("gold", 0)) == 5)
	_finish()
