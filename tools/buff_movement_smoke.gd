extends "res://tests/buff_smoke.gd"
## Quantitative authoritative movement qualification for one selected self-buff rank.
##
## The observer measures held-input travel on the subscribed authoritative
## player row. The same corridor and procedure are used before and after the
## buff so server tick jitter largely cancels in the ratio.

const SAMPLE_COUNT := 3
const WARMUP_MS := 800
const SAMPLE_MS := 3000
const REISSUE_MS := 250
const CORRIDOR_LENGTH := 55.0
const TRAINING_CORRIDOR_CANDIDATES := [
	{"start": Vector2(-30.0, -28.0), "direction": Vector2(0.0, 1.0)},
	{"start": Vector2(-28.0, 30.0), "direction": Vector2(1.0, 0.0)},
	{"start": Vector2(28.0, -30.0), "direction": Vector2(-1.0, 0.0)},
]
const YONGAN_CORRIDOR_CANDIDATES := [
	{"start": Vector2(660.0, 500.0), "direction": Vector2(1.0, 0.0)},
	{"start": Vector2(660.0, 500.0), "direction": Vector2(-1.0, 0.0)},
	{"start": Vector2(660.0, 500.0), "direction": Vector2(0.0, 1.0)},
]


func _verify_skill_reactions(first: GameConnection, second: GameConnection) -> void:
	if not await _prepare_buff_fixture(first):
		return
	var vnum := _buff_vnum()
	var setup := _movement_setup(first, vnum)
	if not _check("movement_fixture", not setup.is_empty()):
		return
	var identity := first.local_identity
	var start: Vector2 = setup.corridor.start
	var direction: Vector2 = setup.corridor.direction
	var expected: float = setup.expected
	first.move_to(start.x, start.y)
	if not _check(
		"movement_reposition",
		await _wait_until(
			func(): return _xz(_player_row(second, identity)).distance_to(start) < 0.25, 30.0
		)
	):
		return
	first.stop_moving()
	# Let the spawn-area Wild Dog leash before the isolated speed samples.
	await create_timer(2.0).timeout
	var baseline := await _sample_travel(first, second, identity, start, direction)
	if not _check("movement_baseline_samples", baseline.size() == SAMPLE_COUNT):
		return
	if not await _cast_buff(first, second):
		return
	var buffed := await _sample_travel(first, second, identity, start, direction)
	if not _check("movement_buffed_samples", buffed.size() == SAMPLE_COUNT):
		return
	var baseline_mean := _mean(baseline)
	var buffed_mean := _mean(buffed)
	var ratio := buffed_mean / baseline_mean if baseline_mean > 0.0 else 0.0
	_check("movement_baseline_speed", baseline_mean > 4.5 and baseline_mean < 5.5)
	_check("movement_multiplier", absf(ratio - expected) <= 0.03)
	if vnum == 3:
		_check("berserk_movement_boost", ratio > 1.05)
	else:
		_check("strong_body_movement_penalty", ratio < 0.98)
	print(
		"BUFF_MOVEMENT vnum=",
		vnum,
		" expected=",
		expected,
		" baseline=",
		baseline,
		" buffed=",
		buffed,
		" ratio=",
		ratio
	)


func _movement_setup(first: GameConnection, vnum: int) -> Dictionary:
	if not _check("movement_supported_skill", vnum in [3, 19]):
		return {}
	var bonus := int(_buff_effects().get("movement_speed", 0))
	if not _check("movement_effect_present", bonus != 0):
		return {}
	var corridor := _find_corridor(first)
	if not _check("movement_clear_corridor", not corridor.is_empty()):
		return {}
	return {
		"corridor": corridor,
		"expected": _speed_multiplier(100 + bonus) / _speed_multiplier(100),
	}


func _sample_travel(
	first: GameConnection,
	second: GameConnection,
	identity: String,
	start: Vector2,
	direction: Vector2
) -> Array:
	var speeds: Array = []
	for index in range(SAMPLE_COUNT):
		first.move_to(start.x, start.y)
		if not await _wait_until(
			func(): return _xz(_player_row(second, identity)).distance_to(start) < 0.25, 30.0
		):
			break
		first.stop_moving()
		await create_timer(0.3).timeout
		first.set_move_input(direction.x, direction.y)
		await create_timer(float(WARMUP_MS) / 1000.0).timeout
		var from := _xz(_player_row(second, identity))
		var begin := Time.get_ticks_msec()
		var deadline := begin + SAMPLE_MS
		while Time.get_ticks_msec() < deadline:
			first.set_move_input(direction.x, direction.y)
			await create_timer(float(REISSUE_MS) / 1000.0).timeout
		var to := _xz(_player_row(second, identity))
		var elapsed := Time.get_ticks_msec() - begin
		first.stop_moving()
		await create_timer(0.3).timeout
		if elapsed <= 0 or from.distance_to(to) < 1.0:
			break
		speeds.append(from.distance_to(to) / (float(elapsed) / 1000.0))
	return speeds


func _find_corridor(client: GameConnection) -> Dictionary:
	var candidates := (
		YONGAN_CORRIDOR_CANDIDATES
		if str(client.world_info.get("map_id", "")) == "metin2_map_a1"
		else TRAINING_CORRIDOR_CANDIDATES
	)
	for candidate: Dictionary in candidates:
		var start: Vector2 = candidate.start
		var direction: Vector2 = candidate.direction
		if _clear_segment(client, start, direction, CORRIDOR_LENGTH):
			return candidate
	return {}


func _clear_segment(
	client: GameConnection, start: Vector2, direction: Vector2, length: float
) -> bool:
	var bounds := _map_bounds(client)
	if bounds.size.x <= 0.0 or bounds.size.y <= 0.0:
		return false
	var end := start + direction * length
	for point: Vector2 in [start, end]:
		if (
			point.x <= bounds.position.x + 0.5
			or point.x >= bounds.end.x - 0.5
			or point.y <= bounds.position.y + 0.5
			or point.y >= bounds.end.y - 0.5
		):
			return false
	var distance := 0.0
	while distance <= length:
		var point := start + direction * distance
		for obstacle: Dictionary in client.obstacles:
			var center := Vector2(float(obstacle.x), float(obstacle.z))
			var extent := Vector2(float(obstacle.half_x), float(obstacle.half_z))
			if (
				absf(point.x - center.x) <= extent.x + 0.55
				and absf(point.y - center.y) <= extent.y + 0.55
			):
				return false
		distance += 0.25
	return true


func _map_bounds(client: GameConnection) -> Rect2:
	if str(client.world_info.get("map_id", "")) == "metin2_map_a1":
		# Baked metin2_map_a1 dimensions from server/content/yongan.bin.
		return Rect2(0.0, 0.0, 1024.0, 1280.0)
	var half_size := float(client.world_info.get("half_size", 0.0))
	if half_size <= 0.0:
		return Rect2()
	return Rect2(-half_size, -half_size, half_size * 2.0, half_size * 2.0)


func _speed_multiplier(points: int) -> float:
	var clamped := clampi(points, 0, 200)
	var duration_percent: int = (
		200 - clamped if clamped < 100 else int(floor(10000.0 / float(clamped)))
	)
	return 100.0 / float(duration_percent)
