extends SceneTree

const ACTOR_DIRECTORY := "res://assets/imported/content/p0-warrior-dog/actors"


func _init() -> void:
	var checked := 0
	for name in DirAccess.get_files_at(ACTOR_DIRECTORY):
		if not name.ends_with(".png"):
			continue
		var path := ACTOR_DIRECTORY.path_join(name)
		var source := Image.load_from_file(path)
		var texture := load(path) as Texture2D
		if source.is_empty() or texture == null:
			fail("could not load %s" % path)
		var imported := texture.get_image()
		source.convert(Image.FORMAT_RGBA8)
		imported.convert(Image.FORMAT_RGBA8)
		imported.clear_mipmaps()
		if source.get_size() != imported.get_size() or source.get_data() != imported.get_data():
			fail("lossless imported pixels differ for %s" % path)
		checked += 1
	if checked == 0:
		fail("no selected actor PNGs found")
	print("ACTOR_TEXTURE_IMPORT PASS %d textures" % checked)
	quit(0)


func fail(message: String) -> void:
	push_error(message)
	quit(1)
