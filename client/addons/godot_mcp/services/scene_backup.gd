@tool
extends RefCounted
## Preserve current editor work before explicitly reloading a changed scene.


func backup(editor: EditorInterface) -> Dictionary:
	var root := editor.get_edited_scene_root()
	if root == null:
		return {"error": "No scene is currently open."}
	var repository := ProjectSettings.globalize_path("res://").get_base_dir().get_base_dir()
	var directory := repository.path_join(".local/editor-backups/%d-%d" % [
		int(Time.get_unix_time_from_system() * 1000000), OS.get_process_id()
	])
	if DirAccess.dir_exists_absolute(directory):
		return {"error": "Backup directory already exists; refusing to overwrite."}
	var error := DirAccess.make_dir_recursive_absolute(directory)
	if error != OK:
		return {"error": "Cannot create backup directory: %d" % error}
	var packed := PackedScene.new()
	error = packed.pack(root)
	if error != OK:
		return {"error": "Cannot pack current scene: %d" % error}
	var scene_path := directory.path_join("scene.tscn")
	error = ResourceSaver.save(packed, scene_path)
	if error != OK:
		return {"error": "Cannot save current scene backup: %d" % error}
	var buffers: Array = []
	var index := 0
	for script_editor in editor.get_script_editor().get_open_script_editors():
		var control := script_editor.get_base_editor()
		if not control is TextEdit:
			continue
		var buffer_path := directory.path_join("script-buffer-%d.txt" % index)
		var file := FileAccess.open(buffer_path, FileAccess.WRITE)
		if file == null:
			return {"error": "Cannot save an open script buffer.", "scene_backup": scene_path}
		file.store_string(control.text)
		file.close()
		var source := ""
		if script_editor.has_method("get_edited_resource"):
			var resource: Resource = script_editor.call("get_edited_resource")
			if resource:
				source = resource.resource_path
		buffers.append({"source": source, "backup": buffer_path, "sha256": FileAccess.get_sha256(buffer_path)})
		index += 1
	var result := {
		"scene_source": root.scene_file_path,
		"scene_name": root.name,
		"scene_backup": scene_path,
		"scene_sha256": FileAccess.get_sha256(scene_path),
		"script_buffers": buffers,
	}
	var manifest := FileAccess.open(directory.path_join("manifest.json"), FileAccess.WRITE)
	if manifest == null:
		return {"error": "Cannot save backup manifest.", "scene_backup": scene_path}
	manifest.store_string(JSON.stringify(result, "\t"))
	manifest.close()
	return result
