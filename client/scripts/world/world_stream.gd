class_name WorldStream
extends Node3D
## Download immutable packs ahead of movement; the server remains authoritative.

signal progress(message: String)

const DIRECTORY := "res://assets/imported/maps/metin2_map_a1/chunks/"
var loaded: Dictionary = {}
var last_error := ""
var failure_message := "Scenery could not load. Reconnect to retry."
var _resource_uids = preload("res://scripts/world/stream_resource_uids.gd").new()
var _manifest: Dictionary = {}
var _mounted: Dictionary = {}
var _busy := false
var _active := false
var _focus := Vector2(660, 575)
var _elapsed := 0.0
var _content_hash := ""
var _asset_version := ""


func prepare(expected_hash: String) -> bool:
	_active = false
	while _busy:
		await get_tree().process_frame
	_busy = true
	last_error = ""
	failure_message = "Scenery could not load. Reconnect to retry."
	var result := await _prepare_content(expected_hash)
	_busy = false
	return result


func set_active(value: bool) -> void:
	_active = value


func _prepare_content(expected_hash: String) -> bool:
	if not _content_hash.is_empty() and _content_hash != expected_hash:
		last_error = "Map content changed; restart the client to update mounted resources."
		failure_message = "The map has changed. Refresh the page or restart the client to update."
		return false
	if OS.has_feature("web"):
		if not await _fetch_manifest(expected_hash):
			return false
		if not await _mount(_manifest.shared):
			return false
	else:
		var metadata: Variant = JSON.parse_string(
			FileAccess.get_file_as_string("res://assets/imported/maps/metin2_map_a1/collision.json")
		)
		if not metadata is Dictionary or metadata.get("content_sha256", "") != expected_hash:
			last_error = "Installed map differs from the server. Update the client."
			return false
	_content_hash = expected_hash
	return loaded.has("002002") or await _load_chunk("002002")


func _fetch_manifest(expected_hash: String) -> bool:
	var request := HTTPRequest.new()
	request.timeout = 30
	request.accept_gzip = false  # Browser Fetch already decompresses HTTP responses.
	request.body_size_limit = 65536
	add_child(request)
	var origin := str(JavaScriptBridge.eval("window.location.origin"))
	if request.request(origin + "/world/manifest.json") != OK:
		request.queue_free()
		last_error = "Could not request the map manifest."
		return false
	var result: Array = await request.request_completed
	request.queue_free()
	if result[0] != HTTPRequest.RESULT_SUCCESS or result[1] != 200:
		last_error = ("Map manifest download failed: result=%d HTTP=%d" % [result[0], result[1]])
		return false
	var parsed: Variant = JSON.parse_string(result[3].get_string_from_utf8())
	if (
		not parsed is Dictionary
		or parsed.get("version", 0) != 1
		or not parsed.get("shared") is Dictionary
		or not parsed.get("chunks") is Dictionary
	):
		last_error = "Map manifest is malformed."
		return false
	var asset_version := JSON.stringify(parsed).sha256_text()
	if not _mounted.is_empty() and _asset_version != asset_version:
		last_error = "Scenery updated. Refresh this page to load it."
		failure_message = last_error
		return false
	_manifest = parsed
	_asset_version = asset_version
	if str(_manifest.get("content_sha256", "")) != expected_hash:
		last_error = "Map version differs from the server. Refresh to update."
		progress.emit("Map version differs from the server. Refresh to update.")
		return false
	return true


func focus(point: Vector3) -> void:
	_focus = Vector2(point.x, point.z)


func ready_at(point: Vector3) -> bool:
	if not _active:
		return true
	return loaded.has("%03d%03d" % [int(point.x / 256), int(point.z / 256)])


func _process(delta: float) -> void:
	_elapsed += delta
	if not _active or _busy or _elapsed < 0.5:
		return
	_elapsed = 0
	_stream_neighbors()


func _stream_neighbors() -> void:
	_busy = true
	var gx := int(_focus.x / 256)
	var gz := int(_focus.y / 256)
	var neighbors: Array[Vector2i] = []
	for x in range(maxi(0, gx - 1), mini(3, gx + 1) + 1):
		for z in range(maxi(0, gz - 1), mini(4, gz + 1) + 1):
			neighbors.append(Vector2i(x, z))
	neighbors.sort_custom(
		func(a: Vector2i, b: Vector2i):
			if a == Vector2i(gx, gz):
				return a != b
			if b == Vector2i(gx, gz):
				return false
			return (
				(Vector2(a) * 256 + Vector2.ONE * 128).distance_to(_focus)
				< (Vector2(b) * 256 + Vector2.ONE * 128).distance_to(_focus)
			)
	)
	for grid: Vector2i in neighbors:
		var id := "%03d%03d" % [grid.x, grid.y]
		if not loaded.has(id):
			if not await _load_chunk(id):
				_elapsed = -4.5  # Back off failed downloads before retrying.
			break
	for id: String in loaded.keys():
		if absi(int(id.left(3)) - gx) > 1 or absi(int(id.right(3)) - gz) > 1:
			loaded[id].queue_free()
			loaded.erase(id)
	_busy = false


func _load_chunk(id: String) -> bool:
	if loaded.has(id):
		return true
	if OS.has_feature("web") and not await _mount_web_chunk(id):
		return false
	var path := DIRECTORY + id + ".tscn"
	if not ResourceLoader.exists(path):
		last_error = "Map chunk %s is missing from the client package." % id
		progress.emit("Map data is missing. Rebuild the map assets.")
		return false
	if OS.has_feature("web") and not _resource_uids.register_dependencies(path):
		last_error = _resource_uids.last_error
		return false
	var packed := load(path) as PackedScene
	if packed == null:
		last_error = "Map chunk %s could not be loaded." % id
		return false
	var chunk := packed.instantiate()
	add_child(chunk)
	loaded[id] = chunk
	progress.emit("")
	return true


func _mount_web_chunk(id: String) -> bool:
	if not _manifest.chunks.has(id):
		last_error = "Map manifest is missing chunk %s." % id
		return false
	return await _mount(_manifest.chunks[id])


func _mount(pack: Dictionary) -> bool:
	var hash_value := str(pack.get("sha256", ""))
	if _mounted.has(hash_value):
		return true
	if not RegEx.create_from_string("^[a-f0-9]{64}$").search(hash_value):
		last_error = "Map pack has an invalid content hash."
		return false
	var expected_bytes := int(pack.get("bytes", 0))
	if expected_bytes <= 0 or expected_bytes > 32 * 1024 * 1024:
		last_error = "Map pack has an invalid size."
		return false
	var directory := "user://world-cache"
	DirAccess.make_dir_recursive_absolute(directory)
	var path := directory + "/" + hash_value + ".pck"
	if FileAccess.file_exists(path) and FileAccess.get_sha256(path) != hash_value:
		DirAccess.remove_absolute(path)
	if not FileAccess.file_exists(path):
		if not await _download_pack(path, hash_value, expected_bytes):
			return false
	# Content packs cannot replace already mounted game scripts or resources.
	if not ProjectSettings.load_resource_pack(path, false):
		last_error = "Scenery pack could not be mounted: " + hash_value
		return false
	_mounted[hash_value] = true
	return true


func _download_pack(path: String, hash_value: String, expected_bytes: int) -> bool:
	progress.emit("Loading nearby scenery…")
	var request := HTTPRequest.new()
	request.timeout = 60
	request.accept_gzip = false
	request.download_chunk_size = 1024 * 1024
	request.body_size_limit = expected_bytes
	add_child(request)
	var origin := str(JavaScriptBridge.eval("window.location.origin"))
	if request.request(origin + "/world/" + hash_value + ".pck") != OK:
		request.queue_free()
		return false
	var response: Array = await request.request_completed
	request.queue_free()
	var body: PackedByteArray = response[3]
	if (
		response[0] != HTTPRequest.RESULT_SUCCESS
		or response[1] != 200
		or body.size() != expected_bytes
	):
		last_error = (
			"Scenery download failed: result=%d HTTP=%d bytes=%d"
			% [response[0], response[1], body.size()]
		)
		progress.emit("Scenery download failed. Reconnect to retry.")
		return false
	# Write explicitly: Web responses may have unknown length, for which the
	# engine's download_file cleanup can remove a successfully downloaded file.
	var file := FileAccess.open(path + ".part", FileAccess.WRITE)
	if file == null:
		last_error = "Unable to write scenery cache."
		return false
	file.store_buffer(body)
	file.close()
	if FileAccess.get_sha256(path + ".part") != hash_value:
		DirAccess.remove_absolute(path + ".part")
		last_error = "Scenery integrity check failed."
		return false
	if DirAccess.rename_absolute(path + ".part", path) != OK:
		last_error = "Unable to save scenery cache."
		return false
	return true
