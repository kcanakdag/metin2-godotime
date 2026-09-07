extends "res://scripts/map_preview.gd"
## Offline development world: static placement and original animation inspection.

var _report: Dictionary = {}
var _entries: Array[Node3D] = []
var _names: Array[String] = []
var _list: ItemList
var _details: Label


func _ready() -> void:
	super._ready()
	if not is_instance_valid(world):
		return
	_report = JSON.parse_string(FileAccess.get_file_as_string("res://world-content.json"))
	for row: Dictionary in _report.spawns:
		var actor: Dictionary = _report.actors[str(int(row.definition_vnum))]
		_add_actor(row, actor, "%s · spawn %s" % [actor.name, row.id])
	for row: Dictionary in _report.points:
		var actor: Dictionary = _report.npc_actors[row.actor_id]
		_add_actor(row, actor, str(actor.name))
	_inspector()
	_focus_entry(0)
	if "--population-smoke" in OS.get_cmdline_user_args():
		_smoke.call_deferred()


func _add_actor(row: Dictionary, actor: Dictionary, label_text: String) -> void:
	var pivot := Node3D.new()
	pivot.name = "Placement_%d" % _entries.size()
	add_child(pivot)
	pivot.position = Vector3(float(row.x), float(row.y), float(row.z))
	var model := (load(str(actor.path)) as PackedScene).instantiate() as Node3D
	pivot.add_child(model)
	var animation := model.find_children("*", "AnimationPlayer", true, false)[0] as AnimationPlayer
	animation.get_animation(actor.idle).loop_mode = Animation.LOOP_LINEAR
	animation.play(actor.idle)
	var label := Label3D.new()
	label.text = label_text
	label.position.y = 2.7
	label.font_size = 28
	label.pixel_size = 0.009
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.modulate = Color(0.4, 1.0, 0.65)
	pivot.add_child(label)
	_entries.append(pivot)
	_names.append(label_text)


func _inspector() -> void:
	var panel := PanelContainer.new()
	panel.position = Vector2(16, 170)
	panel.custom_minimum_size = Vector2(340, 290)
	$HUD.add_child(panel)
	var controls := VBoxContainer.new()
	panel.add_child(controls)
	var title := Label.new()
	title.text = "OFFLINE WORLD CONTENT"
	controls.add_child(title)
	_list = ItemList.new()
	_list.custom_minimum_size = Vector2(340, 180)
	for text: String in _names:
		_list.add_item(text)
	_list.item_selected.connect(_focus_entry)
	controls.add_child(_list)
	_details = Label.new()
	controls.add_child(_details)
	var note := Label.new()
	note.text = (
		"Select a spawn to inspect it.\nU: missing scenery · C: terrain attributes\n"
		+ "Edit profiles with tools/world_content.py.\nPreview actors do not simulate combat."
	)
	controls.add_child(note)


func _focus_entry(index: int) -> void:
	_list.select(index)
	focus = _entries[index].position + Vector3.UP
	camera.position = focus + Vector3(4, 4, -8)
	camera.look_at(focus)
	_details.text = (
		"%s\nX %.2f · Y %.2f · Z %.2f m" % [_names[index], focus.x, focus.y - 1.0, focus.z]
	)


func _process(delta: float) -> void:
	if is_instance_valid(get_viewport().gui_get_focus_owner()):
		return
	super._process(delta)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed:
		get_viewport().gui_release_focus()
	super._unhandled_input(event)


func _smoke() -> void:
	await get_tree().process_frame
	await get_tree().physics_frame
	var checks: Array = []
	checks.append(
		{
			"name": "declared_actors_loaded",
			"passed": _entries.size() == _report.spawns.size() + _report.points.size()
		}
	)
	for index in _entries.size():
		# Select through the actual ItemList input path, including its signal routing.
		_list.ensure_current_is_visible()
		var point := _list.global_position + _list.get_item_rect(index).get_center()
		for pressed: bool in [true, false]:
			var event := InputEventMouseButton.new()
			event.position = point
			event.button_index = MOUSE_BUTTON_LEFT
			event.pressed = pressed
			Input.parse_input_event(event)
		await get_tree().process_frame
		checks.append(
			{
				"name": "selection_focus_%d" % index,
				"passed": focus.is_equal_approx(_entries[index].position + Vector3.UP)
			}
		)
		var players := _entries[index].find_children("*", "AnimationPlayer", true, false)
		checks.append(
			{
				"name": "idle_animation_%d" % index,
				"passed": players.size() == 1 and players[0].is_playing()
			}
		)
	await get_tree().create_timer(0.3).timeout
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png("user://population-preview.png")
	var file := FileAccess.open("user://population-probe.json", FileAccess.WRITE)
	var passed := checks.all(func(row: Dictionary): return row.passed)
	file.store_string(
		JSON.stringify(
			{
				"passed": passed,
				"checks": checks,
				"map": map_name,
				"positions": _entries.map(func(node: Node3D): return str(node.position))
			},
			"\t"
		)
	)
	file.close()
	get_tree().quit(0 if passed else 1)
