class_name ClassicSystemOptions
extends Control
## Small classic System Options panel for persistent presentation accessibility.

signal screen_wave_changed(enabled: bool)

const Art = preload("res://scripts/ui/classic_art.gd")

var screen_wave_enabled := true

var _screen_wave_button: TextureButton
var _screen_wave_caption: Label


func _ready() -> void:
	size = Vector2(220, 116)
	set_anchors_and_offsets_preset(Control.PRESET_CENTER, Control.PRESET_MODE_KEEP_SIZE)
	Art.board(self, size)
	Art.title(self, "System Options", 204, hide)
	_screen_wave_button = Art.button(
		self, "public/xlarge_button_", Vector2(20, 62), _toggle_screen_wave
	)
	_screen_wave_button.tooltip_text = "Enable or disable camera screen-wave effects."
	_screen_wave_caption = Art.label(_screen_wave_button, "", Vector2.ZERO)
	_screen_wave_caption.size = Vector2(180, 30)
	_screen_wave_caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_screen_wave_caption.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_refresh()
	hide()


func set_screen_wave_enabled(value: bool) -> void:
	screen_wave_enabled = value
	_refresh()


func snapshot() -> Dictionary:
	var center := Vector2.ZERO
	if is_instance_valid(_screen_wave_button):
		center = _screen_wave_button.get_global_rect().get_center()
	return {
		"visible": is_visible_in_tree(),
		"screen_wave_enabled": screen_wave_enabled,
		"screen_wave_center": [center.x, center.y],
	}


func _toggle_screen_wave() -> void:
	set_screen_wave_enabled(not screen_wave_enabled)
	screen_wave_changed.emit(screen_wave_enabled)


func _refresh() -> void:
	if is_instance_valid(_screen_wave_caption):
		_screen_wave_caption.text = (
			"Screen Wave: Enabled" if screen_wave_enabled else "Screen Wave: Disabled"
		)
