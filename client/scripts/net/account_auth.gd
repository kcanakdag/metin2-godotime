class_name AccountAuth
extends Node
## Minimal auth transport. Credentials and session tokens never enter UI snapshots.

signal token_ready(token: String)
signal failed(message: String)
signal status_changed(message: String)

## The web export mounts `user://` with Emscripten's IDBFS, and the engine drops a
## write-back requested while another one is running: `GodotFS.sync()` resolves
## immediately and reports "Already syncing!". Signing out therefore waits for the
## in-flight sync, then starts and awaits its own, so the deletion is durable before
## the caller leaves its busy state. `eval` without the global-context flag is a
## direct eval inside the engine's module closure, which is the only scope that can
## reach `GodotFS`; the completion marker travels through `globalThis`.
const WEB_FLUSH_SCRIPT := """
globalThis.__mt2UserFsFlushed = 0;
void (async () => {
	try {
		while (GodotFS._syncing) {
			await new Promise(resolve => setTimeout(resolve, 20));
		}
		await GodotFS.sync();
		globalThis.__mt2UserFsFlushed = 1;
	} catch (error) {
		globalThis.__mt2UserFsFlushed = -1;
	}
})();
"""
const WEB_FLUSH_READY := "globalThis.__mt2UserFsFlushed || 0"
const WEB_FLUSH_TIMEOUT_MS := 5000

var _base_url := ""
var _session_token := ""
var _session_path := ""
var _generation := 0
var _busy := false


func configure(endpoint: String, profile: String) -> void:
	_base_url = endpoint.trim_suffix("/") + "/auth"
	_session_path = ("user://accounts/%s.session" % (_base_url + "/" + profile).sha256_text())


func has_saved_session() -> bool:
	return not _session_path.is_empty() and FileAccess.file_exists(_session_path)


func login(username: String, password: String) -> void:
	await _authenticate(
		"/sign-in/username",
		{"username": username.strip_edges(), "password": password, "rememberMe": true}
	)


func register(username: String, email: String, password: String) -> void:
	await _authenticate(
		"/sign-up/email",
		{
			"username": username.strip_edges(),
			"name": username.strip_edges(),
			"email": email.strip_edges(),
			"password": password,
		}
	)


func resume() -> void:
	if _busy:
		return
	if _session_token.is_empty() and has_saved_session():
		_session_token = FileAccess.get_file_as_string(_session_path).strip_edges()
	if _session_token.is_empty():
		failed.emit("Log in to continue.")
		return
	_busy = true
	_generation += 1
	var generation := _generation
	status_changed.emit("Restoring your session…")
	await _issue_token(generation)
	if generation == _generation:
		_busy = false


func logout() -> void:
	_generation += 1
	var token := _session_token
	_forget_session()
	_busy = false
	if OS.has_feature("web"):
		await _await_web_filesystem_flush()
	if not token.is_empty():
		await _request("/sign-out", HTTPClient.METHOD_POST, {}, token)


func _authenticate(path: String, body: Dictionary) -> void:
	if _busy:
		return
	_busy = true
	_generation += 1
	var generation := _generation
	status_changed.emit("Signing in…" if path == "/sign-in/username" else "Creating your account…")
	var result := await _request(path, HTTPClient.METHOD_POST, body)
	if generation != _generation:
		return
	if not result.get("ok", false):
		_busy = false
		failed.emit(_failure_message(result, path == "/sign-in/username"))
		return
	_session_token = str(result.get("session", ""))
	if _session_token.is_empty():
		_busy = false
		failed.emit("The login service did not return a session. Please try again.")
		return
	_save_session()
	await _issue_token(generation)
	if generation == _generation:
		_busy = false


func _issue_token(generation: int) -> void:
	var result := await _request("/token", HTTPClient.METHOD_GET, {}, _session_token)
	if generation != _generation:
		return
	if not result.get("ok", false):
		if int(result.get("status", 0)) in [401, 403]:
			_forget_session()
		failed.emit(_failure_message(result, false))
		return
	var replacement := str(result.get("session", ""))
	if not replacement.is_empty():
		_session_token = replacement
		_save_session()
	var token := str(result.get("data", {}).get("token", ""))
	if token.is_empty():
		failed.emit("The login service did not return a game session. Please try again.")
		return
	token_ready.emit(token)


func _request(path: String, method: int, body: Dictionary, bearer := "") -> Dictionary:
	var request := HTTPRequest.new()
	request.timeout = 15
	request.body_size_limit = 65536
	request.max_redirects = 0
	add_child(request)
	var headers := PackedStringArray(["Content-Type: application/json"])
	if not OS.has_feature("web"):
		headers.append("Origin: " + _base_url.trim_suffix("/auth"))
	if not bearer.is_empty():
		headers.append("Authorization: Bearer " + bearer)
	var payload := JSON.stringify(body) if method != HTTPClient.METHOD_GET else ""
	var error := request.request(_base_url + path, headers, method, payload)
	if error != OK:
		request.queue_free()
		return {"ok": false, "status": 0}
	var response: Array = await request.request_completed
	request.queue_free()
	var status := int(response[1])
	var data: Variant = JSON.parse_string((response[3] as PackedByteArray).get_string_from_utf8())
	var result := {
		"ok": int(response[0]) == HTTPRequest.RESULT_SUCCESS and status >= 200 and status < 300,
		"status": status,
		"data": data if data is Dictionary else {},
	}
	for header: String in response[2]:
		if header.get_slice(":", 0).to_lower() == "set-auth-token":
			result["session"] = header.substr(header.find(":") + 1).strip_edges()
	return result


func _failure_message(result: Dictionary, signing_in: bool) -> String:
	var status := int(result.get("status", 0))
	if status == 0 or status >= 500:
		return "The login server is unavailable. Please try again."
	if status == 429:
		return "Too many attempts. Please wait a moment and try again."
	if signing_in:
		return "Username or password is incorrect."
	if status in [401, 403]:
		return "Your session has expired. Please log in again."
	return "Could not create the account. Check the username, email and password."


func _save_session() -> void:
	DirAccess.make_dir_recursive_absolute(
		ProjectSettings.globalize_path(_session_path.get_base_dir())
	)
	var file := FileAccess.open(_session_path, FileAccess.WRITE)
	if file:
		file.store_string(_session_token)
		file.close()
		if OS.get_name() not in ["Windows", "Web"]:
			FileAccess.set_unix_permissions(
				_session_path, FileAccess.UNIX_READ_OWNER | FileAccess.UNIX_WRITE_OWNER
			)
	_flush_web_filesystem()


func _forget_session() -> void:
	_session_token = ""
	if has_saved_session():
		DirAccess.remove_absolute(ProjectSettings.globalize_path(_session_path))
	_flush_web_filesystem()


## The browser build mounts `user://` from IndexedDB through Emscripten's IDBFS,
## which only writes back when the filesystem is synced. Godot's own syncs can
## trail a file change by seconds, so a reload right after signing out can read
## the deleted token back. Persist the change before the caller continues.
func _flush_web_filesystem() -> void:
	if not OS.has_feature("web"):
		return
	JavaScriptBridge.force_fs_sync()


## Signing out has to survive an immediate page reload, so the browser build
## waits for the IndexedDB write-back instead of assuming the engine's queued
## sync already ran. The caller keeps its "signing out" state until this returns.
func _await_web_filesystem_flush() -> void:
	JavaScriptBridge.eval(WEB_FLUSH_SCRIPT)
	var deadline := Time.get_ticks_msec() + WEB_FLUSH_TIMEOUT_MS
	while true:
		var state := _web_flush_state()
		if state > 0:
			return
		if state < 0:
			push_warning("The web export could not persist the cleared session.")
			return
		if Time.get_ticks_msec() >= deadline:
			push_warning("The web export did not persist the cleared session in time.")
			return
		await get_tree().process_frame


func _web_flush_state() -> int:
	var raw: Variant = JavaScriptBridge.eval(WEB_FLUSH_READY)
	if typeof(raw) == TYPE_INT or typeof(raw) == TYPE_FLOAT:
		return int(raw)
	return 0
