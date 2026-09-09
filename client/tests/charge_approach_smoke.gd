extends SceneTree
var _checks := 0
var _failed := false


func _initialize() -> void:
	var definition := {
		"vnum": 5,
		"handler": "physical_charge_v1",
		"requires_target": true,
		"weapon_class": "sword_or_two_handed",
		"target_range_m": 1.7,
		"hits_per_life": 1,
		"charge":
		{
			"duration_us": 3000000,
			"speed_bonus": 150,
			"push_distance_m": 2,
			"main_target_stun_us": 4000000
		}
	}
	var owner := {"identity": "owner", "life_sequence": 0, "health": 100, "x": 0.0, "z": 0.0}
	var target := {"id": 1, "life_sequence": 2, "health": 100, "x": 3.0, "z": 0.0}
	var selected := {"target_id": 1, "target_life_sequence": 2}
	var charge := {"character_id": "owner", "skill_vnum": 5}
	var controller := ChargeApproach.new()
	_check(controller.start(definition, owner, target, 0) == "begin_charge", "far begin")
	_check(controller.advance(owner, target, {}, selected, 1) == "", "wait for subscription")
	_check(controller.advance(owner, target, charge, selected, 2) == "move_to", "charged approach")
	_check(controller.advance(owner, target, charge, selected, 3) == "", "movement throttle")
	owner.x = 2.0
	_check(
		controller.advance(owner, target, charge, selected, 4) == "cast_skill", "finish in range"
	)
	_check(controller.advance(owner, target, charge, selected, 5) == "", "no duplicate finish")
	controller.completed("cast_skill", false)
	_check(controller.phase == "idle", "rejection cancels")
	_check(controller.start(definition, owner, target, 10) == "cast_skill", "immediate strike")
	controller.cancel()
	_check(controller.phase == "idle", "manual cancel")
	owner.x = 0.0
	for mutation in [{"health": 0}, {"life_sequence": 3}, {"id": 2}]:
		controller.start(definition, owner, target, 0)
		var changed := target.duplicate()
		changed.merge(mutation, true)
		_check(
			controller.advance(owner, changed, charge, selected, 1) == "stop", "target invalidation"
		)
	controller.start(definition, owner, target, 0)
	_check(controller.advance(owner, target, charge, {}, 1) == "stop", "selection cleared")
	controller.start(definition, owner, target, 0)
	controller.advance(owner, target, charge, selected, 1)
	_check(controller.advance(owner, target, {}, selected, 2) == "stop", "charge expiry")
	controller.start(definition, owner, target, 0)
	_check(controller.advance(owner, target, {}, selected, 5000) == "stop", "bounded wait")
	if not _failed:
		print("CHARGE_APPROACH_SMOKE PASS ", _checks, " checks")
	quit(1 if _failed else 0)


func _check(passed: bool, label: String) -> void:
	_checks += 1
	if not passed:
		_failed = true
		push_error("CHARGE_APPROACH_SMOKE FAIL " + label)
