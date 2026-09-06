# Development workflow

Run commands from the repository root. The game uses standard Godot with
GDScript and a Rust SpacetimeDB module. Python runs development and asset tools;
Node runs the authentication service and local development proxy/MCP tools.
The auth service is deployed separately; no Python/Node runtime belongs inside
a player's Godot client build.

## Install the quality tools

Use Python 3.12 or newer. This creates an ignored virtual environment at
`.local/venv-dev` and installs the exact versions in
`tools/requirements-dev.txt`; activating the environment is optional.

```sh
python3 tools/dev.py setup
rustup component add rustfmt clippy
rustup target add wasm32-unknown-unknown
make mcp-build
make auth-setup
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
| Godot MCP and auth TypeScript | Strict type checks with no output | Each service's `tsconfig.json` and `package-lock.json` |

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

`game_connection.gd` has a file-scoped `max-public-methods` exception: it is the
single typed facade for account, movement, combat and inventory intents. This
keeps callers outside SDK implementation details. Other GDScript checks still
run; do not extend this exception to unrelated files.

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

## Local accounts and shared world

Use Node 24.10 or newer in the Node 24 line. `make auth-setup` installs pinned
Better Auth dependencies; `make test-auth` runs actual HTTP tests against
isolated temporary SQLite databases. All four HTTP suites pass; a separate
Docker check verified persisted account/signing state. Production images pin
Node 24.20.0.

Start each long-running process in its own terminal:

```sh
make server-start
# Another terminal:
AUTH_ISSUER=http://127.0.0.1:8184/auth make auth-start
```

Compile/publish with the same trusted issuer, then start the local proxy:

```sh
MT2_AUTH_ISSUER=http://127.0.0.1:8184/auth make server-publish
make bindings
node tools/serve_local.mjs
```

The browser/native client origin is `http://127.0.0.1:8184`; the proxy forwards
auth to 3219 and game routes to SpacetimeDB on 3210. Administrative publication
and schema/binding requests continue to use 3210. `AUTH_ISSUER` configures the
HTTP service; `MT2_AUTH_ISSUER` is compiled into the Rust module. They must match
exactly, including `/auth`. The production default is
`https://kcanakdag.com:8443/auth`; do not publish a local-issuer module publicly.

The local proxy's actual HTTP check passed for auth health, database identity
and the Web index, while rejecting administrative schema access and traversal.
The isolated-port report is `.local/accounts/local-entry-report.json`.

```sh
make client SERVER_URL=http://127.0.0.1:8184 PROFILE=alice
# Another terminal, with a different account:
make client SERVER_URL=http://127.0.0.1:8184 PROFILE=bob
```

Profiles separate remembered client sessions; account ownership lives on the
server. One account has four character slots, but only one controlling socket.
Use the original server/login/empire/create/select screens to enter Yongan.
The server board checks both auth and database availability every 15 seconds.
`make editor`/F5 uses the client default, but saved profile settings may override
it. Browser exports use their page origin rather than a stale saved endpoint.

The Make server defaults remain `SERVER_FEATURES=yongan`, `DB=mt2-yongan-v2`
and administrative `SERVER_URL=http://127.0.0.1:3210`. Game state lives in
`.local/spacetimedb`; authentication state/keys live in `.local/auth`.
Keep disposable processes/databases separate from development state. Public
account exports and deployment explicitly target `DB=mt2-accounts-v3`, retaining
the old public guest database. This does not change the tested local default.

## Account and gameplay checks

Publish to a disposable game database using the local auth issuer. Stop the
existing local proxy and restart it in its own terminal for the test database:

```sh
MT2_DEV_DATABASE=mt2-yongan-test MT2_WEB_DIR=dist/web-test node tools/serve_local.mjs
```

The proxy exposes only its configured game database. Then run:

```sh
MT2_AUTH_ISSUER=http://127.0.0.1:8184/auth make server-publish DB=mt2-yongan-test
make bindings DB=mt2-yongan-test
make test-auth
make test-accounts SERVER_URL=http://127.0.0.1:8184 DB=mt2-yongan-test
```

`tools/test_accounts.py` creates two real accounts through HTTP, stages a
separate Godot project, writes its two JWTs into a temporary mode-0600 fixture,
and runs `client/tests/account_smoke.gd`. Tokens/passwords are redacted from
logs; fixture sessions are logged out afterward. The accounts and character
rows remain for inspection. Reports default to `.local/accounts-report.json`.
The suite checks raw SDK roster/state/inventory caches for private reads,
four slots, name/ownership rejection, selection, mutual subscribed movement,
duplicate sessions, leaving/switching and reconnect persistence. The full
HTTP → Godot → SpacetimeDB run passed 58 checks on 2026-09-06; its report is
`.local/accounts/integration-report.json`. This establishes real subscribed
account behavior in headless native clients. Rendered browser input and the
real four-minute refresh timer have separate checks below.

Legacy `make test-multiplayer`, `test-combat`, `test-inventory` and
`tools/test_browser.py` target the earlier guest flow. They require an isolated
module compiled with `MT2_ALLOW_GUESTS=1`; production builds reject guests.
The adapted legacy suites passed on the disposable `mt2-account-legacy`
database on 2026-09-06: 22 multiplayer, 19 combat and 60 inventory checks.
Reports are `.local/accounts/legacy-multiplayer.json`, `legacy-combat.json` and
`legacy-inventory.json`. Inventory now reads items from their owner's cache and
asserts the other client cannot read them, including after reconnects and death.
Foreign item intents still verify server rejection. These runs use the current
direct account RLS filter and generated schema, but do not exercise account
registration or authenticated character selection.
Do not enable guest access in the public deployment to make old checks pass.
Training uses `SERVER_FEATURES=` and a separate training database; both maps
use application protocol 3.

For gameplay changes, verify two independently authenticated accounts see each
other, each movement reaches the other subscription, and disconnect removes
presence. Include rejected reducers and reconnect when changing lifecycle.
The server validates actions even when the UI limits inputs. A database query
or plausible snapshot alone does not prove subscribed or rendered behavior.

The development scene exposes `dev_snapshot()` for runtime inspection. Use it
with scene trees, screenshots and actual input. Debug controls send normal
validated reducers; privileged actions require explicit server authorization.

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
inventory, item icons and stitched Yongan minimap. This converts 196 UI images
and 20 original DDS map tiles from 260 pinned source files with Pillow; Blender
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
includes 17 map and 22 chat checks with native screenshots in
`.local/classic-map/` and `.local/classic-chat-final/`. The latest UI run passes
19 checks, including system-menu centering, viewport resizing and button
clicks, in `.local/classic-system/`. The separate original entry suite passes
27 native checks in `.local/classic-intro/`.

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

The account milestone uses `tools/test_browser_accounts.py` with matching
instrumented Web/Linux exports and the auth-aware origin. Run the local proxy
with `MT2_DEV_DATABASE=mt2-yongan-test MT2_WEB_DIR=dist/web-test` as above, so its
allowed database and static directory match the exports:

```sh
make browser-setup
make export-web SERVER_URL=http://127.0.0.1:8184 DB=mt2-yongan-test TEST_PROBE=--test-probe
make export-linux SERVER_URL=http://127.0.0.1:8184 DB=mt2-yongan-test TEST_PROBE=--test-probe
.local/venv-dev/bin/python tools/test_browser_accounts.py \
  --url http://127.0.0.1:8184 --database mt2-yongan-test \
  --hardware --inventory --panels
```

The runner uses visible browser controls for registration/login and character
entry, plus an independent exported Linux account. It covers ownership,
creation/selection, leave/switch, movement, reconnect/refresh, logout and wrong
password handling; optional flags add original HUD/panel interactions. It
writes private reports/screenshots under `.local/browser-accounts/<timestamp>/`.
Add `--session-refresh` to wait for both clients' real four-minute refresh
timers and verify that they reconnect into the same world state; this is a
longer test, not an accelerated timer simulation. Both final runs pass 103
checks, including real timer renewal with unchanged identities and positions:
`.local/browser-accounts/20260906-193823/report.json` on loopback and
`.local/browser-accounts/20260906-194508/report.json` on the public account
database. Both use independent Chrome/Linux accounts and record no browser
engine errors. Entry, inventory/panels, system-menu interactions, movement,
switching, reconnect, page reload, logout and wrong-password retry are covered.
The 19-check native UI suite separately verifies menu centering/resizing/clicks.
Public release `20260906T173802450337Z` also passes HTTPS/served-manifest checks.

### Historical guest browser evidence

The commands/results below describe the preceding guest build. Reusing its
runner requires a dedicated guest-enabled test module and compatible exports.


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
The preceding panel export passed both loopback and public checks. Its final public
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

The preceding public guest release `20260906T154235134255Z` retained the
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

Build the production-issuer server, export a normal Web client with
`DB=mt2-accounts-v3` and run `make deploy DB=mt2-accounts-v3`. This changes only
`/opt/metin2-godotime` and Compose project
`metin2-godotime`. HTTPS/WSS uses 8443; database administration stays on remote
loopback 13210. Auth has a private container and separate persistent `accounts`
volume. The public issuer is `https://kcanakdag.com:8443/auth`.

The script verifies export bytes, stages only selected auth build inputs,
validates Compose/Nginx before downtime and locks its own deployment. It takes
cold game/auth data and runtime backups, checks issuer-key/auth-secret hashes,
and normally publishes with `--delete-data=never`.

Local Godot is also required for deployment: an isolated headless process reads
the actual Web PCK's connection defaults and rejects a database mismatch before
SSH. Use `GODOT=/path/to/godot` or the deploy tool's `--godot` option if needed.

The account rollout creates a new public database while preserving the old
guest database. With matching instrumented exports targeting `mt2-accounts-v3`:

```sh
make deploy DB=mt2-accounts-v3 WEB_DIR=dist/web-test DEPLOY_FLAGS='--allow-test-build'
```

This invocation does not reset a database or remove a volume. The old
`mt2-yongan-v2` remains stored, and the proxy exposes only the new account
database. Auth accounts, signing material and SpacetimeDB issuer keys persist.
The public deployment completed as release `20260906T173802450337Z`, with
verified HTTPS health/discovery, database availability and served manifest.
The public browser/Linux account run passes 103 checks, including real timed
refresh. Local apply-script command fixtures cover failure recovery and optional
reset scope; they are not a real Docker restore drill.

After deployment, verify HTTPS and two actual accounts in browser/native
clients. Health checks and successful container startup do not establish
private subscriptions or gameplay. Normal exports omit probes; the development
test build is explicitly authorized. See [distribution](distribution.md) for
prerequisites, phase status, failure behavior and recorded evidence.

Implementation guidance for agents lives in [AGENTS.md](../AGENTS.md). Update
these notes when the tested workflow changes.
