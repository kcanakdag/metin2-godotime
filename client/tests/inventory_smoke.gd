extends "res://tests/multiplayer_smoke.gd"
## Inventory and equipment evidence from independent subscriptions on a disposable Yongan DB.

var _owner := ""
var _sword_id := 0
var _potion_id := 0


func _run() -> void:
	var first := _make_client()
	var second := _make_client()
	first.connect_game(_server, _database, "InventoryA", _profile_prefix + "-a")
	second.connect_game(_server, _database, "InventoryB", _profile_prefix + "-b")
	if not _check(
		"two_inventory_clients",
		await _wait_until(
			func(): return first.state == "connected" and second.state == "connected", 15
		)
	):
		_finish()
		return
	_owner = first.local_identity
	if not await _validate_inventory(first, second):
		_finish()
		return
	if not await _fight_with_equipment(first, second):
		_finish()
		return
	if not await _collect_item(first, second):
		_finish()
		return
	await _inventory_survives_death(first, second)
	_finish()


func _items(client: GameConnection, owner: String) -> Array:
	var items := client.inventory.filter(func(row: Dictionary): return str(row.owner) == owner)
	items.sort_custom(func(a: Dictionary, b: Dictionary): return int(a.id) < int(b.id))
	return items


func _item(client: GameConnection, id: int) -> Dictionary:
	for row: Dictionary in client.inventory:
		if int(row.id) == id:
			return row
	return {}


func _drop(client: GameConnection, id: int) -> Dictionary:
	for row: Dictionary in client.item_drops:
		if int(row.id) == id:
			return row
	return {}


func _rejected(label: String, action: Callable, reason: String) -> void:
	var before := _errors.size()
	action.call()
	_check(
		label, await _wait_until(func(): return _errors.size() > before and reason in _errors[-1])
	)


func _validate_inventory(first: GameConnection, second: GameConnection) -> bool:
	if not _check(
		"starter_items_replicate", await _wait_until(func(): return _starter_ready(first, second))
	):
		return false
	for row: Dictionary in _items(first, _owner):
		if int(row.vnum) == 10:
			_sword_id = int(row.id)
		elif int(row.vnum) == 27001:
			_potion_id = int(row.id)
	if not _check("starter_types", _sword_id > 0 and _potion_id > 0):
		return false
	_check("starter_sword_unequipped", not bool(_item(second, _sword_id).equipped))
	_check("starter_potion_count", int(_item(second, _potion_id).count) == 5)
	await _rejected(
		"other_owner_move_rejected", func(): second.move_item(_sword_id, 20), "another player"
	)
	await _rejected(
		"other_owner_equip_rejected", func(): second.equip_item(_sword_id), "another player"
	)
	await _rejected(
		"other_owner_use_rejected", func(): second.use_item(_potion_id), "another player"
	)
	await _rejected(
		"potion_cannot_be_equipped", func(): first.equip_item(_potion_id), "Only a sword"
	)
	await _rejected("vertical_overlap_rejected", func(): first.move_item(_potion_id, 5), "occupied")
	await _rejected("page_boundary_rejected", func(): first.move_item(_sword_id, 40), "page")
	# Bypass the UI's numeric guard to verify the server also rejects an encoded U8=255.
	await _rejected(
		"server_invalid_cell_rejected",
		func(): first._call_reducer("move_item", [_sword_id, 255], [&"U64", &"U8"]),
		"page"
	)
	first.move_item(_sword_id, 45)
	_check(
		"move_between_pages_replicates",
		await _wait_until(func(): return int(_item(second, _sword_id).cell) == 45)
	)
	first.move_item(_potion_id, 0)
	await _wait_until(func(): return int(_item(second, _potion_id).cell) == 0)
	first.equip_item(_sword_id)
	_check(
		"equipped_weapon_replicates",
		await _wait_until(func(): return bool(_item(second, _sword_id).equipped))
	)
	_check("equipped_weapon_frees_grid", int(_item(second, _sword_id).cell) == 255)
	await _rejected("equipped_move_rejected", func(): first.move_item(_sword_id, 60), "Unequip")
	await _rejected(
		"occupied_unequip_rejected", func(): first.unequip_item(_sword_id, 0), "occupied"
	)
	first.unequip_item(_sword_id, 60)
	_check(
		"unequip_replicates",
		await _wait_until(func(): return not bool(_item(second, _sword_id).equipped))
	)
	_check("unequip_uses_selected_cell", int(_item(second, _sword_id).cell) == 60)
	first.equip_item(_sword_id)
	await _wait_until(func(): return bool(_item(second, _sword_id).equipped))
	await _rejected("full_health_potion_rejected", func(): first.use_item(_potion_id), "full")
	first._call_reducer("enter_world", ["InventoryA"], [&"String"])
	await _wait_until(func(): return first._pending_calls.is_empty())
	_check("repeated_enter_no_starter_duplication", _items(second, _owner).size() == 2)
	return await _reconnect_inventory(first, second, "inventory_reconnect")


func _starter_ready(first: GameConnection, second: GameConnection) -> bool:
	return _items(second, _owner).size() == 2 and _items(first, second.local_identity).size() == 2


func _reconnect_inventory(first: GameConnection, second: GameConnection, label: String) -> bool:
	var before := _items(second, _owner).duplicate(true)
	first.disconnect_game()
	_check(
		label + "_presence_removed",
		await _wait_until(func(): return _player(second, _owner).is_empty())
	)
	first.reconnect_game()
	if not _check(
		label + "_connected", await _wait_until(func(): return first.state == "connected")
	):
		return false
	_check(label + "_same_identity", first.local_identity == _owner)
	_check(
		label + "_items_preserved",
		await _wait_until(func(): return _items(first, _owner) == before)
	)
	return true


func _fight_with_equipment(first: GameConnection, second: GameConnection) -> bool:
	second.move_to(660, 581)
	first.move_to(671, 575)
	if not _check("approach_sentinel", await _wait_until(func(): return _near_sentinel(first), 8)):
		return false
	first.stop_moving()
	if not _check(
		"sentinel_damages_player",
		await _wait_until(func(): return int(_player(second, _owner).get("health", 100)) <= 60, 8)
	):
		return false
	var health_before := int(_player(second, _owner).health)
	first.use_item(_potion_id)
	_check(
		"potion_consumes_one",
		await _wait_until(func(): return int(_item(second, _potion_id).count) == 4)
	)
	_check(
		"potion_heals_server_amount",
		int(_player(second, _owner).health) == mini(100, health_before + 40)
	)
	await _rejected("potion_cooldown_rejected", func(): first.use_item(_potion_id), "cooling")
	if not await _reconnect_inventory(first, second, "potion_reconnect"):
		return false
	await _rejected(
		"potion_reconnect_keeps_cooldown", func(): first.use_item(_potion_id), "cooling"
	)
	first.perform_attack()
	_check(
		"equipped_sword_adds_ten_damage",
		await _wait_until(func(): return int(second.monsters[0].health) == 65)
	)
	for i in 2:
		await create_timer(0.95).timeout
		first.perform_attack()
	return _check(
		"equipped_weapon_kills_sentinel",
		await _wait_until(func(): return int(second.monsters[0].health) == 0)
	)


func _near_sentinel(client: GameConnection) -> bool:
	if client.monsters.is_empty():
		return false
	return _position(_player(client, _owner)).distance_to(_position(client.monsters[0])) < 2.6


func _owned_drops(client: GameConnection) -> Array:
	return client.item_drops.filter(func(row: Dictionary): return str(row.owner) == _owner)


func _collect_item(first: GameConnection, second: GameConnection) -> bool:
	if not _check(
		"item_drop_replicates",
		await _wait_until(func(): return not _owned_drops(second).is_empty())
	):
		return false
	var owned_drops := _owned_drops(second)
	var drop: Dictionary = owned_drops[0]
	var id := int(drop.id)
	var position := _position(drop)
	_check("server_potion_drop", int(drop.vnum) == 27001 and int(drop.count) == 1)
	await _rejected(
		"reserved_item_pickup_rejected", func(): second.pickup_item_drop(id), "reserved"
	)
	first.move_to(position.x - 4, position.y)
	await _wait_until(func(): return _position(_player(first, _owner)).distance_to(position) > 3, 3)
	await _rejected("distant_item_pickup_rejected", func(): first.pickup_item_drop(id), "closer")
	first.move_to(position.x, position.y)
	await _wait_until(
		func(): return _position(_player(first, _owner)).distance_to(position) < 1.5, 4
	)
	first.pickup_item_drop(id)
	_check(
		"item_pickup_removes_drop_from_both",
		await _wait_until(
			func(): return _drop(first, id).is_empty() and _drop(second, id).is_empty()
		)
	)
	_check(
		"item_pickup_stacks_without_new_instance",
		await _wait_until(func(): return int(_item(second, _potion_id).count) == 5)
	)
	_check("item_pickup_keeps_instance_count", _items(second, _owner).size() == 2)
	await _rejected(
		"duplicate_item_pickup_rejected", func(): first.pickup_item_drop(id), "collected"
	)
	return true


func _inventory_survives_death(first: GameConnection, second: GameConnection) -> void:
	var before := _items(second, _owner).duplicate(true)
	_check(
		"sentinel_respawns",
		await _wait_until(func(): return int(second.monsters[0].health) == 100, 15)
	)
	if not _check(
		"player_dies_with_inventory",
		await _wait_until(func(): return int(_player(second, _owner).get("health", 100)) == 0, 15)
	):
		return
	_check("death_preserves_inventory", _items(second, _owner) == before)
	await _rejected("dead_player_cannot_use_potion", func(): first.use_item(_potion_id), "defeated")
	await _rejected("dead_player_cannot_equip", func(): first.equip_item(_sword_id), "defeated")
	await _reconnect_inventory(first, second, "death_inventory_reconnect")
	_check(
		"player_respawns_with_inventory",
		await _wait_until(func(): return int(_player(second, _owner).get("health", 0)) == 100, 10)
	)
	_check("respawn_preserves_inventory", _items(second, _owner) == before)
