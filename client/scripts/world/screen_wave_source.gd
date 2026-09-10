class_name ScreenWaveSource
extends RefCounted
## Presentation-only feed from subscribed player rows into the camera wave layer.
##
## The timing, range, fingerprint and lifecycle rules stay in `ScreenWave`; this
## adapter only resolves the actor motion event and the actor/viewer positions a
## subscribed action row refers to. It is a translation step, not authority.

const AttackTiming := preload("res://scripts/actors/attack_timing.gd")
const PveVisibility := preload("res://scripts/world/pve_visibility.gd")


static func feed(
	camera_rig: OrbitCamera,
	actor_catalog: ActorCatalog,
	player_rows: Array,
	local_identity: String,
	appearance_for: Callable,
	server_time_us: int
) -> void:
	if server_time_us <= 0:
		return
	var viewer_position: Variant
	for row: Dictionary in player_rows:
		if bool(row.get("online", false)) and str(row.get("identity", "")) == local_identity:
			viewer_position = PveVisibility.position_for(row)
			break
	if not viewer_position is Vector3:
		camera_rig.reset_screen_waves()
		return
	for row: Dictionary in player_rows:
		if not bool(row.get("online", false)) or int(row.get("activity", -1)) != 2:
			continue
		var action_id := str(row.get("attack_action_id", ""))
		if action_id.is_empty():
			continue
		var actor_id := actor_catalog.player_actor_id(
			appearance_for.call(str(row.get("identity", ""))) as Dictionary
		)
		var motion := actor_catalog.motion(actor_id, "", action_id)
		var event: Variant = motion.get("screen_wave", {})
		var actor_position: Variant = PveVisibility.position_for(row)
		if not event is Dictionary or event.is_empty() or not actor_position is Vector3:
			continue
		event = event.duplicate()
		event["activation_offset_us"] = AttackTiming.scaled_us(
			int(event.get("activation_offset_us", 0)), int(row.get("attack_speed_percent", 100))
		)
		camera_rig.observe_screen_wave(
			str(row.get("identity", "")),
			row,
			event,
			actor_position,
			viewer_position,
			server_time_us
		)
