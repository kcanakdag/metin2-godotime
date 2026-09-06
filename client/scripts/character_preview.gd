extends Node3D

var animation_player: AnimationPlayer
var clips: Dictionary = {}
var current_clip := "wait"
var playing := true

@onready var pivot: Node3D = $CameraPivot
@onready var camera: Camera3D = $CameraPivot/Camera3D
@onready var status: Label = $HUD/Margin/Column/Status
@onready var preview: Node3D = $Preview


func _ready() -> void:
	animation_player = find_animation_player(preview)
	if animation_player:
		for animation_name in animation_player.get_animation_list():
			var short_name := str(animation_name).replace(".", "_").get_slice("_", 1)
			if short_name in ["wait", "walk", "run", "attack"]:
				clips[short_name] = animation_name
				animation_player.get_animation(animation_name).loop_mode = Animation.LOOP_LINEAR
		play_animation("wait")
	else:
		status.text = "Warrior asset missing · run make assets, then make import-assets"
	for button in $HUD/Margin/Column/Animations.get_children():
		if button is Button:
			button.pressed.connect(play_animation.bind(str(button.name).to_lower()))
	$HUD/Margin/Column/Pause.pressed.connect(toggle_playback)
	$HUD/Margin/Column/Reset.pressed.connect(reset_view)
	camera.look_at(pivot.global_position)


func find_animation_player(node: Node) -> AnimationPlayer:
	if node is AnimationPlayer:
		return node
	for child in node.get_children():
		var found := find_animation_player(child)
		if found:
			return found
	return null


func play_animation(clip: String) -> Dictionary:
	if not clips.has(clip) or not animation_player:
		return {"error": "Animation unavailable: " + clip, "available": clips.keys()}
	current_clip = clip
	playing = true
	animation_player.play(clips[clip], 0.12)
	status.text = "Warrior · " + clip.capitalize() + " · 75 bones"
	$HUD/Margin/Column/Pause.text = "Pause animation  [Space]"
	return {"animation": clip, "available": clips.keys()}


func toggle_playback() -> void:
	if not animation_player or clips.is_empty():
		return
	playing = not playing
	if playing:
		animation_player.play()
	else:
		animation_player.pause()
	$HUD/Margin/Column/Pause.text = ("Pause" if playing else "Resume") + " animation  [Space]"


func reset_view() -> void:
	pivot.rotation = Vector3.ZERO
	camera.position = Vector3(2.4, 1.25, 3.6)
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
			KEY_SPACE:
				toggle_playback()
			KEY_R:
				reset_view()
