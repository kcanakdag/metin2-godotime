# Godot MCP

Vendored from https://github.com/mkdevkit/godot-mcp at
`328e15f7d38092371b2aca8b81c40b8188bbe747` (MIT).

The matching editor add-on lives in `client/addons/godot_mcp`.
Local change: screenshot results are returned as MCP image content rather than
base64 embedded in JSON text, so vision-capable clients can inspect the image.
The matching add-on also caps reconnect delay at five seconds and fixes input
delivery from the editor to the game's autoload using atomic event batches.
Headless editors do not connect; runtime bridges are disabled in headless/release builds.
Runtime expression results preserve JSON-compatible primitives, arrays, and
dictionaries instead of coercing everything to Godot display strings. Engine
objects and other variants remain strings, with a depth limit for nested data.
This makes `get_tree().current_scene.dev_snapshot()` directly inspectable.
Synthetic keys include physical keycodes for held-input polling. Mouse moves
include relative motion, and explicit press/release events in sequences support
held mouse buttons while preserving the single-click tool's behavior.
Mouse clicks use distinct press/release event objects. Reusing and mutating a
queued press erased it before Godot consumed the event, breaking ground clicks,
UI buttons, and scroll input; the real-client controls audit covers all three.
`play_scene.user_args` temporarily sets Godot's `editor/run/main_run_args` for
one launch, while editor autosave is disabled. The add-on restores the exact
previous in-memory values (or absence) after Godot has consumed the launch or
when the command node leaves the tree. It never saves `ProjectSettings` or an
open scene, and rejects concurrent launches.
`services/scene_backup.gd` and `MCPResourceUtils.backup_scene` preserve the edited
scene and open text-script buffers in unique `.local/editor-backups` directories,
with a manifest and SHA-256 hashes, before a targeted scene reload is considered.
The backup does not overwrite the source scene or save editor buffers over files.

Build with `npm ci --ignore-scripts && npm run build`.
The MCP server uses stdio and listens for the Godot editor on `127.0.0.1:6505`.
Only one MCP server process should own that port at a time.
