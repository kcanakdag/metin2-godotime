extends SceneTree
## Isolated real-resource actor, motion, equipment, timing, and malformed-content checks.

var _checks := 0
var _failed := false
var _catalog := ActorCatalog.new()
var _effect_catalog := TargetEffectCatalog.new()
var _stage: Node3D
var _camera: Camera3D


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	root.size = Vector2i(1280, 800)
	_check(_catalog.load_required(), "generated P1 manifest loads")
	_check(
		_effect_catalog.load_required(),
		"generated target-effect catalog loads: %s" % _effect_catalog.error_message
	)
	var dog_bounds := _catalog.actor_bounds(ActorCatalog.WILD_DOG_ID)
	_check(
		(
			(
				dog_bounds.get("minimum")
				== Vector3(-0.1642078459262848, 0.0009163692593574524, -0.681254506111145)
			)
			and (
				dog_bounds.get("maximum")
				== Vector3(0.20082877576351166, 0.8910432457923889, 0.588355302810669)
			)
		),
		"Wild Dog pick bounds come from the pinned artifact"
	)
	if _failed:
		_finish()
		return
	_build_stage()
	_test_catalog()
	await _test_shared_catalog()
	await _test_player()
	await _test_monster()
	_test_malformed()
	await _capture_named("overview")
	_finish()


func _test_catalog() -> void:
	_check(_catalog.gameplay_definition_hash().length() == 64, "definition hash is available")
	_check(
		_catalog.mode_for_weapon(ActorCatalog.WARRIOR_ID, 0) == "general",
		"unarmed Warrior selects general mode"
	)
	_check(
		_catalog.mode_for_weapon(ActorCatalog.WARRIOR_ID, 10) == "onehand",
		"subscribed starter sword selects onehand mode"
	)
	var attack := _catalog.motion(
		ActorCatalog.WARRIOR_ID, "", "actor.player.warrior-male.general.normal_attack.v1"
	)
	_check(attack.get("mode_id") == "general", "trusted action ID resolves across modes")
	_check(attack.get("duration_us") is int, "JSON motion duration is normalized to integer")
	_check(
		(
			_catalog.actor(ActorCatalog.WARRIOR_ID).get("forward") == "-Z"
			and _catalog.actor(ActorCatalog.WILD_DOG_ID).get("forward") == "-Z"
		),
		"both converted actors declare server-heading -Z forward"
	)
	_check(
		(
			(
				_catalog.actor(ActorCatalog.WARRIOR_ID).get("motion_vector_space")
				== "output_actor_local_godot"
			)
			and (
				_catalog.actor(ActorCatalog.WILD_DOG_ID).get("motion_vector_space")
				== "output_actor_local_godot"
			)
		),
		"motion vectors declare baked actor-local Godot coordinates"
	)
	_check(
		(
			_catalog
			. validate_world(
				{
					"definition_profile": ActorCatalog.PROFILE_ID,
					"definition_hash": _catalog.gameplay_definition_hash(),
				}
			)
		),
		"world profile and action hash match"
	)


func _test_player() -> void:
	var player := PlayerActor.new()
	player.name = "FixturePlayer"
	player.configure(_catalog)
	_stage.add_child(player)
	var row := _player_row()
	player.apply_state(row, true, {}, 1_000_000)
	_check(
		not bool(player.presentation_snapshot().get("visible", false)), "appearance may arrive late"
	)
	var appearance := _appearance(0)
	player.apply_state(row, true, appearance, 1_000_000)
	await process_frame
	var state := player.presentation_snapshot()
	_check(state.actor_id == ActorCatalog.WARRIOR_ID, "player instantiates generated Warrior")
	_check(".general.wait" in str(state.action_id), "idle uses manifest general wait")
	_check(_skinned_meshes(player) > 0, "Warrior uses an imported skinned mesh")
	_check(_skeleton_pose_is_sane(player), "Warrior wait pose remains in meter bounds")
	row.activity = 1
	player.apply_state(row, true, appearance, 1_050_000)
	_check(
		".general.run" in str(player.presentation_snapshot().action_id), "movement uses run clip"
	)
	var position_before := player.position
	await create_timer(0.08).timeout
	_check(
		player.position.distance_to(position_before) < 0.001,
		"clip root motion does not move server actor"
	)
	_check(_skeleton_pose_is_sane(player), "Warrior run pose remains in meter bounds")
	row.activity = 2
	row.attack_sequence = 4
	row.attack_action_id = "actor.player.warrior-male.general.normal_attack.v1"
	row.action_started_at_us = 1_000_000
	row.action_ends_at_us = 2_000_000
	player.apply_state(row, true, appearance, 1_400_000)
	state = player.presentation_snapshot()
	_check(state.mode == "general", "explicit attack keeps its server-frozen motion mode")
	_check(
		absf(float(state.animation_position) - 0.4) < 0.08,
		"late-join attack seeks from subscribed server time"
	)
	_check(_skeleton_pose_is_sane(player), "Warrior attack pose remains in meter bounds")
	var before_repeat := float(state.animation_position)
	await create_timer(0.08).timeout
	player.apply_state(row, true, appearance, 1_480_000)
	_check(
		float(player.presentation_snapshot().animation_position) > before_repeat + 0.03,
		"repeated attack sequence does not restart playback"
	)
	appearance = _appearance(10)
	player.apply_state(row, true, appearance, 1_500_000)
	state = player.presentation_snapshot()
	_check(state.weapon_vnum == 10 and state.equipment_attached, "subscribed sword is attached")
	_check(state.mode == "general", "mid-action equip does not replace frozen action")
	_check(_equipment_bounds_are_sane(player), "sword grip and bounds are in canonical meters")
	row.activity = 0
	row.action_started_at_us = 0
	row.action_ends_at_us = 0
	player.apply_state(row, true, appearance, 2_100_000)
	_check(
		".onehand.wait" in str(player.presentation_snapshot().action_id),
		"equipped idle uses onehand"
	)
	await _capture_from(
		"equipped-front", player.position + Vector3(0.0, 1.1, -3.2), player.position
	)
	await _capture_from("equipped-side", player.position + Vector3(3.2, 1.1, 0.0), player.position)
	var sword_attack := _catalog.motion(
		ActorCatalog.WARRIOR_ID, "", "actor.player.warrior-male.onehand.combo_1"
	)
	var hit_start_us := _first_hit_time(sword_attack)
	row.activity = 2
	row.attack_sequence = 5
	row.attack_action_id = str(sword_attack.action_id)
	row.action_started_at_us = 3_000_000
	row.action_ends_at_us = 3_000_000 + int(sword_attack.duration_us)
	player.apply_state(row, true, appearance, 3_000_000 + hit_start_us)
	await _capture_from("warrior-swing", player.position + Vector3(2.8, 1.4, -3.6), player.position)
	row.activity = 0
	row.action_started_at_us = 0
	row.action_ends_at_us = 0
	appearance = _appearance(0)
	player.apply_state(row, true, appearance, 4_150_000)
	_check(not player.presentation_snapshot().equipment_attached, "unequipped sword is removed")
	row.health = 70
	player.apply_state(row, true, appearance, 2_200_000)
	var damage_action := str(player.presentation_snapshot().action_id)
	row.health = 70
	player.apply_state(row, true, appearance, 2_250_000)
	_check(
		(
			player.presentation_snapshot().action_id == damage_action
			and "front_damage" in damage_action
		),
		"damage clip survives ordinary snapshots for its declared duration"
	)
	await create_timer(0.7).timeout
	_check(
		".general.wait" in str(player.presentation_snapshot().action_id),
		"damage clip returns to idle without another row update"
	)
	row.activity = 3
	row.life_sequence = 3
	row.action_started_at_us = 2_000_000
	row.action_ends_at_us = 10_000_000
	player.apply_state(row, true, appearance, 9_000_000)
	state = player.presentation_snapshot()
	_check(
		"death" in str(state.action_id) and state.frozen_pose, "late-join death holds final pose"
	)
	var warrior_death_bounds := _skeleton_pose_bounds(player)
	print("ACTOR_POSE warrior_death ", JSON.stringify(warrior_death_bounds))
	_check(_pose_bounds_are_sane(warrior_death_bounds), "Warrior death remains near actor origin")
	var warrior_death_center := _skeleton_pose_center(player)
	await _capture_from(
		"warrior-death",
		warrior_death_center + Vector3(2.8, 1.4, -3.6),
		warrior_death_center - Vector3.UP * 0.75
	)
	row.activity = 0
	row.health = 100
	row.life_sequence = 4
	row.action_started_at_us = 0
	row.action_ends_at_us = 0
	player.apply_state(row, true, appearance, 10_100_000)
	_check(
		"wait" in str(player.presentation_snapshot().action_id), "life sequence resets death state"
	)


func _test_shared_catalog() -> void:
	var first := ActorPresentation.new()
	var second := ActorPresentation.new()
	_check(
		(
			first.configure(_catalog, ActorCatalog.WARRIOR_ID)
			and second.configure(_catalog, ActorCatalog.WARRIOR_ID)
		),
		"two presentations configure from one immutable catalog"
	)
	_stage.add_child(first)
	_stage.add_child(second)
	_check(
		(
			first.play_action("general", "", "wait", 0)
			and second.play_action("general", "", "wait", 0)
		),
		"two presentations share one cached motion"
	)
	var wait_action_id := str(second.snapshot().action_id)
	first.reset_action()
	_check(
		(
			str(_catalog.motion(ActorCatalog.WARRIOR_ID, "general", "", "wait").action_id)
			== wait_action_id
		),
		"resetting one presentation preserves the shared cached motion"
	)
	_check(
		(
			first.play_action("general", "", "wait", 0)
			and str(first.snapshot().action_id) == wait_action_id
			and str(second.snapshot().action_id) == wait_action_id
		),
		"shared motion replays after another presentation resets"
	)
	first.queue_free()
	second.queue_free()


func _test_monster() -> void:
	var dog := PveActor.new()
	dog.name = "FixtureDog"
	dog.configure(_catalog, _effect_catalog)
	_stage.add_child(dog)
	var row := {
		"id": 1,
		"x": 1.8,
		"y": 0.0,
		"z": 0.0,
		"heading": 0.0,
		"health": 100,
		"max_health": 100,
		"activity": 0,
		"attack_sequence": 0,
		"life_sequence": 0,
		"action_started_at_us": 0,
		"action_ends_at_us": 0,
		"definition_vnum": 101,
		"actor_id": ActorCatalog.WILD_DOG_ID,
		"name": "Wild Dog",
		"model_key": "stray_dog",
		"motion_set": "actor.mob.wild-dog-101.general",
		"attack_action_id": "actor.mob.wild-dog-101.general.normal_attack.v1",
	}
	dog.apply_state(row, 1_000_000)
	await process_frame
	var state := dog.presentation_snapshot()
	_check(state.actor_id == ActorCatalog.WILD_DOG_ID, "vnum 101 uses original Wild Dog actor")
	_check(state.definition_vnum == 101, "monster presentation retains definition vnum")
	var pick_body := dog.get_node("TargetPickBody") as StaticBody3D
	var pick_shape := pick_body.get_node("TargetPickShape") as CollisionShape3D
	var expected_bounds := _catalog.actor_bounds(ActorCatalog.WILD_DOG_ID)
	var expected_minimum: Vector3 = expected_bounds.minimum
	var expected_maximum: Vector3 = expected_bounds.maximum
	_check(
		(
			pick_body.collision_layer == 2
			and pick_body.collision_mask == 0
			and pick_body.position.is_equal_approx((expected_minimum + expected_maximum) * 0.5)
			and (pick_shape.shape as BoxShape3D).size.is_equal_approx(
				expected_maximum - expected_minimum
			)
		),
		"Wild Dog pick proxy uses pinned bounds on dedicated layer 2"
	)
	_check(state.pickable, "live streamed Wild Dog is pickable")
	var projection := dog.pick_projection(_camera, root.get_visible_rect())
	_check(
		(
			projection.available
			and Vector2(float(projection.screen[0]), float(projection.screen[1])).is_finite()
			and projection.target_id == 1
			and projection.target_life_sequence == 0
		),
		"live in-front Wild Dog exposes a finite viewport pick point and exact generation"
	)
	dog.set_targeted(true)
	dog.set_hovered(true)
	var target_effect := dog.get_node("AcceptedTargetEffect") as Node3D
	var hover_effect := dog.get_node("HoverTargetEffect") as Node3D
	target_effect.set_process(false)
	hover_effect.set_process(false)
	target_effect._process(0.020001)
	hover_effect._process(0.020001)
	state = dog.presentation_snapshot()
	_check(
		(
			state.target_effect.visible
			and state.target_effect.effect_id == TargetEffectCatalog.TARGET_ID
			and state.target_effect.layer_count == 2
			and state.hover_effect.visible
			and state.hover_effect.effect_id == TargetEffectCatalog.HOVER_ID
			and state.hover_effect.layer_count == 1
		),
		"accepted target and local hover effects coexist with their source layers"
	)
	row.health = 99
	dog.apply_state(row, 1_000_000)
	dog.set_targeted(true)
	state = dog.presentation_snapshot()
	_check(
		(
			state.targeted
			and state.hovered
			and state.target_effect.frame == 1
			and state.hover_effect.frame == 1
			and dog.get_node("AcceptedTargetEffect") == target_effect
			and dog.get_node("HoverTargetEffect") == hover_effect
		),
		"same-life HP and accepted-target renewals preserve both effect instances and clocks"
	)
	dog.set_targeted(false)
	dog.set_hovered(false)
	state = dog.presentation_snapshot()
	_check(
		not state.target_effect.visible and not state.hover_effect.visible,
		"inactive target and hover roles hide their retained effect instances"
	)
	dog.set_targeted(true)
	dog.set_hovered(true)
	state = dog.presentation_snapshot()
	_check(
		(
			state.target_effect.frame == 0
			and state.hover_effect.frame == 0
			and dog.get_node("AcceptedTargetEffect") == target_effect
			and dog.get_node("HoverTargetEffect") == hover_effect
		),
		"role reactivation resets the retained effect clocks"
	)
	target_effect._process(0.020001)
	dog.set_stream_visible(false)
	state = dog.presentation_snapshot()
	_check(
		(
			not state.pickable
			and not state.hovered
			and not state.hover_effect.visible
			and not state.target_effect.visible
		),
		"unstreamed Wild Dog disables picking and hides both effects"
	)
	dog.set_stream_visible(true)
	state = dog.presentation_snapshot()
	_check(
		(
			state.target_effect.visible
			and state.target_effect.frame == 1
			and dog.get_node("AcceptedTargetEffect") == target_effect
		),
		"stream restoration resumes the same accepted-target effect instance and clock"
	)
	_check(_skinned_meshes(dog) > 0, "Wild Dog uses an imported skinned mesh")
	_check(_skeleton_pose_is_sane(dog), "Wild Dog wait pose remains in meter bounds")
	row.activity = 2
	row.attack_sequence = 7
	row.action_started_at_us = 1_000_000
	row.action_ends_at_us = 2_000_000
	dog.apply_state(row, 1_300_000)
	state = dog.presentation_snapshot()
	_check(state.attack_sequence == 7, "monster consumes subscribed attack sequence")
	_check("normal_attack" in str(state.action_id), "monster consumes subscribed action ID")
	_check(_skeleton_pose_is_sane(dog), "Wild Dog attack pose remains in meter bounds")
	await _capture_from("dog-attack", dog.position + Vector3(2.4, 1.1, -3.0), dog.position)
	row.attack_sequence = 8
	row.action_started_at_us = 2_000_000
	row.action_ends_at_us = 3_000_000
	dog.apply_state(row, 0)
	dog.apply_state(row, 2_350_000)
	_check(
		absf(float(dog.presentation_snapshot().animation_position) - 0.35) < 0.08,
		"late server clock reseeks an already subscribed monster action"
	)
	row.activity = 3
	row.life_sequence = 2
	row.action_started_at_us = 4_000_000
	row.action_ends_at_us = 16_000_000
	var death := _catalog.motion(ActorCatalog.WILD_DOG_ID, "general", "", "front_death")
	dog.apply_state(row, 4_000_000 + int(death.duration_us) + 10_000)
	_check(dog.presentation_snapshot().frozen_pose, "Wild Dog death holds its final pose")
	_check(
		(
			not dog.presentation_snapshot().pickable
			and not dog.presentation_snapshot().targeted
			and dog.presentation_snapshot().hover_effect.is_empty()
			and dog.presentation_snapshot().target_effect.is_empty()
		),
		"death/new life disables picking and detaches prior-generation effects"
	)
	var dog_death_bounds := _skeleton_pose_bounds(dog)
	print("ACTOR_POSE dog_death ", JSON.stringify(dog_death_bounds))
	_check(_pose_bounds_are_sane(dog_death_bounds), "Wild Dog death remains near actor origin")
	var dog_death_center := _skeleton_pose_center(dog)
	await _capture_from(
		"dog-death",
		dog_death_center + Vector3(2.4, 1.1, -3.0),
		dog_death_center - Vector3.UP * 0.75
	)


func _test_malformed() -> void:
	var mutable_document: Dictionary = _catalog.manifest.duplicate(true)
	var isolated := ActorCatalog.new()
	isolated.report_errors = false
	_check(isolated.load_document(mutable_document), "catalog accepts an independent document copy")
	var original_wait := str(
		isolated.motion(ActorCatalog.WARRIOR_ID, "general", "", "wait").action_id
	)
	mutable_document.actors[0].modes[0].motions[0].action_id = "caller.changed.action"
	_check(
		(
			str(isolated.motion(ActorCatalog.WARRIOR_ID, "general", "", "wait").action_id)
			== original_wait
		),
		"caller mutation cannot alter cached catalog definitions"
	)
	_check(
		isolated.actor(ActorCatalog.WARRIOR_ID).is_read_only(),
		"indexed actor definitions are recursively read-only"
	)
	var missing := ActorCatalog.new()
	missing.report_errors = false
	_check(not missing.load_required("res://missing-profile.json"), "missing profile fails clearly")
	_check("missing" in missing.error_message.to_lower(), "missing profile explains failure")
	var malformed: Dictionary = _catalog.manifest.duplicate(true)
	malformed.actors[0].modes[0].motions[0].duration_us = 1.5
	var invalid := ActorCatalog.new()
	invalid.report_errors = false
	_check(not invalid.load_document(malformed), "fractional motion duration is rejected")
	_check(not invalid.error_message.is_empty(), "malformed profile reports a reason")
	var malformed_bounds: Dictionary = _catalog.manifest.duplicate(true)
	for artifact: Dictionary in malformed_bounds.artifacts:
		if artifact.id == ActorCatalog.WILD_DOG_ID:
			artifact.bounds_m[1][0] = artifact.bounds_m[0][0]
	var invalid_bounds := ActorCatalog.new()
	invalid_bounds.report_errors = false
	_check(invalid_bounds.load_document(malformed_bounds), "bounds do not change the P1 schema")
	_check(
		invalid_bounds.actor_bounds(ActorCatalog.WILD_DOG_ID).is_empty(),
		"unordered artifact bounds cannot construct a pick shape"
	)
	var overflowing_bounds: Dictionary = _catalog.manifest.duplicate(true)
	for artifact: Dictionary in overflowing_bounds.artifacts:
		if artifact.id == ActorCatalog.WILD_DOG_ID:
			artifact.bounds_m[1][0] = 1.0e300
	var invalid_overflow := ActorCatalog.new()
	invalid_overflow.report_errors = false
	_check(invalid_overflow.load_document(overflowing_bounds), "bounds remain optional P1 metadata")
	_check(
		invalid_overflow.actor_bounds(ActorCatalog.WILD_DOG_ID).is_empty(),
		"finite float64 bounds that overflow Vector3 cannot construct a pick shape"
	)


func _player_row() -> Dictionary:
	return {
		"identity": "01".repeat(32),
		"name": "Fixture Warrior",
		"x": -0.8,
		"y": 0.0,
		"z": 0.0,
		"heading": 0.0,
		"activity": 0,
		"online": true,
		"attack_sequence": 0,
		"life_sequence": 0,
		"attack_action_id": "",
		"action_started_at_us": 0,
		"action_ends_at_us": 0,
		"health": 100,
		"max_health": 100,
		"gold": 0,
		"respawn_at_us": 0,
	}


func _appearance(weapon_vnum: int) -> Dictionary:
	return {
		"character_id": "01".repeat(32),
		"empire": 1,
		"character_class": 0,
		"sex": 0,
		"weapon_vnum": weapon_vnum,
	}


func _build_stage() -> void:
	_stage = Node3D.new()
	root.add_child(_stage)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-45, -25, 0)
	light.light_energy = 1.2
	_stage.add_child(light)
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-25, 155, 0)
	fill.light_energy = 0.8
	_stage.add_child(fill)
	var world_environment := WorldEnvironment.new()
	world_environment.environment = Environment.new()
	world_environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	world_environment.environment.ambient_light_color = Color(0.8, 0.85, 0.95)
	world_environment.environment.ambient_light_energy = 0.55
	_stage.add_child(world_environment)
	var ground := MeshInstance3D.new()
	var ground_mesh := PlaneMesh.new()
	ground_mesh.size = Vector2(8.0, 7.0)
	ground.mesh = ground_mesh
	_stage.add_child(ground)
	var marker := MeshInstance3D.new()
	var marker_mesh := BoxMesh.new()
	marker_mesh.size = Vector3(0.08, 0.04, 2.0)
	marker.mesh = marker_mesh
	marker.position = Vector3(0.0, 0.03, -1.0)
	_stage.add_child(marker)
	var forward_label := Label3D.new()
	forward_label.text = "SERVER HEADING 0  →  -Z"
	forward_label.position = Vector3(0.0, 0.08, -2.3)
	forward_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	forward_label.font_size = 28
	forward_label.pixel_size = 0.006
	_stage.add_child(forward_label)
	_camera = Camera3D.new()
	_camera.position = Vector3(3.8, 2.5, -6.5)
	_camera.look_at_from_position(_camera.position, Vector3(0.3, 0.8, 0))
	_camera.current = true
	_stage.add_child(_camera)


func _skinned_meshes(node: Node) -> int:
	var count := 1 if node is MeshInstance3D and node.skin else 0
	for child: Node in node.get_children():
		count += _skinned_meshes(child)
	return count


func _equipment_bounds_are_sane(node: Node) -> bool:
	var attachment := node.find_child("Equipment_10", true, false) as BoneAttachment3D
	if attachment == null:
		return false
	var bounds := AABB()
	var found := false
	var pending: Array[Node] = [attachment]
	while not pending.is_empty():
		var current: Node = pending.pop_back()
		if current is MeshInstance3D and current.mesh:
			var mesh_bounds: AABB = current.global_transform * current.mesh.get_aabb()
			bounds = mesh_bounds if not found else bounds.merge(mesh_bounds)
			found = true
		for child: Node in current.get_children():
			pending.append(child)
	return (
		found
		and bounds.size.length() > 0.2
		and bounds.size.length() < 3.0
		and bounds.get_center().distance_to(attachment.global_position) < 2.0
	)


func _skeleton_pose_is_sane(node: Node) -> bool:
	var skeleton := _find_skeleton(node)
	if skeleton == null:
		return false
	for index in skeleton.get_bone_count():
		if skeleton.get_bone_global_pose(index).origin.length() > 4.0:
			return false
	return true


func _skeleton_pose_bounds(node: Node) -> Dictionary:
	var skeleton := _find_skeleton(node)
	if skeleton == null or skeleton.get_bone_count() == 0:
		return {}
	var minimum := skeleton.get_bone_global_pose(0).origin
	var maximum := minimum
	for index in skeleton.get_bone_count():
		var point := skeleton.get_bone_global_pose(index).origin
		minimum = minimum.min(point)
		maximum = maximum.max(point)
	return {
		"minimum": [minimum.x, minimum.y, minimum.z],
		"maximum": [maximum.x, maximum.y, maximum.z],
	}


func _skeleton_pose_center(node: Node) -> Vector3:
	var skeleton := _find_skeleton(node)
	var bounds := _skeleton_pose_bounds(node)
	if skeleton == null or bounds.is_empty():
		return node.global_position
	var minimum: Array = bounds.minimum
	var maximum: Array = bounds.maximum
	var local_center := Vector3(
		(float(minimum[0]) + float(maximum[0])) * 0.5,
		(float(minimum[1]) + float(maximum[1])) * 0.5,
		(float(minimum[2]) + float(maximum[2])) * 0.5
	)
	return skeleton.global_transform * local_center


func _pose_bounds_are_sane(bounds: Dictionary) -> bool:
	if bounds.is_empty():
		return false
	var minimum: Array = bounds.minimum
	var maximum: Array = bounds.maximum
	return (
		float(minimum[0]) > -4.0
		and float(minimum[1]) > -2.0
		and float(minimum[2]) > -4.0
		and float(maximum[0]) < 4.0
		and float(maximum[1]) < 3.0
		and float(maximum[2]) < 4.0
	)


func _find_skeleton(node: Node) -> Skeleton3D:
	if node is Skeleton3D:
		return node
	for child: Node in node.get_children():
		var found := _find_skeleton(child)
		if found:
			return found
	return null


func _first_hit_time(motion: Dictionary) -> int:
	for event: Dictionary in motion.get("events", []):
		if str(event.get("kind", "")) in ["attack_window", "attack_area"]:
			return int((int(event.get("start_us", 0)) + int(event.get("end_us", 0))) / 2.0)
	return 0


func _capture_from(name: String, camera_position: Vector3, target: Vector3) -> void:
	_camera.look_at_from_position(camera_position, target + Vector3.UP * 0.75)
	await _capture_named(name)


func _capture_named(name: String) -> void:
	if DisplayServer.get_name() == "headless":
		return
	await process_frame
	await RenderingServer.frame_post_draw
	get_root().get_texture().get_image().save_png("user://actors-" + name + ".png")


func _check(passed: bool, description: String) -> void:
	if passed:
		_checks += 1
	else:
		_failed = true
		push_error("ACTOR_SMOKE FAIL " + description)


func _finish() -> void:
	if not _failed:
		print("ACTOR_SMOKE PASS ", _checks, " checks")
	quit(1 if _failed else 0)
