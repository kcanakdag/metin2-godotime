# Metin2 Godotime

A Metin2-inspired game with a **standard Godot/GDScript client and Rust
SpacetimeDB server in one monorepo**. The server owns movement, terrain height,
building collision, presence, combat and rewards. Blender converts selected
original warrior and Yongan assets. The original Metin2 executable cannot
connect to this game's new protocol.

Repository: [kcanakdag/metin2-godotime](https://github.com/kcanakdag/metin2-godotime).
The development browser deployment is [kcanakdag.com:8443](https://kcanakdag.com:8443/),
on the VPS at `159.195.213.9`. It is updated during development and may restart.
The current development build includes the explicitly authorized fixed test
probe. The original HUD and inventory passed 39 public Chrome/Linux checks,
including drag/drop, quickslots, browser refresh, combat and item pickup.
Normal exports omit this probe as before.
The map/chat update is live as release `20260906T154235134255Z`. Original
area-map/chat-history windows and minimap controls pass 45 public Chrome/Linux
checks. A separate 45-check loopback run verifies actual chat delivery and WASD
after sending, Escape, world clicks and history submission.
Browser multiplayer has passed real Web/Linux export tests on the training
ground and Yongan. The public Yongan test verifies movement, terrain appearance,
combat, loot, both respawns, reconnect and database-container replacement.
Nearby scenery loads during play. Refresh an older open browser tab to load the
corrected terrain and collision data. The preceding normal Web/Linux release
was also checked directly, with test interfaces excluded.

The PvE slice has a procedural **Stone Sentinel**, attacks, damage, death/respawn
and gold. The current UI/inventory work adds original taskbar and inventory art,
a two-page bag, one starter sword, red potions and item drops. Its 56 live
inventory checks pass, and native editor input equips the server-owned sword.
The matching Web/Linux test exports passed mouse and keyboard inventory checks
against the public server, including browser refresh and potion pickup.

Original UI fidelity is the target, not completed parity with the original game.
Login remains a prototype; character, skills and social systems are inactive;
matching original fonts and behavior has not been established against a running
original client. The sword changes server damage but has no 3D hand attachment
yet. There are no quests, leveling or full Metin2 combat balance. Yongan has all
20 terrain sections and 601 building/prop placements; **368 trees and 6 effects
remain unsupported**. See [the rebuild roadmap](docs/full-rebuild-plan.md).

The next milestone is the account-to-world flow: minimal username/password
sign-in, original server/channel and character screens, persistent character
ownership, and entering Yongan with a selected character. Use the real pinned
intro artwork and screen layouts; defer a full account dashboard and recovery
flow. This takes priority over additional combat content; the existing guest
login is still the current implementation. See
[the milestone scope](docs/full-rebuild-plan.md#immediate-next-milestone-account-to-world).

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

In another terminal:

```sh
make server-publish
make bindings
make editor
```

Press **F5**, choose a name, and enter the world. Make uses
`http://127.0.0.1:3210` and database `mt2-yongan-v2`; select those values in the
editor's connection screen if an earlier profile saved different settings.
Database files are in `.local/spacetimedb`, and CLI configuration stays
project-local. For incompatible schema changes, choose a new database or an
explicit migration; do not wipe an existing development world.

Two clients on one machine need different profiles:

```sh
make client PROFILE=alice PLAYER_NAME=Alice
# In another terminal:
make client PROFILE=bob PLAYER_NAME=Bob
```

Make enables the `yongan` Cargo feature by default, requiring the ignored
`server/content/yongan.bin` and `.sha256` produced by `make bake-map`.
For the smaller training world, use
`make server-publish SERVER_FEATURES= DB=mt2-training-v2` and select that database
in both clients. Raw Cargo without `--features yongan` also selects training.
Both variants use the version-2 gameplay schema.

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

Approach the Stone Sentinel near the town spawn, attack it, and collect its
gold and one red potion. It can also defeat the player. Player respawn takes 8 seconds; monster
respawn takes 12. Loot is reserved for its slayer for 10 seconds and expires
after 60. Reconnecting preserves gold, position and death state.

Each identity receives one sword and five potions once. The sword occupies two
vertical bag cells and adds 10 to the base 25 attack damage when equipped.
A potion restores up to 40 HP with a one-second server cooldown; full-health
and dead-player use is rejected. The 90 bag cells form two 5 × 9 pages, and
potions stack to 200. Item ownership, placement, rewards and consumption belong
to the server; quickslot assignments and window preferences are saved locally.

`make import-ui` converts 159 selected original UI images and stitches Yongan's
20 original DDS minimap tiles, using 207 pinned source files. The minimap uses
that stitched image; the area-map window uses its separate original 171 × 214
image. Player markers come from subscribed state. Chat uses the original
centered entry and fading passive lines, with normal messages still limited to
160 characters by the server. Every exported UI texture is checked against its
decoded source-pixel hash. See [UI assets](docs/ui-assets.md) for conversion,
layout references and fidelity limits.

Chat sits at the bottom center. Sending, closing with Escape, or clicking the
world releases text focus and restores WASD/camera input. This passes native
and loopback browser/Linux regression checks. The public build also passes
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
make export-web SERVER_URL=https://kcanakdag.com:8443
make export-linux SERVER_URL=https://kcanakdag.com:8443
make server-build
make deploy
```

Outputs are `dist/web/` and `dist/linux/`. Browser players open the HTTPS link;
Linux players run `dist/linux/MT2Spacetime.x86_64`. Exports stage an isolated
project, remove MCP/test bridges, retain runtime dependencies, and audit the PCK.

Deployment uses Compose project `metin2-godotime` in
`/opt/metin2-godotime` on the VPS. HTTPS/WSS uses **8443**; database administration
binds to remote loopback **13210**. Existing portfolio/project ports remain
untouched. The script backs up database files before restarting and prohibits
data deletion during publication. See [distribution](docs/distribution.md)
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
make test-multiplayer DB=mt2-yongan-test
make test-combat DB=mt2-yongan-test
make test-inventory DB=mt2-yongan-test
```

Publish the module to the selected disposable test database first. Live SDK
checks use distinct identities and exercise mutual visibility, movement,
rejection, disconnect/reconnect, and the combat/reward/inventory loop. They create
characters and state in that database. For rendered browser/Linux checks, use
explicit test exports as described in
[development](docs/development.md#browser-integration-checks).
The original inventory UI check adds `BROWSER_FLAGS="--hardware --inventory"`
to `make test-browser` with matching test exports.
Add `--panels` for actual browser minimap, area-map and chat-window controls.
`--chat-focus` adds sending and subsequent WASD checks on a loopback test world
only; it rejects public hostnames to keep synthetic chat out of public sessions.
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
client/spacetime_bindings/   Generated version-2 schema and provenance
client/addons/SpacetimeDB/   Pinned runtime SDK
client/addons/godot_mcp/     Editor tooling, excluded from exports
server/src/                 Identity, movement, map content and combat rules
server/content/             Generated authoritative map data (ignored)
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
