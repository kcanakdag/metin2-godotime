class_name AccountAuth
extends Node
## Minimal auth transport. Credentials and session tokens never enter UI snapshots.

signal token_ready(token: String)
signal failed(message: String)
signal status_changed(message: String)

## Emscripten's IDBFS queues its write-backs, and a queued write carries a snapshot
## of the file it captured. A write-back of the token that was captured before the
## sign-out can therefore land *after* the deletion sync and put the file back,
## which is why one sync is never enough: signing out keeps forcing a write-back of
## the cleared state and reads the persisted store until the session file stays
## absent across consecutive reads. `indexedDB` is reachable from the engine's
## module closure, so no global execution context is needed; the result travels
## through `globalThis`.
##
## That write-back can also lose the race entirely, so the stored file is not the
## session's source of truth on its own. `localStorage` is written synchronously,
## which the browser persists before the next page load even when IndexedDB has not
## caught up yet, so the browser build records the signed-out state there and a
## reload refuses to restore a token this client already discarded.
const WEB_SESSION_PROBE_SCRIPT := """
globalThis.__mt2SessionPersisted = -1;
void (async () => {
	try {
		const request = indexedDB.open('/userfs');
		const root = await new Promise((resolve, reject) => {
			request.onsuccess = event => resolve(event.target.result);
			request.onerror = event => reject(event.target.error);
		});
		let present = 0;
		for (const name of Array.from(root.objectStoreNames)) {
			const keys = await new Promise((resolve, reject) => {
				const query = root.transaction(name, 'readonly').objectStore(name).getAllKeys();
				query.onsuccess = event => resolve(event.target.result);
				query.onerror = event => reject(query.error);
			});
			if (Array.from(keys).some(key => String(key).includes('.session'))) {
				present = 1;
			}
		}
		root.close();
		globalThis.__mt2SessionPersisted = present;
	} catch (error) {
		globalThis.__mt2SessionPersisted = -1;
	}
})();
"""
const WEB_SESSION_READY := "globalThis.__mt2SessionPersisted"
const WEB_SESSION_TIMEOUT_MS := 6000
const WEB_SESSION_SETTLE_MS := 200
const WEB_SESSION_PROBE_TIMEOUT_MS := 1000
const WEB_SESSION_CLEAN_READS := 3
## Signed-out marker keys are per endpoint and profile, so signing out of one
## server never hides a session kept for another.
const WEB_MARKER_PREFIX := "mt2.spacetime.signed-out."
const WEB_MARKER_WRITE := """
((key) => {
\ttry {
\t\tglobalThis.localStorage.setItem(key, '1');
\t\treturn 1;
\t} catch (error) {
\t\treturn 0;
\t}
})(%s)
"""
const WEB_MARKER_CLEAR := """
((key) => {
\ttry {
\t\tglobalThis.localStorage.removeItem(key);
\t\treturn 1;
\t} catch (error) {
\t\treturn 0;
\t}
})(%s)
"""
## A marker that cannot be read (private mode, blocked storage) reports -1 and the
## client falls back to the stored file instead of locking the player out.
const WEB_MARKER_READ := """
((key) => {
\ttry {
\t\treturn globalThis.localStorage.getItem(key) === '1' ? 1 : 0;
\t} catch (error) {
\t\treturn -1;
\t}
})(%s)
"""

var _base_url := ""
var _session_token := ""
var _session_path := ""
var _session_key := ""
var _generation := 0
var _busy := false


func configure(endpoint: String, profile: String) -> void:
	_base_url = endpoint.trim_suffix("/") + "/auth"
	_session_key = (_base_url + "/" + profile).sha256_text()
	_session_path = "user://accounts/%s.session" % _session_key
	if _signed_out() and _session_file_exists():
		# A signed-out client still found the token file, which is the queued
		# write-back that outran the deletion. Drop it again before the entry
		# screen can restore a session the player already discarded.
		_forget_session()


func has_saved_session() -> bool:
	return not _signed_out() and _session_file_exists()


func _session_file_exists() -> bool:
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
		await _await_web_session_removed()
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
		_clear_signed_out()
		if OS.get_name() not in ["Windows", "Web"]:
			FileAccess.set_unix_permissions(
				_session_path, FileAccess.UNIX_READ_OWNER | FileAccess.UNIX_WRITE_OWNER
			)
	_flush_web_filesystem()


## Called whenever this client stops owning a usable session: signing out, and an
## expired token the server rejected. The browser marker lands synchronously, so
## the next page load already knows not to trust a stored file.
func _forget_session() -> void:
	_session_token = ""
	_mark_signed_out()
	if _session_file_exists():
		DirAccess.remove_absolute(ProjectSettings.globalize_path(_session_path))
	_flush_web_filesystem()


func _signed_out_marker_key() -> String:
	return WEB_MARKER_PREFIX + _session_key


func _mark_signed_out() -> void:
	if not OS.has_feature("web") or _session_key.is_empty():
		return
	JavaScriptBridge.eval(WEB_MARKER_WRITE % JSON.stringify(_signed_out_marker_key()))


func _clear_signed_out() -> void:
	if not OS.has_feature("web") or _session_key.is_empty():
		return
	JavaScriptBridge.eval(WEB_MARKER_CLEAR % JSON.stringify(_signed_out_marker_key()))


func _signed_out() -> bool:
	if not OS.has_feature("web") or _session_key.is_empty():
		return false
	var raw: Variant = JavaScriptBridge.eval(
		WEB_MARKER_READ % JSON.stringify(_signed_out_marker_key())
	)
	if typeof(raw) != TYPE_INT and typeof(raw) != TYPE_FLOAT:
		return false
	return int(raw) == 1


## The browser build mounts `user://` from IndexedDB through Emscripten's IDBFS,
## which only writes back when the filesystem is synced. Godot's own syncs can
## trail a file change by seconds, so a reload right after signing out can read
## the deleted token back. Persist the change before the caller continues.
func _flush_web_filesystem() -> void:
	if not OS.has_feature("web"):
		return
	JavaScriptBridge.force_fs_sync()


## Signing out has to survive an immediate page reload, so the browser build keeps
## forcing a write-back of the cleared state and confirms against IndexedDB that
## the session file is gone. The caller keeps its "signing out" state until this
## returns, so the login screen is never shown while the token is still readable.
func _await_web_session_removed() -> void:
	var deadline := Time.get_ticks_msec() + WEB_SESSION_TIMEOUT_MS
	var clean_reads := 0
	while clean_reads < WEB_SESSION_CLEAN_READS:
		if Time.get_ticks_msec() >= deadline:
			push_warning("The web export did not persist the cleared session in time.")
			return
		JavaScriptBridge.force_fs_sync()
		await get_tree().create_timer(WEB_SESSION_SETTLE_MS / 1000.0).timeout
		if await _web_session_absent():
			clean_reads += 1
		else:
			clean_reads = 0


func _web_session_absent() -> bool:
	JavaScriptBridge.eval(WEB_SESSION_PROBE_SCRIPT)
	var deadline := Time.get_ticks_msec() + WEB_SESSION_PROBE_TIMEOUT_MS
	while Time.get_ticks_msec() < deadline:
		var state := _web_session_state()
		if state >= 0:
			return state == 0
		await get_tree().process_frame
	return false


func _web_session_state() -> int:
	var raw: Variant = JavaScriptBridge.eval(WEB_SESSION_READY)
	if typeof(raw) == TYPE_INT or typeof(raw) == TYPE_FLOAT:
		return int(raw)
	return -1
