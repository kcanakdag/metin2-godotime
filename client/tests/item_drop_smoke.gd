extends SceneTree

var _checks := 0
var _failures: Array[String] = []


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	root.size = Vector2i(1280, 800)
	var world := Node3D.new()
	root.add_child(world)
	var camera := Camera3D.new()
	world.add_child(camera)
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
		actor.apply_state({"id": index + 1, "vnum": vnums[index], "x": (index - 1) * 2.0})
		actors.append(actor)
		var state := actor.presentation_snapshot()
		_check("catalog name %d" % vnums[index], state.label == names[index])
		_check(
			"catalog icon %d" % vnums[index],
			str(state.icon_path).ends_with("%05d.png" % vnums[index])
		)
		_check("texture loaded %d" % vnums[index], actor.get("_loot_icon").texture != null)
	await process_frame
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png("user://item-drops.png")
	actors[0].apply_state({"id": 1, "vnum": 27002})
	_check("changed definition replaces label", actors[0].presentation_snapshot().label == names[1])
	_check(
		"changed definition replaces icon",
		actors[0].presentation_snapshot().icon_path.ends_with("27002.png")
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
	var report := {"checks": _checks, "failures": _failures}
	FileAccess.open("user://item-drops.json", FileAccess.WRITE).store_string(JSON.stringify(report))
	print(JSON.stringify(report))
	quit(0 if _failures.is_empty() else 1)


func _check(label: String, condition: bool) -> void:
	_checks += 1
	if not condition:
		_failures.append(label)
