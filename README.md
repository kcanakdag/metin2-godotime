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
character ownership and private roster, inventory, progression and
command-feedback reads. The accepted P1 checkpoint passed **94 authenticated
server checks** for creation, ownership, movement, combat, switching and
reconnect. Native editor entry and return to character selection
have also been observed. The P1 development release
`20260906T204513591109Z` is live on `mt2-p1-v4`; publication preserved account,
key and game data, and verified the served manifest. Its public exported-gameplay
qualification is still pending. The preceding `mt2-accounts-v3` release passed
**103 public Chrome/Linux checks**, including entry, inventory/panels, movement,
switching, reconnect, logout and the real four-minute token refresh, and remains
stored without being routed publicly.

The selected P0/P1 Warrior, Sword+0 and Wild Dog 101 fixture is accepted locally.
Its final independent Chrome/Linux run passes **111 checks** against
`mt2-p1-final`, including generated actors, equipment projection, combat,
two-client lifecycle and both real refresh timers. The same checkpoint has 94
authenticated server checks, 52 source-freeze actor checks, 30 Rust tests and
101 Python tool tests. Export audits cover 711 Web paths, 1,514 Linux paths, all
197 selected UI images, all 40 declared clips and all 20 Yongan section packs.

The local protocol-5 P2 candidate has also produced matching Web/Linux exports
for the fresh default-deny `mt2-p2-yongan-20260906` database. Their actual-PCK
audits cover 795 Web paths, 1,598 Linux paths, all 225 selected UI images, all
40 clips and all 20 isolated Yongan sections. A real exported client read back
Yongan, the exact P2 gameplay-definition hash, nine loaded map chunks and no
content error. A 199-check exported Chrome/Linux run verifies five ordinary
Wild Dog kills, exact +15 XP per life, the first +2-potion quarter, the source
Status/orb, VIT allocation without healing, state persistence through switch,
reconnect, reload and login, and both real four-minute token refreshes. The
report is `.local/p2/browser-positive-progression-fresh-read/report.json`. The
separate 298-check headless report at
`.local/p2/accounts-progression-20260907T0349.json` verifies an ordinary +15
Wild Dog reward, the source float32 70/35 to 11/4 and 75/35 to 11/3 splits on
separate lives, owner privacy and reconnect, all 20 ordinary kills from level 1
to 2, quarter potions, and VIT allocation without a current-HP heal. Privileged
operator success still awaits explicit authorization for its isolated bootstrap
fixture. Protocol 5 remains local; this does not change the public `mt2-p1-v4`
route.

The bounded local protocol-6 Target Slice A is accepted. Its separate actual-PCK
audits cover 832 Web paths and 1,635 Linux paths, including all 226 UI/map
images. The target-effect audit loads both models through all 11 frames and
checks four runtime textures plus four matching engine-extracted derivatives;
the Python tool suite passes 139 checks. The final 174-check exported hardware
Chrome/Linux run verifies owner-private exact-life selection, stationary hover,
the authoritative panel and effects, ground/WASD target retention, clear and
rejection handling, four ordinary 25-damage attacks, death/new-life cleanup,
actor equipment with exact inventory restoration, account lifecycle and both
real four-minute token refreshes, with no engine errors. The native pointer path
uses fixed production-routed InputEvents from the authorized test probe. Root
reviewed both final selected-target captures; they show the source effects
grounded with the expected orientation. The report is
`.local/p2-target/browser-root-final-20260907/report.json`. This local acceptance
does not change the public `mt2-p1-v4` route or establish original-client pixel
parity, current Windows execution, or full P2 behavior.

The bounded local protocol-7 Sword+0 two-step combo slice is also accepted. Its
final 288-check hardware Chrome/Linux run proves both browser-origin and
native-origin `combo_1` to `combo_2` chains, with exact 100→65→30 Wild Dog
health on fresh lives and both clients presenting each subscribed action. The
exact next reducer acknowledgements place both queued follow-ups inside the
source-defined receipt window; accepted same-life target renewal preserves the
link, while held/released WASD, a ground click, and target clear each cancel an
accepted queue after only the first 35-damage hit. The same run retains target,
inventory, actor, panel and account-lifecycle coverage, both real four-minute
token refreshes, zero authoritative-position drift and no engine errors. Root
also reviewed both final combo captures. See the [288-check report](.local/p2-combo/browser-root-independent-followup-20260907/report.json)
and [root acceptance review](.local/p2-combo/root-acceptance-review.json). This
evidence uses authorized local instrumented exports; it does not qualify the
public route, normal exports, current Windows execution, original-client parity
or the remaining P2 scope.

The bounded local protocol-8 third-combo/root-motion Slice C is accepted. It adds
the third common Sword+0 combo action and server-authoritative horizontal
displacement for all three actions. The server publishes each accepted action
and resulting position; local and remote actors follow those subscribed rows
without applying animation root displacement themselves. The interim trajectory
policy is a linear approximation of the three pinned GR2 endpoints in fixed
50 ms physical quanta, with collision and exact terminal remainders enforced by
the server. Each accepted action keeps its captured heading through hit
resolution; a later action may capture a new heading.

The final 297-check run with hardware-accelerated Chrome and an exported Linux
client verifies browser-origin and native-origin three-step chains, exact
100→65→30→0 Wild Dog health, source-window receipts, same-life target renewal,
constant action headings and authoritative root travel on both clients. It also
verifies queue cancellation by WASD, ground movement and target clear while the
accepted root continues, lethal-hit root completion, zero reconnect
displacement, 0.921997 m travel clipped by an authored Yongan wall, both real
four-minute refreshes and no browser engine errors. Root reviewed both final
step-3 captures. See the
[297-check exported report](.local/p2-rootmotion/revision2/browser-root-lifecycle-20260907/report.json)
and [root acceptance review](.local/p2-rootmotion/root-acceptance-review.json).
The revision-2 live headless run separately passes 91 checks, including the
attacker traveling past its target before the hit, authoritative root endpoints
and collision, cancellation, target death and disconnect without replay; see
the [headless report](.local/p2-rootmotion/revision2/headless-root-20260907.json).
The current generated actor manifest also passes the isolated
[77-check actor smoke](.local/p2-rootmotion/revision2/client-actors-current-local-sockets/report.json).
This evidence uses authorized local instrumented exports. It does not qualify
the public route, normal exports, current Windows execution, editor MCP behavior,
full P2 behavior or original Granny within-cycle and transition-blend parity.

The preceding guest build, release `20260906T154235134255Z`, passed 45 public
Chrome/Linux panel, inventory and multiplayer checks. Earlier Yongan tests also
verified terrain appearance, combat, loot, both respawns and database-container
replacement. Those are historical gameplay results, not account-flow evidence.
The development test probe is explicitly authorized; normal exports omit it.

The first rebuilt PvE fixture uses original **Wild Dog 101** identity, model and
motion metadata with server-owned delayed hit windows, damage, death/respawn and
gold. Original taskbar and inventory art surround a two-page bag, one
starter sword, red potions and item drops. The preceding guest inventory slice
passed 56 live checks; native editor input equipped the server-owned sword.
Its Web/Linux exports also passed mouse/keyboard inventory, browser refresh
and potion-pickup checks against the public server.

Original UI fidelity is the target, not completed parity with the original game.
Entry enables one real server/channel, Shinsoo/Yongan and a male warrior;
other empires/classes, skills and social systems remain inactive. Matching
original fonts, intro animations and complete behavior has not been established
against a running original client. The equipped sword is projected through a
small public presence row so peers can attach it without reading another
account's inventory. The bounded P2 slice adds source-backed level 1 male
Warrior stats, experience through the level-99 cap, quarter-step stat points
and automatic potion grants. Other classes, skills, quests, death penalties,
party experience and full Metin2 combat/stat balance remain unimplemented.
Yongan has all
20 terrain sections and 601 building/prop placements; **368 trees and 6 effects
remain unsupported**. See [the rebuild roadmap](docs/full-rebuild-plan.md).

The generated Warrior/Sword+0/Wild Dog 101 fixture has a separate
[content-import workflow](docs/content-import.md). Its selected original files,
converted GLBs and trusted action definitions are a reproducible P1 fixture;
they are accepted for the bounded local two-client/server slice. They do not
establish full content coverage, original-client visual parity, normal-export
packaging, public P1 gameplay qualification or current Windows execution.

The [full-game plan](docs/full-rebuild-plan.md) now maps original server/client
sources, open-mt2 and other references into a
[feature catalog with dependencies](docs/rebuild/feature-catalog.md).
It covers classic gameplay, marriage/weddings/divorce, guilds/land/wars,
later-system variants, and [development/admin automation](docs/rebuild/development-and-admin.md).
Source inventories and current implementation gaps are explicit; the plan is
not a claim that these systems already work. Run `make check-plan` to validate
the catalog and its acyclic implementation prerequisites.

Authentication uses pinned Better Auth 1.7.3 in a separate Node service. Game
JWTs last five minutes; the client refreshes after four minutes and reconnects
the selected character. Remembered account sessions last up to 30 days. Recovery,
social login and an account dashboard are deferred. The current public P1
development rollout uses `mt2-p1-v4`; the preceding `mt2-accounts-v3` account
database and old guest database remain stored without migrating their
characters. See
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

# Build the first generated actor fixture: Warrior, Sword+0 vnum 10 and Wild Dog 101.
make content-build BLENDER=/path/to/blender
make content-validate
make content-probe

# Fetch, convert, install, and test the two required target effects.
.local/venv-dev/bin/python tools/import_target_effects.py --fetch \
  --blender /path/to/blender --godot /path/to/godot \
  --geometry-only --install
.local/venv-dev/bin/python tools/test_target_effects.py --godot /path/to/godot \
  --output .local/p2-target/effects/smoke

# Exercise actor/effect attachment and target UI/picking in isolated projects.
make test-actors
.local/venv-dev/bin/python tools/test_target_client.py --godot /path/to/godot \
  --output .local/p2-target/client-smoke

# Reconstruct Yongan, then bake authoritative data and playable chunk scenes.
make import-map BLENDER=/path/to/blender
make bake-map BLENDER=/path/to/blender
make test-map

# Leave the database running in this terminal.
make server-start
```

Target-effect conversion requires Blender 5.2.1 and Godot 4.7.2. The first
`--fetch` downloads the nine pinned conversion inputs plus the archive Index and
inventory metadata; later runs use the cache.
Generated development output stays under `.local/p2-target/effects/generated`,
and `--install` writes the ignored runtime package under
`client/assets/imported/content/p2-target-effects`. `--geometry-only` validates
the source transforms and bounds; use the separate `--render` mode for native
visual comparison.

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
Use a new database or an explicit migration for incompatible changes. The
Makefile's retained legacy placeholder is `mt2-yongan-v2`; current protocol-8
development should pass a fresh explicit `DB`, such as
`DB=mt2-p2-rootmotion-yongan-local`. Public P1 exports/deployment still use
`DB=mt2-p1-v4` until a separately qualified P2 rollout.

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
Both variants use application protocol 8. Earlier databases do not contain all
private progression, command-feedback, and combat-target tables and need a new
database or an explicit migration before using a current client. The production
default requires an account token. Legacy guest smoke tests need a separate module
compiled with `MT2_ALLOW_GUESTS=1`; never enable that option in a public build.

## Play and inspect

| Control | Action |
| --- | --- |
| Left click ground | Move toward terrain or an authored walk surface; preserve the selected target |
| Left click living monster | Request selection of that exact subscribed monster generation |
| WASD / arrows | Move relative to the camera |
| Right mouse drag; wheel | Orbit; zoom |
| Space | Attack the selected exact monster, or the nearest valid enemy when no target is selected; Sword+0 accepts the current three-step server-timed prefix |
| E / Z | Collect nearby gold/items with server distance/ownership validation |
| I / Inventory button | Open the two-page inventory |
| Item left click, then destination; drag/drop | Carry or move an item between valid bag/equipment/quickslot locations |
| Item right click | Equip/unequip the sword or consume a potion |
| 1–4 / F1–F4 | Activate one of the eight visible quickslots |
| Shift+1–4 / quickslot arrows | Select a quickslot page |
| M / minimap atlas button | Open/close the draggable original Yongan area map |
| C / character button | Open/close the character status window and allocate earned stat points |
| Minimap close/reopen and +/− buttons | Hide/show the minimap or change zoom |
| L / chat-history button | Open the draggable, resizable chat log |
| Enter | Open chat; send nonempty text and return to movement; empty Enter closes |
| Up / Down while typing | Recall recently submitted chat text |
| Escape | Cancel chat/carry or close a panel; otherwise open/close the system menu |
| Ctrl+F3 | Toggle local diagnostics; F3 remains a quickslot key |
| System menu: Change Character / Logout | Return to character selection / end the account session |

The target board and ground effect appear only after the owner-private selection
row matches the same subscribed live monster ID and life sequence. Closing the
board sends the normal clear-target action. This first pointer slice selects
only; the original smart click's chase/attack behavior remains future work.
Picking respects whichever terrain, authored walk surface, or other collider is
actually nearest to the camera ray. Buildings without a client collider cannot
visually occlude a target proxy, while server movement blocking remains
authoritative.

With Sword+0 equipped, a second or third Space during the current action's
source-defined input window requests the next link through `combo_3`. The server
alone schedules and publishes each transition; both clients keep presenting the
current action until its subscribed row changes. An accepted movement intent or
target clear cancels a queued link, while renewing the same exact target
preserves it. The current accepted action's authoritative root travel and hit
continue after those queue cancellations; stored ordinary locomotion begins
after the attack hold ends. Target death clears future links but the lethal
action continues its root travel through clip end. A targetless or missed chain
may animate and travel without inventing damage or a new selection.

Approach the Wild Dog near the town spawn, attack it, and collect its
gold and one red potion. It can also defeat the player. Player respawn takes 8 seconds; monster
respawn takes 12. Loot is reserved for its slayer for 10 seconds and expires
after 60. Reconnecting preserves gold, position and death state.

A new supported male Warrior starts at level 1 with 6 strength, 4 vitality,
3 dexterity, 3 intelligence, 760 HP and 260 SP. Wild Dog 101 grants 15 ordinary
experience. At 75, 150 and 225 experience the character earns a stat point;
300 advances it to level 2 and applies the source-backed random HP/SP growth.
Every positive quarter step refills living characters' HP/SP and grants two
small red potions through level 10. Later supported steps grant two medium red
potions (`vnum=27002`); their storage and full-bag fallback are implemented,
while consuming that later potion is deferred. Experience is authoritative and
private to the owning account. Eligible non-party contributors share a kill's
experience by registered damage and must remain on the same live connection and
within the original approximate 50 m rule when the monster dies.

`/help` returns private command help and never emits public chat. `/xp AMOUNT`
and `/level TARGET` use the normal progression kernel but require a server-side
operator capability; builds default to no authorized operators. Operator setup,
auditing, idempotency and rate limits are documented in
[development and admin automation](docs/rebuild/development-and-admin.md).

Each character receives one sword and five potions once. The sword occupies two
vertical bag cells and adds 10 to the base 25 attack damage when equipped.
A potion restores up to 40 HP with a one-second server cooldown; full-health
and dead-player use is rejected. The 90 bag cells form two 5 × 9 pages, and
potions stack to 200. Item ownership, placement, rewards and consumption belong
to the server; quickslot assignments and window preferences are saved locally.

`make import-ui` converts 225 selected original UI images and stitches Yongan's
20 original DDS minimap tiles into image 226, using 294 pinned source files.
The minimap uses that stitched image; the area-map window uses its separate
original 171 × 214 image. Player markers come from subscribed state. Chat uses
the original centered entry and fading passive lines. Normal messages remain
limited to 160 characters by the server. Every exported UI texture is checked
against its decoded source-pixel hash. See [UI assets](docs/ui-assets.md) for
conversion, layout references and fidelity limits.

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
make export-web SERVER_URL=https://kcanakdag.com:8443 DB=mt2-p1-v4
make export-linux SERVER_URL=https://kcanakdag.com:8443 DB=mt2-p1-v4
make server-build
make deploy DB=mt2-p1-v4
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
`make deploy DB=mt2-p1-v4 WEB_DIR=dist/web-test DEPLOY_FLAGS='--allow-test-build'`.
The old `mt2-yongan-v2` guest and `mt2-accounts-v3` account databases remain
stored, while the public proxy selects the P1 database. Auth accounts and issuer
keys persist.
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
`tools/test_browser_accounts.py --actors --hardware --headless --inventory
--panels --targeting --combo --session-refresh` with matching test exports and an explicit
URL/database. See
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
client/spacetime_bindings/   Generated protocol-8 schema and provenance
client/addons/SpacetimeDB/   Pinned runtime SDK
client/addons/godot_mcp/     Editor tooling, excluded from exports
server/src/                 Identity, movement, map content and combat rules
server/content/             Generated authoritative map/action data (ignored)
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
