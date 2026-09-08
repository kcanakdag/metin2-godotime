extends CanvasLayer
## One viewport-local layout for ground names; controls never consume world input.

const GROUP := &"ground_item_labels"
const Art := preload("res://scripts/ui/classic_art.gd")
const GAP := 5.0
const MAX_ADJUSTMENTS := 20

var _entries: Dictionary = {}


func _ready() -> void:
	layer = 0


func _process(_delta: float) -> void:
	var camera := get_viewport().get_camera_3d()
	var viewport_rect := get_viewport().get_visible_rect()
	var seen: Dictionary = {}
	var occupied: Array[Rect2] = []
	for node in get_tree().get_nodes_in_group(GROUP):
		var source := node as Label3D
		if source == null or source.get_viewport() != get_viewport():
			continue
		var key := source.get_instance_id()
		seen[key] = true
		if not _entries.has(key):
			var label := Art.label(self, source.text, Vector2.ZERO, source.modulate)
			_entries[key] = {"source": source, "label": label, "was_visible": source.visible}
		var entry: Dictionary = _entries[key]
		var label: Label = entry.label
		source.hide()
		label.hide()
		if (
			camera == null
			or not source.get_parent().is_visible_in_tree()
			or source.text.is_empty()
			or camera.is_position_behind(source.global_position)
		):
			continue
		var anchor := camera.unproject_position(source.global_position)
		if not viewport_rect.has_point(anchor):
			continue
		if label.text != source.text:
			label.text = source.text
		if label.get_theme_color("font_color") != source.modulate:
			label.add_theme_color_override("font_color", source.modulate)
		label.size = label.get_combined_minimum_size()
		var rect := place(Rect2(anchor - Vector2(label.size.x * 0.5, 0), label.size), occupied)
		label.position = rect.position.round()
		label.show()
		occupied.append(Rect2(label.position, label.size))
	for key in _entries.keys():
		if not seen.has(key):
			_release(key)


func _exit_tree() -> void:
	for key in _entries.keys():
		_release(key)


func _release(key: int) -> void:
	var entry: Dictionary = _entries[key]
	if is_instance_valid(entry.source):
		entry.source.visible = entry.was_visible
	entry.label.queue_free()
	_entries.erase(key)


static func place(rect: Rect2, occupied: Array[Rect2]) -> Rect2:
	# Bounded downward displacement, using the original text-tail spacing.
	for _attempt in MAX_ADJUSTMENTS:
		var bottom := rect.position.y
		for other in occupied:
			if rect.intersects(other, true):
				bottom = maxf(bottom, other.end.y + GAP)
		if bottom == rect.position.y:
			break
		rect.position.y = bottom
	return rect
