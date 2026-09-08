extends "res://tests/actor_smoke.gd"
## Original equipped clips with candidate type-1 effect links, never installed by QA.

const WorldEffects = preload("res://scripts/world/world_motion_effects.gd")
var _requests := 0
var _mixed: Array = []
var _scenes: Dictionary = {}


func _run() -> void:
	root.size = Vector2i(1280, 800)
	if not _catalog.load_required(ActorCatalog.MANIFEST_PATH, true):
		_check(false, "skill effect actor catalog loads")
		_finish()
		return
	var effects: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string("res://effect-candidate/effects.v1.json")
	)
	var links: Array = JSON.parse_string(
		FileAccess.get_file_as_string("res://effect-candidate/links.json")
	)
	var textures: Dictionary = {}
	for path: String in effects.textures:
		textures[path] = ImageTexture.create_from_image(
			Image.load_from_file("res://effect-candidate/" + str(effects.textures[path].path))
		)
	if FileAccess.file_exists("res://mixed-candidate/catalog.json"):
		var mixed: Dictionary = JSON.parse_string(
			FileAccess.get_file_as_string("res://mixed-candidate/catalog.json")
		)
		_mixed.append(mixed)
		for mesh: Dictionary in mixed.meshes:
			_scenes[mesh.model] = load("res://mixed-candidate/" + str(mesh.model))
			for geometry: Dictionary in mesh.geometries:
				textures[geometry.texture] = load("res://mixed-candidate/" + str(geometry.texture))
		for path: String in mixed.textures:
			textures[path] = load("res://mixed-candidate/" + str(mixed.textures[path].path))
	_build_stage()
	_check(
		links.size() == (6 if _mixed.is_empty() else 8),
		"complete selected skills across both Warrior sexes"
	)
	for link: Dictionary in links:
		await _exercise(link, effects.effects, textures)
	_finish()


func _exercise(link: Dictionary, recipes: Array, textures: Dictionary) -> void:
	var actor := ActorPresentation.new()
	_check(actor.configure(_catalog, link.actor_id), "effect actor configures")
	_stage.add_child(actor)
	_check(actor.set_weapon(10), "effect actor equips original sword")
	actor.set_process(false)
	actor.animation_player.callback_mode_process = (
		AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	)
	var manager := WorldEffects.new()
	_stage.add_child(manager)
	_check(manager.configure(recipes, textures, _mixed, _scenes), "effect resources configure")
	_check(manager.bind_actor(actor, 180), "actor effect signal binds")
	_requests = 0
	actor.motion_effect_requested.connect(func(_event: Dictionary) -> void: _requests += 1)
	var action := str(link.actor_id) + ".general.skill_" + str(int(link.skill_vnum))
	var motion: Dictionary = _catalog.motion(link.actor_id, "general", action).duplicate(true)
	motion.effects = link.effects
	_check(actor._play_motion(motion, "general", 1, 0, 0, false, 1.0), "original skill starts")
	var peak := 0
	var sane := true
	var clean := true
	var frames := int(ceil(float(motion.duration_us) / 1000000.0 * 60)) + 30
	for frame: int in range(frames):
		actor.animation_player.advance(1.0 / 60)
		actor._process(1.0 / 60)
		clean = manager.advance(1.0 / 60, _camera) and clean
		peak = maxi(peak, manager._instances.size())
		sane = sane and _skeleton_pose_is_sane(actor) and _equipment_bounds_are_sane(actor)
		if int(link.skill_vnum) == 17 and frame == 65:
			await _capture_from(
				str(link.actor_id).get_slice(".", 2) + "-bash-burst",
				Vector3(5, 4, -8),
				Vector3(0, 1, -2)
			)
		if frame in [20, 50, 80]:
			var center := _skeleton_pose_center(actor)
			await _capture_from(
				(
					str(link.actor_id).get_slice(".", 2)
					+ "-effect-%s-%d" % [str(int(link.skill_vnum)), frame]
				),
				center + Vector3(2.0, 1.3, -4.0),
				center
			)
	_check(_requests == link.effects.size(), "all source events dispatched once")
	_check(peak > 0, "source events created render instances")
	_check(
		clean and manager.error_message.is_empty(), "animated attachment simulation has no errors"
	)
	if not manager.error_message.is_empty():
		print("EFFECT_ERROR " + manager.error_message)
	_check(sane, "equipped skill deformation remains bounded")
	actor.queue_free()
	await actor.tree_exited
	manager.queue_free()
	await process_frame
