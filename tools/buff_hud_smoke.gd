extends "res://tests/buff_smoke.gd"
## The actual HUD consumes the real connection's owner-only status stream.


func _verify_skill_reactions(first: GameConnection, second: GameConnection) -> void:
	var hud: Node = load("res://scripts/ui/dev_hud.gd").new()
	root.add_child(hud)
	await process_frame
	hud.set_connection_state("connected", "")
	load("res://scripts/ui/skill_hud_binding.gd").attach(first, hud)
	var observations: Array = []
	var observe := func(rows: Array):
		observations.append({"rows": rows.size(), "icons": hud.buff_strip._icons.size()})
	first.buffs_changed.connect(observe)
	await super._verify_skill_reactions(first, second)
	_check(
		"hud_observed_live_buff",
		observations.any(func(row): return row.rows == 1 and row.icons == 1)
	)
	_check(
		"hud_observed_live_removal",
		observations.any(func(row): return row.rows == 0 and row.icons == 0)
	)
	_check("hud_has_no_icon_after_expiry", hud.buff_strip._icons.is_empty())
	_check("hud_duration_updates_reach_binding", observations.size() >= 10)
	first.buffs_changed.disconnect(observe)
	hud.queue_free()
