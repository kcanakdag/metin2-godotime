extends SceneTree

const Layout := preload("res://scripts/ui/world_drop_labels.gd")
var _checks := 0
var _failures: Array[String] = []


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	root.size = Vector2i(800, 600)
	var world := Node3D.new()
	root.add_child(world)
	var camera := Camera3D.new()
	world.add_child(camera)
	camera.position = Vector3(0, 3, 8)
	camera.look_at(Vector3.ZERO)
	camera.current = true
	var overlay := Layout.new()
	world.add_child(overlay)
	var sources: Array[Label3D] = []
	for text in ["Red Potion (S)", "26 Yang", "Sword+0"]:
		var label := Label3D.new()
		label.text = text
		world.add_child(label)
		label.add_to_group(Layout.GROUP)
		sources.append(label)
	await process_frame
	overlay._process(0)
	_check("all co-located drops included", overlay.get_child_count() == 3)
	var rectangles: Array[Rect2] = []
	for label in overlay.get_children():
		_check("label visible", label.visible)
		_check("world clicks pass through", label.mouse_filter == Control.MOUSE_FILTER_IGNORE)
		for previous in rectangles:
			_check("co-located labels separated", not label.get_rect().intersects(previous, true))
		rectangles.append(label.get_rect())
	_check("world label replaced", not sources[0].visible)
	var original_position: Vector2 = overlay.get_child(0).position
	overlay._process(0)
	_check("stationary layout stable", overlay.get_child(0).position == original_position)
	camera.position.x += 1
	overlay._process(0)
	_check("camera movement reprojects", overlay.get_child(0).position != original_position)
	sources[0].text = "A much longer item name"
	overlay._process(0)
	_check("text update resizes", overlay.get_child(0).size.x > rectangles[0].size.x)
	sources[0].position = camera.position + camera.global_basis.z * 10
	overlay._process(0)
	_check("behind camera hidden", not overlay.get_child(0).visible)
	sources[0].position = Vector3(10000, 0, 0)
	overlay._process(0)
	_check("offscreen hidden", not overlay.get_child(0).visible)
	sources[0].position = Vector3.ZERO
	world.hide()
	overlay._process(0)
	_check("hidden world hides overlay", not overlay.get_child(1).visible)
	world.show()
	sources[2].free()
	overlay._process(0)
	await process_frame
	_check("removed drop cleaned up", overlay.get_child_count() == 2)
	var other_view := SubViewport.new()
	world.add_child(other_view)
	var foreign := Label3D.new()
	other_view.add_child(foreign)
	foreign.add_to_group(Layout.GROUP)
	overlay._process(0)
	_check("other viewport untouched", foreign.visible and overlay.get_child_count() == 2)
	root.size = Vector2i(640, 480)
	await process_frame
	overlay._process(0)
	_check("resize updates projection", overlay.get_child(0).position != original_position)
	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("user://drop-labels.png")
	overlay.free()
	_check("removing overlay restores fallback", sources[0].visible and sources[1].visible)
	var report := {"checks": _checks, "failures": _failures}
	var file := FileAccess.open("user://drop-labels.json", FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "\t"))
	print(JSON.stringify(report))
	world.free()
	quit(0 if _failures.is_empty() else 1)


func _check(label: String, passed: bool) -> void:
	_checks += 1
	if not passed:
		_failures.append(label)
