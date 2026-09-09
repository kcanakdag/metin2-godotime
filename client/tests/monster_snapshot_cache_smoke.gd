extends SceneTree
var _checks := 0
var _failed := false


func _initialize() -> void:
	var client := GameConnection.new()
	var first := GameMonster.new()
	first.id = 1
	first.health = 100
	first.attack_target = PackedByteArray([1, 2, 255])
	var second := GameMonster.new()
	second.id = 2
	var initial := client._snapshot_rows("monster", [first, second])
	_check(initial[0].attack_target == "0102ff", "identity conversion preserved")
	_check(initial[0].is_read_only(), "cached snapshots cannot be mutated by consumers")
	var repeated := client._snapshot_rows("monster", [first, second])
	_check(is_same(initial[0], repeated[0]), "unchanged SDK row reuses conversion")
	var replacement := GameMonster.new()
	replacement.id = 1
	replacement.health = 90
	client._on_row_updated("monster", first, replacement, client._session)
	var updated := client._snapshot_rows("monster", [replacement, second])
	_check(updated[0].health == 90 and initial[0].health == 100, "updates preserve old snapshots")
	_check(is_same(initial[1], updated[1]), "unrelated update retains unchanged conversion")
	replacement.health = 80
	client._on_row_updated("monster", replacement, replacement, client._session)
	updated = client._snapshot_rows("monster", [replacement])
	_check(updated[0].health == 80, "in-place update invalidates cached conversion")
	_check(client._monster_snapshot_cache.size() == 1, "removed rows release cached resources")
	client._clear_world_snapshots()
	_check(client._monster_snapshot_cache.is_empty(), "world exit drops all cached rows")
	var other := client._snapshot_rows("other", [first])
	_check(not other[0].is_read_only(), "other table behavior unchanged")
	_profile_flush(client, first)
	_benchmark(client)
	client.free()
	if not _failed:
		print("MONSTER_SNAPSHOT_CACHE_SMOKE PASS ", _checks, " checks")
	quit(1 if _failed else 0)


func _profile_flush(client: GameConnection, monster: GameMonster) -> void:
	var sdk := SpacetimeDBClient.new()
	var database := LocalDatabase.new(SpacetimeDBSchema.new("game"), sdk)
	sdk.add_child(database)
	sdk._local_db = database
	database._tables["monster"] = {monster.id: monster}
	client._client = sdk
	var results: Array = []
	var observe := func(table: String, count: int, conversion: int, dispatch: int):
		results.append([table, count, conversion, dispatch, client.monsters.size()])
	client.snapshot_profiled.connect(observe)
	client._dirty_tables["monster"] = true
	client._flush_snapshots()
	_check(
		results.size() == 1 and results[0][0] == "monster" and results[0][1] == 1,
		"profile identifies the actual flushed table and row count"
	)
	_check(
		results[0][2] >= 0 and results[0][3] >= 0 and results[0][4] == 1,
		"profile records separate nonnegative phases after publication"
	)
	client.snapshot_profiled.disconnect(observe)
	client._dirty_tables["monster"] = true
	client._flush_snapshots()
	_check(results.size() == 1 and client.monsters.size() == 1, "unobserved flush still publishes")
	client._client = null
	sdk.free()


func _benchmark(client: GameConnection) -> void:
	var rows: Array = []
	for index in 2800:
		var monster := GameMonster.new()
		monster.id = index + 1
		rows.append(monster)
	var started := Time.get_ticks_usec()
	for _iteration in 20:
		client._snapshot_rows("uncached", rows)
	var uncached := Time.get_ticks_usec() - started
	client._snapshot_rows("monster", rows)
	started = Time.get_ticks_usec()
	for _iteration in 20:
		client._snapshot_rows("monster", rows)
	var cached := Time.get_ticks_usec() - started
	print(
		JSON.stringify(
			{"rows": rows.size(), "iterations": 20, "uncached_us": uncached, "cached_us": cached}
		)
	)


func _check(passed: bool, label: String) -> void:
	_checks += 1
	if not passed:
		_failed = true
		push_error("MONSTER_SNAPSHOT_CACHE_SMOKE FAIL " + label)
