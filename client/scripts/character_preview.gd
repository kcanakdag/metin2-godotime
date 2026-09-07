extends Node3D

var current_clip := "wait"
var playing := true
var selected_weapon_vnum := 0
var motion_rows: Array[Dictionary] = []
var syncing_timeline := false

@onready var pivot: Node3D = $CameraPivot
@onready var camera: Camera3D = $CameraPivot/Camera3D
@onready var status: Label = $HUD/Margin/Column/Status
@onready var preview: Node3D = $Preview


func _ready() -> void:
	call_deferred("initialize_preview")


func initialize_preview() -> void:
	var initial: Dictionary = preview.snapshot()
	if not str(initial.get("error", "")).is_empty():
		status.text = str(initial.error)
	else:
		refresh_motion_selector("wait")
	$HUD/Margin/Column/Motion.item_selected.connect(select_motion)
	$HUD/Margin/Column/Equipment.pressed.connect(toggle_equipment)
	$HUD/Margin/Column/Pause.pressed.connect(toggle_playback)
	$HUD/Margin/Column/Timeline.value_changed.connect(scrub_timeline)
	$HUD/Margin/Column/Reset.pressed.connect(reset_view)
	camera.look_at(pivot.global_position)


func play_animation(clip: String) -> Dictionary:
	var manifest_action := "normal_attack" if clip == "attack" else clip
	if manifest_action == "normal_attack" and selected_weapon_vnum == 10:
		manifest_action = "combo_1"
	for index in motion_rows.size():
		if str(motion_rows[index].get("action", "")) == manifest_action:
			select_motion(index)
			return {"animation": clip, "state": preview.snapshot()}
	return {"error": "Animation unavailable: " + clip, "state": preview.snapshot()}


func refresh_motion_selector(preferred_action := "") -> void:
	motion_rows = preview.available_motions()
	var selector: OptionButton = $HUD/Margin/Column/Motion
	selector.clear()
	var selected := 0
	for index in motion_rows.size():
		var motion: Dictionary = motion_rows[index]
		var title := str(motion.get("action", "")).replace("_", " ").capitalize()
		if int(motion.get("sequence", 0)) > 0:
			title += " %d" % (int(motion.get("sequence", 0)) + 1)
		selector.add_item(title)
		if str(motion.get("action", "")) == preferred_action:
			selected = index
	if motion_rows.is_empty():
		status.text = "No manifest motions for this presentation."
		return
	selector.select(selected)
	select_motion(selected)


func select_motion(index: int) -> void:
	if index < 0 or index >= motion_rows.size():
		return
	$HUD/Margin/Column/Motion.select(index)
	var motion: Dictionary = motion_rows[index]
	if not preview.play_motion(motion):
		status.text = "Selected manifest motion is unavailable."
		return
	current_clip = str(motion.get("action", ""))
	playing = true
	status.text = (
		"Warrior · " + current_clip.replace("_", " ").capitalize() + " · generated profile"
	)
	$HUD/Margin/Column/Pause.text = "Pause animation  [Space]"
	$HUD/Margin/Column/Timeline.set_value_no_signal(0.0)


func toggle_equipment() -> void:
	selected_weapon_vnum = 10 if selected_weapon_vnum == 0 else 0
	if not preview.set_weapon(selected_weapon_vnum):
		selected_weapon_vnum = 0
		status.text = "Sword+0 presentation is unavailable."
		return
	$HUD/Margin/Column/Equipment.text = (
		"Presentation: Sword+0  [E]" if selected_weapon_vnum == 10 else "Presentation: Unarmed  [E]"
	)
	refresh_motion_selector("wait")


func toggle_playback() -> void:
	if preview.presentation == null:
		return
	var player: AnimationPlayer = preview.presentation.animation_player
	if not player:
		return
	playing = not playing
	if playing:
		player.play()
	else:
		player.pause()
	$HUD/Margin/Column/Pause.text = ("Pause" if playing else "Resume") + " animation  [Space]"


func scrub_timeline(value: float) -> void:
	if syncing_timeline or not preview.set_timeline_fraction(value):
		return
	playing = false
	$HUD/Margin/Column/Pause.text = "Resume animation  [Space]"


func _process(_delta: float) -> void:
	var actor_presentation = preview.presentation
	if actor_presentation == null:
		return
	var player: AnimationPlayer = actor_presentation.animation_player
	var duration := (
		float(int(actor_presentation.current_motion.get("duration_us", 0))) / 1_000_000.0
	)
	if player == null or duration <= 0.0:
		return
	syncing_timeline = true
	$HUD/Margin/Column/Timeline.value = clampf(
		player.current_animation_position / duration, 0.0, 1.0
	)
	syncing_timeline = false


func reset_view() -> void:
	pivot.rotation = Vector3.ZERO
	camera.position = Vector3(0.0, 1.25, -4.1)
	camera.look_at(pivot.global_position)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.is_mouse_button_pressed(MOUSE_BUTTON_RIGHT):
		pivot.rotation.y -= event.relative.x * 0.008
		pivot.rotation.x = clampf(pivot.rotation.x - event.relative.y * 0.006, -0.6, 0.7)
	if event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			camera.position *= 0.9 if camera.position.length() > 1.5 else 1.0
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			camera.position *= 1.1 if camera.position.length() < 10.0 else 1.0
	if event is InputEventKey and event.pressed and not event.echo:
		match event.keycode:
			KEY_1:
				play_animation("wait")
			KEY_2:
				play_animation("walk")
			KEY_3:
				play_animation("run")
			KEY_4:
				play_animation("attack")
			KEY_E:
				toggle_equipment()
			KEY_SPACE:
				toggle_playback()
			KEY_R:
				reset_view()
