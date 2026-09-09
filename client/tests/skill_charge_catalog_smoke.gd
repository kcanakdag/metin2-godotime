extends SceneTree
## Charge capability gate accepts compiler JSON numbers and rejects malformed policy.
var _checks := 0
var _failed := false


func _initialize() -> void:
	var row := {
		"handler": "physical_charge_v1",
		"requires_target": true,
		"weapon_class": "sword_or_two_handed",
		"target_range_m": 1.7,
		"hits_per_life": 1,
		"charge":
		{
			"duration_us": 3000000,
			"speed_bonus": 150,
			"push_distance_m": 2.0,
			"main_target_stun_us": 4000000
		}
	}
	_check(SkillCatalog.supported_handler(row), "typed Dash policy")
	_check(
		SkillCatalog.supported_handler(JSON.parse_string(JSON.stringify(row))), "JSON numeric types"
	)
	for key in row.charge:
		var missing := row.duplicate(true)
		missing.charge.erase(key)
		_check(not SkillCatalog.supported_handler(missing), "missing " + key)
		for invalid in [null, "3", true, NAN, INF, -1.0]:
			var malformed := row.duplicate(true)
			malformed.charge[key] = invalid
			_check(not SkillCatalog.supported_handler(malformed), "invalid " + key)
	for mutation in [
		{"requires_target": false},
		{"requires_target": 1},
		{"weapon_class": "fan"},
		{"hits_per_life": 2},
		{"target_range_m": 0},
		{"handler": "unknown"},
		{"charge": []}
	]:
		var changed := row.duplicate(true)
		changed.merge(mutation, true)
		_check(not SkillCatalog.supported_handler(changed), "invalid capability")
	for handler in ["physical_splash_v1", "physical_area_v1"]:
		_check(SkillCatalog.supported_handler({"handler": handler}), "existing handler")
		_check(
			not SkillCatalog.supported_handler({"handler": handler, "charge": row.charge}),
			"misplaced charge"
		)
	var buffs := {
		"vnum": 3,
		"handler": "self_buff_v1",
		"buff": {},
		"requires_target": false,
		"weapon_class": "any",
		"target_range_m": 0,
		"radius_m": 0,
		"rank_costs": [],
		"rank_cooldowns_us": []
	}
	for rank in range(21):
		buffs.rank_costs.append(50 + rank)
		buffs.rank_cooldowns_us.append((63 + rank) * 1000000)
	_check(SkillCatalog.supported_handler(buffs), "buff presentation capability")
	var catalog := SkillCatalog.new()
	catalog.document = {"skills": [buffs]}
	for rank in range(21):
		_check(catalog.cost(3, rank) == 50 + rank, "compiled buff cost")
		_check(catalog.cooldown_us(3, rank) == (63 + rank) * 1000000, "compiled buff cooldown")
	for key in ["rank_costs", "rank_cooldowns_us"]:
		for invalid in [null, [], "wrong"]:
			var malformed := buffs.duplicate(true)
			malformed[key] = invalid
			_check(not SkillCatalog.supported_handler(malformed), "invalid buff rank table")
		for invalid in [NAN, INF, -1, "12", true, 0.5, 600000001]:
			var malformed := buffs.duplicate(true)
			malformed[key][12] = invalid
			_check(not SkillCatalog.supported_handler(malformed), "invalid buff rank value")
	var targeted := buffs.duplicate(true)
	targeted.requires_target = true
	_check(not SkillCatalog.supported_handler(targeted), "self buff cannot target enemies")
	if not _failed:
		print("SKILL_CHARGE_CATALOG_SMOKE PASS ", _checks, " checks")
	quit(1 if _failed else 0)


func _check(passed: bool, label: String) -> void:
	_checks += 1
	if not passed:
		_failed = true
		push_error("SKILL_CHARGE_CATALOG_SMOKE FAIL " + label)
