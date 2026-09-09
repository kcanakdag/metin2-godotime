extends "res://tests/buff_smoke.gd"
## Quantitative live combat qualification for one selected self-buff rank.
##
## The fixture uses ordinary validated gameplay only: it equips the starter
## sword, attacks the passive training target, or lets a real Wild Dog attack
## the player. It never mutates health, damage, stats or buff state directly.

const DUMMY_ID := 900001
const SAMPLE_COUNT := 8
const MELEE_WAIT := 1.0

# Exact level-20 domains for the unspent initial Warrior stats (STR 6, DEX 3,
# VIT 4) and the selected content:
#   player -> training dummy: baseline [64, 66, 67], Aura (+83) [120, 122, 123]
#   Wild Dog -> player: baseline [10, 11, 13, 14, 16],
#     Strong Body (+101 defense) [1, 2, 3, 4, 5],
#     Berserk (+12% normal damage taken) [11, 12, 14, 15, 17].
const DUMMY_BASELINE := [64, 66, 67]
const DUMMY_AURA := [120, 122, 123]
const DOG_BASELINE := [10, 11, 13, 14, 16]
const DOG_STRONG_BODY := [1, 2, 3, 4, 5]
const DOG_BERSERK := [11, 12, 14, 15, 17]


func _verify_skill_reactions(first: GameConnection, second: GameConnection) -> void:
	if not await _prepare_buff_fixture(first):
		return
	match _buff_vnum():
		4:
			await _verify_aura_outgoing(first, second)
		3:
			await _verify_incoming(first, second, DOG_BERSERK, "berserk")
		19:
			await _verify_incoming(first, second, DOG_STRONG_BODY, "strong_body")
		_:
			_check("buff_combat_supported_skill", false)


func _verify_aura_outgoing(first: GameConnection, second: GameConnection) -> void:
	var identity := first.local_identity
	if not await _prepare_aura_melee(first, second, identity):
		return
	var baseline := await _sample_dummy_hits(first, second, SAMPLE_COUNT)
	if not _check("aura_baseline_samples", baseline.size() == SAMPLE_COUNT):
		return
	if not _check("aura_baseline_domain", _all_in_domain(baseline, DUMMY_BASELINE)):
		return
	if not await _cast_buff(first, second):
		return
	if not await _select_dummy(first, second):
		return
	var buffed := await _sample_dummy_hits(first, second, SAMPLE_COUNT)
	if not _check("aura_buffed_samples", buffed.size() == SAMPLE_COUNT):
		return
	var baseline_mean := _mean(baseline)
	var buffed_mean := _mean(buffed)
	_check("aura_buffed_domain", _all_in_domain(buffed, DUMMY_AURA))
	_check("aura_raises_ordinary_melee", buffed_mean > baseline_mean * 1.5)
	print("BUFF_COMBAT aura baseline=", baseline, " buffed=", buffed)


func _prepare_aura_melee(first: GameConnection, second: GameConnection, identity: String) -> bool:
	if not _check(
		"aura_dummy_subscribed",
		await _wait_until(func(): return not _dog(second, DUMMY_ID).is_empty(), 10.0)
	):
		return false
	var dummy := _dog(second, DUMMY_ID).duplicate(true)
	_check("aura_dummy_passive_fixture", int(dummy.max_health) >= 1000)
	var sword := _starter_sword(first)
	if not _check("aura_starter_sword", not sword.is_empty()):
		return false
	var sword_id := int(sword.id)
	first.equip_item(sword_id)
	if not _check(
		"aura_sword_equipped", await _wait_until(func(): return _sword_equipped(first, sword_id))
	):
		return false
	var destination := _xz(dummy) + Vector2(-1.2, 0.0)
	first.move_to(destination.x, destination.y)
	if not _check(
		"aura_reaches_dummy",
		await _wait_until(
			func(): return _xz(_player_row(second, identity)).distance_to(destination) < 0.25, 15.0
		)
	):
		return false
	first.stop_moving()
	return await _select_dummy(first, second)


func _verify_incoming(
	first: GameConnection, second: GameConnection, buffed_domain: Array, label: String
) -> void:
	var identity := first.local_identity
	if not _check(
		"incoming_dog_subscribed",
		await _wait_until(func(): return not _live_dogs(second).is_empty(), 10.0)
	):
		return
	var dog: Dictionary = _live_dogs(second)[0].duplicate(true)
	var dog_id := int(dog.id)
	var destination := _xz(dog) + Vector2(-1.2, 0.0)
	first.move_to(destination.x, destination.y)
	if not _check(
		"incoming_dog_approach",
		await _wait_until(func(): return _player_near_dog(second, identity, dog_id), 15.0)
	):
		return
	first.stop_moving()
	var baseline := await _sample_incoming(first, second, identity, SAMPLE_COUNT)
	if not _check("incoming_baseline_samples_%s" % label, baseline.size() == SAMPLE_COUNT):
		return
	if not _check("incoming_baseline_domain_%s" % label, _all_in_domain(baseline, DOG_BASELINE)):
		return
	if not await _cast_buff(first, second):
		return
	var buffed := await _sample_incoming(first, second, identity, SAMPLE_COUNT)
	if not _check("incoming_buffed_samples_%s" % label, buffed.size() == SAMPLE_COUNT):
		return
	var baseline_mean := _mean(baseline)
	var buffed_mean := _mean(buffed)
	_check("incoming_buffed_domain_%s" % label, _all_in_domain(buffed, buffed_domain))
	if label == "berserk":
		_check(
			"berserk_incoming_penalty",
			_any_outside_domain(buffed, DOG_BASELINE) and buffed_mean > baseline_mean
		)
	else:
		_check("strong_body_incoming_reduction", buffed_mean < baseline_mean * 0.5)
	print("BUFF_COMBAT ", label, " baseline=", baseline, " buffed=", buffed)


func _starter_sword(client: GameConnection) -> Dictionary:
	var swords := client.inventory.filter(func(item): return int(item.vnum) == 10)
	return swords[0] if swords.size() == 1 else {}


func _sword_equipped(client: GameConnection, sword_id: int) -> bool:
	for item: Dictionary in client.inventory:
		if int(item.id) == sword_id and bool(item.equipped):
			return true
	return false


func _live_dogs(client: GameConnection) -> Array:
	return client.monsters_for_definition(101).filter(
		func(row): return int(row.get("health", 0)) > 0
	)


func _player_near_dog(client: GameConnection, identity: String, dog_id: int) -> bool:
	return _xz(_player_row(client, identity)).distance_to(_xz(_dog(client, dog_id))) <= 2.0


func _select_dummy(first: GameConnection, second: GameConnection) -> bool:
	var dummy := _dog(second, DUMMY_ID)
	if dummy.is_empty():
		return false
	return await _raw_success(
		first, "select_combat_target", [DUMMY_ID, int(dummy.life_sequence)], [&"U32", &"U32"]
	)


func _sample_dummy_hits(first: GameConnection, second: GameConnection, count: int) -> Array:
	var samples: Array = []
	for index in range(count):
		var before := int(_dog(second, DUMMY_ID).health)
		if before <= 0:
			break
		var accepted := false
		for _attempt in 3:
			accepted = await _raw_success(first, "perform_attack", [], [])
			if accepted:
				break
			await create_timer(0.35).timeout
		if not accepted:
			break
		if not await _wait_until(func(): return int(_dog(second, DUMMY_ID).health) < before, 4.0):
			break
		var after := int(_dog(second, DUMMY_ID).health)
		if int(_dog(first, DUMMY_ID).health) != after:
			_check("aura_damage_replication_%d" % index, false)
			break
		samples.append(before - after)
		await create_timer(MELEE_WAIT).timeout
	return samples


func _sample_incoming(
	first: GameConnection, second: GameConnection, identity: String, count: int
) -> Array:
	var samples: Array = []
	for index in range(count):
		var before := int(_player_row(second, identity).health)
		if before <= 1:
			break
		if not await _wait_until(
			func(): return int(_player_row(second, identity).health) < before, 6.0
		):
			break
		var after := int(_player_row(second, identity).health)
		if int(_player_row(first, identity).health) != after:
			_check("incoming_damage_replication_%d" % index, false)
			break
		samples.append(before - after)
	return samples
