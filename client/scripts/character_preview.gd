extends Node3D

var current_clip := "wait"
var playing := true

@onready var pivot: Node3D = $CameraPivot
@onready var camera: Camera3D = $CameraPivot/Camera3D
@onready var status: Label = $HUD/Margin/Column/Status
@onready var preview: Node3D = $Preview


func _ready() -> void:
	if preview.snapshot().has("error"):
		status.text = str(preview.snapshot().error)
	else:
		play_animation("wait")
	for button in $HUD/Margin/Column/Animations.get_children():
		if button is Button:
			button.pressed.connect(play_animation.bind(str(button.name).to_lower()))
	$HUD/Margin/Column/Pause.pressed.connect(toggle_playback)
	$HUD/Margin/Column/Reset.pressed.connect(reset_view)
	camera.look_at(pivot.global_position)


func play_animation(clip: String) -> Dictionary:
	if not preview.play_named(clip):
		return {"error": "Animation unavailable: " + clip, "state": preview.snapshot()}
	current_clip = clip
	playing = true
	status.text = "Warrior · " + clip.capitalize() + " · generated P1 profile"
	$HUD/Margin/Column/Pause.text = "Pause animation  [Space]"
	return {"animation": clip, "state": preview.snapshot()}


func toggle_playback() -> void:
	var player: AnimationPlayer = preview.presentation.animation_player
	if not player:
		return
	playing = not playing
	if playing:
		player.play()
	else:
		player.pause()
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
