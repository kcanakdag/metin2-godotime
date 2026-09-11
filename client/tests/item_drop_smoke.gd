extends SceneTree

var _checks := 0
var _failures: Array[String] = []


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	root.size = Vector2i(1280, 800)
	var world := Node3D.new()
	root.add_child(world)
	var labels := preload("res://scripts/ui/world_drop_labels.gd").new()
	world.add_child(labels)
	var camera := Camera3D.new()
	world.add_child(camera)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-45, -25, 0)
	world.add_child(light)
	camera.position = Vector3(0, 5, 8)
	camera.look_at(Vector3(0, 0.5, 0))
	camera.current = true
	var vnums := [27001, 27002, 10]
	var names := ["Red Potion (S)", "Red Potion (M)", "Sword+0"]
	var actors: Array[PveActor] = []
	for index in vnums.size():
		var actor := PveActor.new()
		actor.loot_mode = true
		actor.item_mode = true
		world.add_child(actor)
		actor.apply_state({"id": index + 1, "vnum": vnums[index], "x": (index - 1) * 0.2})
		actors.append(actor)
		var state := actor.presentation_snapshot()
		_check("catalog name %d" % vnums[index], state.label == names[index])
		var has_ground := (
			index < 2
			and FileAccess.file_exists("res://assets/imported/ground_items/catalog.v1.json")
		)
		if has_ground:
			_check(
				"original ground model %d" % vnums[index], not state.ground_model_path.is_empty()
			)
			_check("billboard replaced %d" % vnums[index], not actor.get("_loot_icon").visible)
			actor.call("_process", 0.5)
			_check("ground model stays settled", actor.get("_visual").position == Vector3.ZERO)
		else:
			_check(
				"catalog icon %d" % vnums[index],
				str(state.icon_path).ends_with("%05d.png" % vnums[index])
			)
			_check("texture loaded %d" % vnums[index], actor.get("_loot_icon").texture != null)
	await process_frame
	labels._process(0)
	_check("all ground names use shared layout", labels.get_child_count() == 3)
	var occupied: Array[Rect2] = []
	for label in labels.get_children():
		_check("ground name visible", label.visible)
		for previous in occupied:
			_check("nearby ground names separated", not label.get_rect().intersects(previous, true))
		occupied.append(label.get_rect())
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png("user://item-drops.png")
	actors[0].apply_state({"id": 1, "vnum": 27002})
	_check("changed definition replaces label", actors[0].presentation_snapshot().label == names[1])
	_check(
		"changed definition replaces icon",
		(
			actors[0].presentation_snapshot().icon_path.ends_with("27002.png")
			or not actors[0].presentation_snapshot().ground_model_path.is_empty()
		)
	)
	actors[0].apply_state({"id": 1, "vnum": 999999})
	_check(
		"unknown item never borrows potion label",
		actors[0].presentation_snapshot().label == "Unknown item (999999)"
	)
	_check("unknown item clears prior texture", actors[0].get("_loot_icon").texture == null)
	_check("unknown item hides prior sprite", not actors[0].get("_loot_icon").visible)
	var gold := PveActor.new()
	gold.loot_mode = true
	world.add_child(gold)
	gold.apply_state({"id": 1, "gold": 27})
	_check(
		"Yang label remains authoritative amount", gold.presentation_snapshot().label == "27 Yang"
	)
	if FileAccess.file_exists("res://assets/imported/ground_items/catalog.v1.json"):
		_check(
			"Yang uses original coin model",
			not gold.presentation_snapshot().ground_model_path.is_empty()
		)
		_check("unknown item clears prior ground mesh", actors[0].get("_ground_model") == null)
		var policy = load("res://scripts/content/ground_item_catalog.gd").new()
		var document: Dictionary = JSON.parse_string(
			FileAccess.get_file_as_string("res://assets/imported/ground_items/catalog.v1.json")
		)
		_check("ground catalog validates", policy.load_document(document))
		var bad := document.duplicate(true)
		bad.items.append(bad.items[0])
		_check("duplicate ground vnum rejects", not policy.load_document(bad))
		_check("invalid reload clears old mappings", policy.scene(1) == null)
		bad = document.duplicate(true)
		bad.models.values()[0].path = "res://scripts/main.gd"
		_check("ground model cannot escape namespace", not policy.load_document(bad))
		var model_id: String = document.models.keys()[0]
		var shared := {"schema_version": 1, "models": document.models, "items": []}
		for vnum in range(1, 400):
			shared.items.append({"vnum": vnum, "model_id": model_id})
		_check(
			"hundreds of vnums may share one ground model",
			policy.load_document(shared) and policy.scene(399) != null and policy.scene(400) == null
		)
		shared.items = shared.items.slice(0, 399)
		shared.items.append({"vnum": 399, "model_id": model_id})
		_check("repeated vnum still rejects", not policy.load_document(shared))
	var report := {"checks": _checks, "failures": _failures}
	FileAccess.open("user://item-drops.json", FileAccess.WRITE).store_string(JSON.stringify(report))
	print(JSON.stringify(report))
	quit(0 if _failures.is_empty() else 1)


func _check(label: String, condition: bool) -> void:
	_checks += 1
	if not condition:
		_failures.append(label)
