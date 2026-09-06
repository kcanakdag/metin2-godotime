# Godot MCP

The project includes [mkdevkit/godot-mcp](https://github.com/mkdevkit/godot-mcp)
at commit `328e15f7d38092371b2aca8b81c40b8188bbe747`, under its MIT license.
The editor addon and its Node.js server are both in this repository. They expose
173 tools for editor/runtime scene inspection, node properties, screenshots,
scene playback, scripts, simulated input, and other Godot operations. Core
workflows are exercised here; individual advanced tools have not all been tested.

## Installation and connection

```text
Codex → stdio MCP → local Node.js server → WebSocket → Godot editor addon
                                                       ↓
                                              running game bridges
```

The bridge binds **127.0.0.1:6505**. The Godot addon reconnects automatically.
One Node server owns that port at a time. This editor bridge is separate from the
SpacetimeDB gameplay connection: players do not need Node, Codex, or MCP.

The addon lives in `client/addons/godot_mcp` and is enabled in `project.godot`.
To install on another development machine:

```sh
make mcp-build
codex mcp add godot --env GODOT_MCP_PORT=6505 -- /absolute/path/to/node /absolute/path/to/mt2spacetime/tools/godot-mcp-server/build/index.js
codex mcp get godot
make editor
```

Use absolute executable and repository paths. On the original development
machine Node is `/home/kcan/.nvm/versions/node/v24.10.0/bin/node`. The
registration is named `godot`, uses stdio, and is enabled. `codex mcp get godot`
shows the effective configuration without dumping unrelated settings or tokens.
The CLI registration and configuration format are documented in the
[official OpenAI MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

After initial registration, restart/reconnect the Codex session if its tool list
has not refreshed. Registration on disk and callable tools in an already-open
session are separate checks. The standalone helper below can verify the real
integration even before an active session exposes `godot` tools. Do not start
that helper when Codex already owns the bridge port; use the connected tools.

In Godot, verify **Project → Project Settings → Plugins → Godot MCP** is enabled.
An editor that was already open when the addon was installed may need to reload
this project. The addon installs three runtime autoloads for scene inspection,
input, and screenshots. The previous temporary `MT2 Dev Bridge` is no longer used.

## Useful tools

| Tool | Purpose |
| --- | --- |
| `get_project_info` | Verify the exact connected checkout and Godot version |
| `get_scene_tree` | Inspect the scene open in the editor |
| `get_node_properties` | Read an editor node's properties |
| `get_editor_screenshot` | See the actual editor, viewport, docks, and inspector |
| `play_scene` with `mode: main` | Start the shared development world |
| `play_scene` with `mode: custom`, `scene_path: res://scenes/character_preview.tscn` | Start the asset/animation preview |
| `get_game_scene_tree` | Inspect the live game's nodes |
| `get_game_screenshot` | See the rendered client |
| `simulate_key` | Send a key press/release through the running game's input bridge |
| `execute_game_script` | Evaluate an expression against the running game |
| `stop_scene` | Stop the client |

For structured runtime observations use this expression:

```gdscript
get_tree().current_scene.dev_snapshot()
```

The main scene's snapshot includes connection state, players, and debug-menu
visibility. Use snapshots alongside screenshots and input checks. The snapshot
alone does not prove that an avatar is visible or that remote movement works.
The **F3** key toggles the debug menu; its Godot keycode is `4194334`.

The optional preview supports
`get_tree().current_scene.play_animation("attack")`. Its **1–4** keys select
wait/walk/run/attack. Despite their upstream names, `execute_game_script` and
`execute_editor_script` accept expressions, not arbitrary multiline programs.
The local runtime patch preserves primitive, array, and dictionary results as
structured JSON. Engine objects and other Godot-specific values become strings.
Do not wrap the expression in `JSON.stringify`: Godot's expression evaluator
cannot resolve arbitrary static class names such as `JSON`.

## Reproducible checks

`tools/godot_mcp_check.py` starts the actual Node MCP server and uses stdio
`initialize`, `tools/list`, and `tools/call`. It validates the editor's resolved
project path before sending the requested operation. It refuses an occupied port
and cleans up only its own Node child on normal exit, error, or interruption.

```sh
# Keep this project open in Godot. No other MCP server may own port 6505.
python3 tools/godot_mcp_check.py get_project_info
python3 tools/godot_mcp_check.py get_editor_screenshot
python3 tools/godot_mcp_check.py --smoke
python3 tools/godot_mcp_check.py --smoke --preview

# A single tool with explicit JSON arguments:
python3 tools/godot_mcp_check.py execute_game_script --args '{"code":"get_tree().current_scene.dev_snapshot()"}'
```

The default smoke starts the **main world**, verifies editor/runtime scene trees,
captures the editor and game, checks a world snapshot, simulates F3 and verifies
the changed debug visibility, captures the debug menu, then confirms stop and
restart. It can run without an available gameplay server; a disconnected world
is a valid editor-tooling test. Multiplayer verification has its own smoke test
and requires the real SpacetimeDB database.

`--smoke --preview` selects the character preview explicitly and verifies all
four clips plus simulated Run input. Generated warrior assets must exist for
that test. Both smoke modes intentionally stop the currently running scene and
leave the tested scene running at the end. Editor documents are not closed or
saved by the helper. On failure it leaves the current game visible for diagnosis.

Reports are `.local/mcp/report.json` and `.local/mcp/preview-report.json`.
Screenshots use readable names such as `world.png`, `debug.png`, `idle.png`, and
`run.png`; raw tool captures are also saved. The report records failure status
instead of presenting partial checks as success. Plain MCP text responses are
preserved; image blocks are decoded separately from text JSON.

When a scene on disk changes while the editor still holds an older copy,
preserve current work before invoking `reload_project`: that upstream tool
reloads the current edited scene as well as scanning the filesystem. The local
`services/scene_backup.gd` helper, exposed through
`MCPResourceUtils.backup_scene(editor_interface)`, packs the current scene and
copies every open text-script buffer into a unique `.local/editor-backups/`
directory. Its manifest records source paths and SHA-256 hashes. Verify those
files before reloading, and keep the backup when the old editor state differs
from the intended on-disk scene. The backup operation does not overwrite scene
files or save script buffers over their originals.

## Troubleshooting and release builds

- **Port already occupied:** use the existing Codex `godot` connection or close
  the standalone helper that you started. Do not kill an unknown process or
  launch another server on the same port. A different `--port` works only when
  the Godot addon is also configured to connect to that port.
- **Editor not connected:** confirm the correct project is open and the addon
  enabled. Inspect `.local/mcp/server.log` or the active Codex MCP status. The
  helper allows up to 75 seconds for reconnection; the local addon patch caps
  each reconnect delay at five seconds.
- **Runtime timeout:** the game must run graphically from this editor with its
  runtime bridges. Check Godot parse/runtime errors and whether the game's
  `user://` directory matches the editor. Headless checks and player exports do
  not service runtime MCP requests.
- **No image visible in an agent:** local patches return screenshots as MCP image
  content. The original server embedded base64 in text JSON. The standalone
  helper writes decoded images that can be opened with the agent's image viewer.

`tools/export_client.py` creates an isolated project copy and removes MCP addons,
plugin entries, and runtime autoloads automatically before exporting. It audits
the actual exported pack. Keep the addon enabled in the development editor;
there is no manual disable/re-enable step for the supported export workflow.
The gameplay SpacetimeDB SDK remains in the player build. Do not distribute a
manually exported development pack containing runtime script evaluation.

Other local patches queue atomic input batches so rapid press/release commands
reach the running game. Simulated keys also populate physical keycodes for WASD
polling. Mouse motion includes relative movement; `simulate_sequence` can hold
a mouse button using a `mouse_click` event with an explicit `pressed` field.
Clicks use separate press/release event objects so queued presses reach both
gameplay and GUI controls before release. The live controls audit exercised
ground-click movement, Space and button attacks, Enter/chat submission, camera
scroll/right drag, and F3; its report is `.local/mcp/controls-report.json`.
The running game must have focus for normal held movement, just as with a real
keyboard. Headless editors do not connect to MCP, and runtime
bridges are inactive in headless processes and release builds. See
`tools/godot-mcp-server/UPSTREAM.md` for pinned-source details and patch history.
