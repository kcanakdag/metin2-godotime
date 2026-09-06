# Development workflow

Run commands from the repository root. The game uses standard Godot with
GDScript and a Rust SpacetimeDB module. Python runs development and asset tools;
Node runs the local Godot MCP server. None of these Python/Node development
dependencies belong in a player's client build.

## Install the quality tools

Use Python 3.12 or newer. This creates an ignored virtual environment at
`.local/venv-dev` and installs the exact versions in
`tools/requirements-dev.txt`; activating the environment is optional.

```sh
python3 tools/dev.py setup
rustup component add rustfmt clippy
rustup target add wasm32-unknown-unknown
make mcp-build
```

`setup` installs Python packages locally; the two `rustup` commands add
components to your selected Rust toolchain. `make mcp-build` uses the existing
NPM lockfile with `npm ci` and builds the TypeScript MCP server. Python setup and
NPM installation need network access on a fresh machine. They do not install
Blender or Godot; see the root README for game and asset requirements.

The pinned tools are [Ruff 0.15.22](https://pypi.org/project/ruff/0.15.22/) and
[gdtoolkit 4.5.0](https://pypi.org/project/gdtoolkit/4.5.0/). gdtoolkit is an
independent Godot 4 parser/linter/formatter; it does not replace the actual
Godot engine's import and runtime checks. Upgrade tool versions deliberately,
including transitive pins, and run the checks before accepting formatter changes.

The normal setup also includes `tools/requirements-assets.txt`, pinning
**Pillow 12.1.0** for original raster UI conversion. Re-run `make dev-setup` after
updating this checkout to install that added dependency in `.local/venv-dev`.
It is a development tool, not a dependency in the exported game.

`tools/gdtoolkit_local.py` relocates gdtoolkit's parser cache to
`.cache/gdtoolkit`. Its pinned upstream version otherwise writes to the user's
home cache even during read-only checks and does not honor `XDG_CACHE_HOME`.
This small adapter leaves the installed package and the home directory unchanged.

## Checks and formatting

```sh
python3 tools/dev.py lint
# Or just one area during iteration:
python3 tools/dev.py lint --only gdscript
python3 tools/dev.py lint --only python
python3 tools/dev.py lint --only rust
python3 tools/dev.py lint --only typescript

# Apply formatting and Ruff safe fixes to owned code:
python3 tools/dev.py format
make check
make test-tools              # Python tooling tests, including real loopback sockets
```

The lint runner returns a failure if any requested check fails or a required tool
is missing. It continues through independent groups so one failure does not hide
the rest. It never installs packages as a side effect of checking. Formatting is
explicit and may still leave findings that require a code change.

| Scope | Checks | Configuration |
| --- | --- | --- |
| Owned Python under `tools/` and `tests/` | Ruff correctness/import/bug checks and formatter | `pyproject.toml` |
| Owned `.gd` files under `client/` and `tools/`, recursively | gdformat and gdlint | `gdlintrc`, 100 columns |
| Rust server | rustfmt; clippy for all targets and features, warnings as errors | `server/Cargo.toml`, `server/Cargo.lock` |
| Godot MCP TypeScript server | Strict TypeScript type check with no output | Its existing `tsconfig.json` and `package-lock.json` |

The checker excludes all Godot `addons/` directories, generated data, dependency
directories, and downloaded source trees. This includes the vendored Godot MCP
and SpacetimeDB SDK. The latter is a game dependency and must remain in client
exports. The MCP addon is developer tooling and must be excluded from player
exports. TypeScript keeps its upstream formatting; its local patches still pass
the strict compiler. `.editorconfig` supplies LF endings, tabs for Godot files,
and consistent indentation in supporting files.

The Python importer has one explicit `E402` exception because it must put the
pinned Carbon modules on Blender's import path before importing them. Do not
expand this exception to other tools. Ruff's standard undefined-name and unused
import checks still run. Explain narrow exclusions and keep failures visible.

`make check` complements static checks with the project's test/build/import
commands. Inspect its output; passing formatting does not prove networking,
animation fidelity, server behavior, or a working Windows export.

Rust checks include the `yongan` feature, which embeds ignored generated content.
Run `make import-map` and `make bake-map` after asset setup before the full check.
`make server-test` also selects Yongan by default. To test the smaller training
variant independently, use `make server-test SERVER_FEATURES=`. Missing baked
content is a setup failure, not a reason to disable Yongan checking.

The gateway tests bind ephemeral loopback ports and exercise real HTTP and
WebSocket traffic against a fake upstream. Run them with local socket access;
a sandbox denying socket creation cannot execute those integration checks.
The launcher tests cover ownership validation and cleanup without creating a
public tunnel. For actual remote sessions, follow [Internet playtesting](playtesting.md).

## Iterating on the shared map

Start the local database and publish using the README commands. Give disposable
tests a separate database name and data directory; do not reset someone else's
development state. Run two clients with distinct identity profiles and connect
both to the same endpoint/database.

The Make defaults are `SERVER_FEATURES=yongan`, `DB=mt2-yongan-v2` and
`SERVER_URL=http://127.0.0.1:3210`. Publish to a disposable database before live
network/gameplay checks:

```sh
make server-publish DB=mt2-yongan-test
make test-multiplayer DB=mt2-yongan-test
make test-combat DB=mt2-yongan-test
make test-inventory DB=mt2-yongan-test
```

The tests create real guest characters and act on the selected world. The combat
test exercises monster/player damage, attack rejection, death/respawn, reward
reservation, duplicate pickup rejection and retained gold. Use separate data
directories when starting disposable SpacetimeDB processes, and do not reuse a
port occupied by the development server. An empty `SERVER_FEATURES=` selects
training for Make's server build/test/publish commands; raw Cargo defaults to
training too.

The inventory suite uses `client/tests/inventory_smoke.gd` and writes
`.local/inventory-report.json`. It is intended to exercise starter initialization,
ownership rejection, page/footprint collision, equipment effects, potion limits,
reserved/distant/duplicate item pickups and persistence through death/reconnect.
Run it against the freshly published additive inventory schema, not an older
baseline database. Inspect its actual report before describing any path as tested.

For gameplay or networking changes, verify that both clients show both players,
that each player's movement reaches the server and the other client, and that
presence disappears after disconnect. Verify reconnect when changing lifecycle
code. Reducer validation belongs on the server even when the UI already limits
input. Tests should exercise rejected input and identity/presence boundaries,
not merely compare a helper's output to an identical implementation.

The development scene exposes `dev_snapshot()` for runtime inspection. Use it
alongside scene-tree and screenshot checks; a plausible snapshot does not prove
the character is visible or the input controls work. Debug controls should call
normal server reducers. Adding privileged controls requires an explicit
server-side permission model.

## Working with the editor

Use the configured `godot` MCP tools for live changes. Confirm `get_project_info`
points to this checkout, inspect the edited scene, start the game, inspect its
runtime tree, capture the rendered game, and exercise the input you changed.
Capture another screenshot after UI/camera/material changes. Preserve unrelated
open scenes and unsaved work. See [Godot MCP setup](godot-mcp.md) for installation
and troubleshooting.

Do not run `tools/godot_mcp_check.py` while another MCP process owns its port. That
standalone test launches its own server. Prefer the connected agent tools during
an active session. Keep bridge listeners local and exclude runtime script
evaluation/input injection from the exported player client.

## Assets and builds

`make import-map BLENDER=/path/to/blender` reconstructs the original Yongan
inspection scene and section scenes. `make bake-map BLENDER=/path/to/blender`
then reads the original height/attribute/collision sources, writes the shared
server data and client collision metadata, and reassembles playable sections
with terrain and authored walk-surface colliders. Rebuild/publish the server and
re-export clients after a changed bake so their content hashes agree.

`make map-preview` opens the separate inspector; `make test-map` checks the pure
formats and generated resources/placements with Godot. The importer also runs
resource checks itself. Web exports additionally run all 20 sections through
`tools/check_world_packs.py` in fresh engine processes with only their shared
and individual packs. `make test-world-packs WEB_DIR=dist/web` reruns this audit,
including exact tile-ID/attribute bytes and texture dependencies.
See [map importing](map-import.md) for cache/offline
behavior, strict status, unsupported assets, controls and evidence. Keep authored
changes outside generated output. Preview camera movement is independent of
server-authoritative gameplay.

Use `make assets` and `make import-assets` for the pinned warrior fixture. The
source manifest records commits and file hashes; conversion reports go in
`.local/`. Changing the converter requires checking real deformation and viewing
the result in Godot. Downloaded assets and converted output are ignored so they
can be regenerated; they are not hand-maintained game source.

Use `make import-ui` after `make dev-setup` for the selected original HUD,
inventory, item icons and stitched Yongan minimap. This converts 159 UI images
and 20 original DDS map tiles from 207 pinned source files with Pillow; Blender
is unnecessary for these raster assets. For a cached rebuild and format tests:

```sh
.local/venv-dev/bin/python tools/import_metin_ui.py --offline
.local/venv-dev/bin/python -m unittest discover -s tests -p test_metin_ui.py
```

Converted output and its hash/provenance manifest live in ignored
`client/assets/imported/ui/`. The importer preserves decoded pixels and alpha,
validates atlas/crop rules and never executes downloaded original client code.
See [UI assets](ui-assets.md) for mappings and layout references. Verify the
actual Godot layout, icon sizes, mouse carry/drag, right-click actions, page
changes, quickslots and chat focus after UI changes. Conversion tests alone do
not prove usable UI or original-client parity.

The isolated presentation runner supports `ui`, `map` and `chat` suites. Give
each its own output directory so one report cannot overwrite another:

```sh
make test-ui UI_FLAGS="--suite ui --native --output .local/classic-panels-ui"
make test-ui UI_FLAGS="--suite map --native --output .local/classic-map"
make test-ui UI_FLAGS="--suite chat --native --output .local/classic-chat"
```

Omit `--native` for a headless run; native rendering uses `xvfb-run` and saves a
PNG. The runner stages UI sources/art plus the selected smoke script in an
isolated Godot project, without network SDK, editor bridge or saved identity.
These checks verify input, layout and emitted intents; only the live multiplayer
checks establish server acceptance and subscriptions. Current local evidence
includes 15 UI, 17 map and 22 chat checks with native screenshots. Reports are
in `.local/classic-panels-ui/`, `.local/classic-map/` and `.local/classic-chat-final/`.

`make import-ui` also records each image's decoded RGBA SHA-256 and pins lossless
texture import without mipmaps, automatic 3D compression or alpha-border fixes.
The actual export audit loads every UI texture from its PCK and compares pixels
against that hash, including the stitched map. Re-export after importer changes;
inspecting only a source PNG does not establish the exported texture's fidelity.

Before sharing a client, execute the real export workflow, check that required
SDK libraries/assets are included and MCP tooling/tokens are absent, then run
the export against the configured server. The friend's machine must be able to
reach that endpoint; localhost on one computer does not point to another
computer. Record what platform and network path were actually tested. Do not
describe a Linux run or a generated `.exe` as verified Windows execution.

Keep asset and code provenance in [third-party sources](third-party.md).
The original assets, GPL reference server code, and MIT import/editor tooling
have separate terms. Record source and license when adapting external resources.

## Browser integration checks

Install matching Godot 4.7.2 Web/Linux export templates and an actual Chrome
browser. The optional runner also needs `xvfb-run` for the rendered Linux client
and the pinned packages in `tools/requirements-browser.txt`:

```sh
make browser-setup
make export-web TEST_PROBE=--test-probe DB=mt2-yongan-test
make export-linux TEST_PROBE=--test-probe DB=mt2-yongan-test
```

These write `dist/web-test/` and `dist/linux-test/`. Host the test Web directory
with the configured database's HTTPS/WSS routes, then run:

```sh
make test-browser PUBLIC_URL=https://YOUR_TEST_HOST:8443 DB=mt2-yongan-test
```

For a visible browser using the workstation's GPU, add `BROWSER_FLAGS=--hardware`.
This requires an available graphical session. The default headless SwiftShader
path can render Yongan too slowly for timing-sensitive combat checks; report its
functional results separately from a real GPU playtest.

For the original inventory interaction slice, use:

```sh
make test-browser PUBLIC_URL=https://YOUR_TEST_HOST:8443 DB=mt2-yongan-test \
  BROWSER_FLAGS="--hardware --inventory"
```

`--inventory` adds mouse/keyboard inventory and quickslot checks to the browser
runner. It requires newly exported test clients containing the classic UI and
the matching inventory schema. The exported interface is exercised through
mouse/key input; a helper calling reducers directly is separate server evidence.
Verify reconnect and browser refresh preserve item state and local quickslots.
Adding `--combat` also checks quickslot consumption after monster damage and
collecting the potion drop with Z. The 2026-09-06 public run passed 39 checks:
`.local/browser-proof/20260906-165921/report.json`. It used independent Chrome
and Linux export identities, real mouse/keyboard UI actions and the workstation
GPU, and recorded no engine errors. Cold world readiness was 15.98 seconds;
the final combat sample was 59 FPS. These timings describe this run only.

Add `--panels` to test original minimap close/reopen/zoom, atlas opening/dragging/
closing, chat focus and chat-history dragging/resizing with actual browser
mouse/key input. Scrolling is covered by the native chat suite. This requires
exports containing the new panel code.
The new panel export passed both loopback and public checks. The latest public
run in `.local/browser-proof/20260906-174806/report.json` passes 45 core/panel/
inventory checks with independent Chrome/Linux clients and no browser engine
errors. It checks final drag positions and the chat log's final 530 × 210 size,
so an intermediate drag snapshot cannot count as completion. It sends no public
chat; the delivery and post-send movement proof remains the loopback run below.

The chat-focus regression exercises native and browser clients: send from the
bottom-center field, close it with Escape, and dismiss it by clicking the world.
Each path releases both chat fields, leaves ordinary entry closed and lets
WASD reach the server and the other client's avatar. Sending from chat history
also releases focus while retaining its visible window.
Consuming the submit Enter before releasing focus prevents the same event from
reopening chat through the world shortcut. Keep this evidence distinct from
older UI tests that expected continued editing after send; the return-to-game
behavior follows the player's later request.

For synthetic chat delivery checks, `--chat-focus` accepts only URL hostnames
`127.0.0.1`, `localhost` or `::1`. Serve matching test exports and the test
database's routes on loopback first, then run, for example:

```sh
make test-browser PUBLIC_URL=http://127.0.0.1:8182 DB=mt2-yongan-test \
  BROWSER_FLAGS="--hardware --panels --chat-focus"
```

The restriction prevents synthetic chat from reaching public players. The
loopback run in `.local/browser-proof/20260906-174144/report.json` passed all
45 checks with independent Chrome/Linux identities and no browser engine errors.
It covers the focus paths, panel interactions, actual message replication,
rejection, disconnect/reconnect and refresh. Before recording the reconnect
position, the runner waits for both subscribed movement to stop and the rendered
avatar to settle. Cold world readiness was 8.82 seconds and one final sample
was 21 FPS; these are observations from that run, not a benchmark.

The current public development release `20260906T154235134255Z` retains the
fixed test probe with the user's explicit authorization. Its Web/Linux PCK
audits checked 582/1,385 files and all 160 exact RGBA UI/map images, with no MCP
bridge, runtime script evaluator, identity tokens or source archives. The served
manifest in `.local/classic-panels-served-manifest.json` equals the Web export's
manifest; deployment output is `.local/classic-chat-map-deploy.log`.

The public run reached the world in 12.52 seconds with a final sample of 42 FPS;
these are observations on this workstation, not a performance guarantee.
Native editor inspection confirmed the connected project, opened bottom-center
chat, and observed Escape clearing focus and hiding entry; its screenshot is
`.local/classic-chat-native-editor/centered-chat.png`. The final tool suite has
70 passing tests and all lint groups pass. Normal exports exclude the fixed
probe; inspect those separately before friend/release delivery.

The Web build connects to its page origin and the database baked into its config.
The Linux export receives the same endpoint/database from the runner. Publishing
a test build to the development VPS requires explicit
`WEB_DIR=dist/web-test DEPLOY_FLAGS=--allow-test-build`; see
[distribution](distribution.md). Run this against an isolated test world where
possible. A default player build contains no probe, so it cannot satisfy this
instrumented test runner.

The runner uses Playwright with installed Chrome and a rendered exported Linux
client. It reads real scene-avatar state through a test-only probe, sends normal
validated actions, captures screenshots, and checks both directions of movement,
presence, rejection, reconnect and browser refresh. Reports go under
`.local/browser-proof/<timestamp>/`. A partial report is retained on failure;
the presence of a report file alone does not indicate a pass. Its software
rendering path is functional evidence, not a consumer-GPU performance benchmark.

For the original small training-ground proof, build/publish with
`SERVER_FEATURES=` and export with `INCLUDE_MAP=` to omit Yongan. Keep its database
and reports distinct from Yongan evidence. Exporting Linux or Web with
`--test-probe` adds only the explicit local test interface; normal exports remove
all `client/tests/` sources and MCP bridges.

## Deploying an update

Build the selected server, export a normal Web client, then run `make deploy`.
This deploys only `/opt/metin2-godotime` and Compose project `metin2-godotime` on
the configured VPS. The default game port is 8443, separate from existing
services; the SpacetimeDB administrative port remains loopback-only. The script
verifies the full export inventory, uploads a separate candidate, validates the
proxy before downtime and locks its own deployment. It checks port ownership,
takes a cold database/runtime backup, preserves issuer keys and refuses data
deletion. It can interrupt game sessions; distribution documents phase status
and failure recovery.

After deployment, verify HTTPS and a real browser/client session against that
endpoint. Health checks and successful Docker startup do not establish gameplay
replication. Restore a normal Web export after instrumented tests unless the
user has explicitly authorized keeping the development test build. Deployment
details, prerequisites, backups and evidence are in [distribution](distribution.md).

Implementation guidance for agents lives in the root [AGENTS.md](../AGENTS.md).
Update these instructions when a tested workflow changes.
