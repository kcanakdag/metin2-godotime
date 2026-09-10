extends RefCounted
## Merge validated client settings without exposing identity or server authority.


static func merge(path: String, settings: Dictionary) -> void:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not parsed is Dictionary:
		return
	for key: String in ["server_url", "database", "player_name"]:
		if parsed.get(key) is String and not str(parsed[key]).is_empty():
			settings[key] = parsed[key]
	if parsed.get("screen_wave_enabled") is bool:
		settings.screen_wave_enabled = parsed.screen_wave_enabled
	if (
		parsed.get("default_player_name") is String
		and not str(parsed.default_player_name).is_empty()
	):
		settings.player_name = parsed.default_player_name
