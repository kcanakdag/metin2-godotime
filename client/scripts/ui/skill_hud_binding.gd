extends RefCounted
## Keep progression and owner-only buff subscriptions connected in one place.


static func attach(connection: GameConnection, hud: DevHud) -> void:
	var sync := func(_rows: Array):
		hud.set_progression(
			connection.selected_progression(),
			connection.selected_skills(),
			connection.server_time_us
		)
	connection.progression_changed.connect(sync)
	connection.skills_changed.connect(sync)
	connection.buffs_changed.connect(
		func(rows: Array): hud.buff_strip.set_state(rows, connection.local_identity)
	)
