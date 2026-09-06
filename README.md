# Metin2 Godotime

A Metin2-inspired game with a **standard Godot/GDScript client and Rust
SpacetimeDB server in one monorepo**. The server owns movement, terrain height,
building collision, presence, combat and rewards. Blender converts selected
original warrior and Yongan assets. The original Metin2 executable cannot
connect to this game's new protocol.

Repository: [kcanakdag/metin2-godotime](https://github.com/kcanakdag/metin2-godotime).
The development browser deployment is [kcanakdag.com:8443](https://kcanakdag.com:8443/),
on the VPS at `159.195.213.9`. It is updated during development and may restart.
Account login and character selection are now implemented: username/password
registration and sign-in, four persistent character slots, original entry-screen
art, character previews, selection, world entry and logout. The server enforces
character ownership and private roster/inventory reads. Two real local accounts
pass **58 headless integration checks** for creation, ownership, movement,
switching and reconnect. Native editor entry and return to character selection
have also been observed. Public account release `20260906T173802450337Z` is live
on `mt2-accounts-v3`. Independent Chrome/Linux accounts pass **103 checks** both
locally and publicly, including entry, inventory/panels, movement, switching,
reconnect, logout and the real four-minute token refresh. Identities and
positions survive renewal, with no browser engine errors.

The preceding guest build, release `20260906T154235134255Z`, passed 45 public
Chrome/Linux panel, inventory and multiplayer checks. Earlier Yongan tests also
verified terrain appearance, combat, loot, both respawns and database-container
replacement. Those are historical gameplay results, not account-flow evidence.
The development test probe is explicitly authorized; normal exports omit it.

The PvE slice has a procedural **Stone Sentinel**, attacks, damage, death/respawn
and gold. Original taskbar and inventory art surround a two-page bag, one
starter sword, red potions and item drops. The preceding guest inventory slice
passed 56 live checks; native editor input equipped the server-owned sword.
Its Web/Linux exports also passed mouse/keyboard inventory, browser refresh
and potion-pickup checks against the public server.

Original UI fidelity is the target, not completed parity with the original game.
Entry enables one real server/channel, Shinsoo/Yongan and a male warrior;
other empires/classes, skills and social systems remain inactive. Matching
original fonts, intro animations and complete behavior has not been established
against a running original client. The sword changes server damage but has no
3D hand attachment yet. There are no quests, leveling or full Metin2 combat balance. Yongan has all
20 terrain sections and 601 building/prop placements; **368 trees and 6 effects
remain unsupported**. See [the rebuild roadmap](docs/full-rebuild-plan.md).

Authentication uses pinned Better Auth 1.7.3 in a separate Node service. Game
JWTs last five minutes; the client refreshes after four minutes and reconnects
the selected character. Remembered account sessions last up to 30 days. Recovery,
social login and an account dashboard are deferred. The public account rollout
uses a new database, `mt2-accounts-v3`, retaining the old guest database
without migrating its characters. See
[the milestone scope](docs/full-rebuild-plan.md#account-to-world-milestone).

## Develop locally

Verified tools: **Godot 4.7.2 standard**, **SpacetimeDB 2.8.3**, Rust with
`wasm32-unknown-unknown`, Python 3.12+, Node.js 24, and **Blender 5.2.1 LTS**.
Godot .NET is unnecessary: a pinned MIT GDScript SDK handles networking.

Run from the repository root:

```sh
# Once per checkout: local quality tools and optional editor bridge.
make dev-setup
rustup component add rustfmt clippy
rustup target add wasm32-unknown-unknown
make mcp-build
make auth-setup

# Fetch the pinned warrior fixture and conversion tools.
make assets
make import-assets BLENDER=/path/to/blender
make import-ui

# Reconstruct Yongan, then bake authoritative data and playable chunk scenes.
make import-map BLENDER=/path/to/blender
make bake-map BLENDER=/path/to/blender
make test-map

# Leave the database running in this terminal.
make server-start
```

Run the authentication service in another terminal:

```sh
AUTH_ISSUER=http://127.0.0.1:8184/auth make auth-start
```

Then publish the module with the same trusted issuer and start the local proxy:

```sh
MT2_AUTH_ISSUER=http://127.0.0.1:8184/auth make server-publish
make bindings
node tools/serve_local.mjs
```

The proxy provides one client origin at `http://127.0.0.1:8184`, forwarding to
SpacetimeDB on 3210 and auth on 3219. Administrative publish/binding commands
still use 3210. Start `make editor` separately and press **F5**, or use the client
commands below. A saved editor profile may override the built-in endpoint.
Register an account, choose the supported empire, create a character and enter.
Game data is in `.local/spacetimedb`; account data and keys are in `.local/auth`.
Use a new database or an explicit migration for incompatible changes. The local
default stays `mt2-yongan-v2`; public account exports/deployment explicitly use
`DB=mt2-accounts-v3`.

Two clients on one machine use different local profiles and separate accounts:

```sh
make client SERVER_URL=http://127.0.0.1:8184 PROFILE=alice
# In another terminal:
make client SERVER_URL=http://127.0.0.1:8184 PROFILE=bob
```

Make enables the `yongan` Cargo feature by default, requiring the ignored
`server/content/yongan.bin` and `.sha256` produced by `make bake-map`.
For the smaller training world, use
`make server-publish SERVER_FEATURES= DB=mt2-training-v2` and select that database
in both clients. Raw Cargo without `--features yongan` also selects training.
Both variants use application protocol 3. The production default requires an
account token. Legacy guest smoke tests need a separate module compiled with
`MT2_ALLOW_GUESTS=1`; never enable that option in a public build.

## Play and inspect

| Control | Action |
| --- | --- |
| Left click ground | Move toward terrain or an authored walk surface |
| WASD / arrows | Move relative to the camera |
| Right mouse drag; wheel | Orbit; zoom |
| Space | Attack the nearest living enemy in validated range |
| E / Z | Collect nearby gold/items with server distance/ownership validation |
| I / Inventory button | Open the two-page inventory |
| Item left click, then destination; drag/drop | Carry or move an item between valid bag/equipment/quickslot locations |
| Item right click | Equip/unequip the sword or consume a potion |
| 1–4 / F1–F4 | Activate one of the eight visible quickslots |
| Shift+1–4 / quickslot arrows | Select a quickslot page |
| M / minimap atlas button | Open/close the draggable original Yongan area map |
| Minimap close/reopen and +/− buttons | Hide/show the minimap or change zoom |
| L / chat-history button | Open the draggable, resizable chat log |
| Enter | Open chat; send nonempty text and return to movement; empty Enter closes |
| Up / Down while typing | Recall recently submitted chat text |
| Escape | Cancel chat/carry or close a panel; otherwise open/close the system menu |
| Ctrl+F3 | Toggle local diagnostics; F3 remains a quickslot key |
| System menu: Change Character / Logout | Return to character selection / end the account session |

Approach the Stone Sentinel near the town spawn, attack it, and collect its
gold and one red potion. It can also defeat the player. Player respawn takes 8 seconds; monster
respawn takes 12. Loot is reserved for its slayer for 10 seconds and expires
after 60. Reconnecting preserves gold, position and death state.

Each character receives one sword and five potions once. The sword occupies two
vertical bag cells and adds 10 to the base 25 attack damage when equipped.
A potion restores up to 40 HP with a one-second server cooldown; full-health
and dead-player use is rejected. The 90 bag cells form two 5 × 9 pages, and
potions stack to 200. Item ownership, placement, rewards and consumption belong
to the server; quickslot assignments and window preferences are saved locally.

`make import-ui` converts 196 selected original UI images and stitches Yongan's
20 original DDS minimap tiles, using 260 pinned source files. The minimap uses
that stitched image; the area-map window uses its separate original 171 × 214
image. Player markers come from subscribed state. Chat uses the original
centered entry and fading passive lines, with normal messages still limited to
160 characters by the server. Every exported UI texture is checked against its
decoded source-pixel hash. See [UI assets](docs/ui-assets.md) for conversion,
layout references and fidelity limits.

Chat sits at the bottom center. Sending, closing with Escape, or clicking the
world releases text focus and restores WASD/camera input. This passes native
and loopback browser/Linux regression checks. The preceding public build also passed
panel, inventory and multiplayer checks without sending synthetic public chat.

Click movement follows a straight line with collision/sliding; it does not
route around walls. Visuals interpolate server positions without local
movement prediction. Debug controls cannot grant rewards or bypass server rules.

`make preview` opens the warrior animation inspector. `make map-preview` opens
the separate flying map inspector: **WASD/Q/E** fly, right drag looks, **R**
returns to town, **M** shows the whole map, **U** toggles missing scenery markers,
and **C** shows source attributes. Flying there is independent of multiplayer.
See [map importing](docs/map-import.md).

## Browser, desktop and deployment

Install matching Godot **4.7.2** Web and Linux export templates. Web uses
Compatibility/WebGL 2 and a single-threaded WebAssembly template. A core pack
boots the game; Yongan has shared assets plus 20 content-hashed section packs
for loading nearby scenery during play. Engine, core assets and the starting
area still require an initial download. One real-GPU test reached the engine
in 6.66 seconds and the world in 12.97 seconds total; connection and hardware
change these times. All 20 section packs pass isolated dependency and exact
terrain-ID checks.

```sh
make export-web SERVER_URL=https://kcanakdag.com:8443 DB=mt2-accounts-v3
make export-linux SERVER_URL=https://kcanakdag.com:8443 DB=mt2-accounts-v3
make server-build
make deploy DB=mt2-accounts-v3
```

Outputs are `dist/web/` and `dist/linux/`. Browser players open the HTTPS link;
Linux players run `dist/linux/MT2Spacetime.x86_64`. Exports stage an isolated
project, remove MCP/test bridges, retain runtime dependencies, and audit the PCK.

Deployment uses Compose project `metin2-godotime` in
`/opt/metin2-godotime` on the VPS. HTTPS/WSS uses **8443**; database administration
binds to remote loopback **13210**. Existing portfolio/project ports remain
untouched. A private auth container persists accounts and signing keys in its
own volume. The script takes cold game/auth backups before restarting and
preserves game data. With matching instrumented exports targeting the new
database, the account rollout uses
`make deploy DB=mt2-accounts-v3 WEB_DIR=dist/web-test DEPLOY_FLAGS='--allow-test-build'`.
The old `mt2-yongan-v2` guest database remains stored, while the public proxy
selects the new account database. Auth accounts and issuer keys persist.
See [distribution](docs/distribution.md)
for prerequisites, update behavior and verification.

The older Windows ZIP and temporary tunnel workflow remains training-only;
`make export-windows` uses `WINDOWS_DB=mt2-training-v2` and omits Yongan assets.
Its historical Wine proof does not establish Windows execution of current Yongan.
See [temporary playtesting](docs/playtesting.md).

## Checks and schema changes

```sh
make format                 # Explicit formatters and safe Python fixes
make check                  # Lint, server/tool tests, Godot checks
make test-map               # Source formats and generated map resources
make test-auth              # Actual HTTP auth tests with temporary databases
make test-accounts SERVER_URL=http://127.0.0.1:8184 DB=mt2-yongan-test
```

Publish the account module to the selected disposable database first and restart
the local proxy with matching `MT2_DEV_DATABASE=mt2-yongan-test`. The
account suite creates two real accounts and checks roster/inventory privacy,
name/slot rejection, selected-character movement, session ownership and
disconnect/reconnect. It creates persistent fixture rows; it does not erase
the world. For rendered browser/Linux account checks, use
`tools/test_browser_accounts.py --hardware --inventory --panels` with matching
test exports and an explicit URL/database. See
[development](docs/development.md#browser-integration-checks).
Legacy `test-multiplayer`, `test-combat`, `test-inventory` and `test-browser`
remain disposable guest-suite tools and require their opt-in module build.
Local isolated panel checks use `make test-ui UI_FLAGS="--suite map"` or
`UI_FLAGS="--suite chat"`; add `--native` to capture their rendered result.

After table/reducer changes, publish, run `make bindings`, and test before
exporting. Generated bindings record the schema hash and SDK pin;
`tools/generate_bindings.py --offline` regenerates from the saved schema.

## Repository and tools

```text
client/scripts/net/          SDK, identity and subscription boundary
client/scripts/actors/       Warrior, monster and loot presentation
client/scripts/world/        Training ground and streamed Yongan sections
client/scripts/ui/           Original taskbar/inventory/minimap, chat and diagnostics
client/spacetime_bindings/   Generated protocol-3 schema and provenance
client/addons/SpacetimeDB/   Pinned runtime SDK
client/addons/godot_mcp/     Editor tooling, excluded from exports
server/src/                 Identity, movement, map content and combat rules
server/content/             Generated authoritative map data (ignored)
auth/                       Pinned Better Auth service, HTTP tests and container
deploy/                     Docker image, Compose and restricted HTTPS proxy
tools/                      Import, bake, export, deployment and test commands
assets/source/              Selected originals (ignored)
client/assets/imported/     Converted assets and generated chunks (ignored)
.local/                    Databases, reports and staging (ignored)
dist/                      Exported client packages (ignored)
```

Godot MCP supports editor/runtime trees, screenshots, inspection and simulated
input. Confirm the connected project before changing it. Do not run
`make mcp-check` while another MCP server owns port 6505; use connected tools.
See [MCP setup](docs/godot-mcp.md), [architecture](docs/architecture.md), and
[agent instructions](AGENTS.md).

The warrior has **3 meshes, 2,207 source vertices, 2,268 triangles, 75 bones**
and wait/walk/run/attack clips. Selected Yongan dependencies use the same pinned
archive. Original assets and derivatives remain ignored; their rights are
separate from MIT tooling and this project's source.
[Third-party provenance](docs/third-party.md) records revisions and terms.
[open-mt2](docs/open-mt2.md) is a reference; its implementation has not been copied.
