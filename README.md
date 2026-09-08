# Metin2 Godotime

A Metin2-inspired game with a **standard Godot/GDScript client and Rust
SpacetimeDB server in one monorepo**. The server owns movement, terrain height,
building collision, presence, combat and rewards. Blender converts selected
original character and Yongan assets. The original Metin2 executable cannot
connect to this game's new protocol.

The current [public development build](https://kcanakdag.com:8443/) uses protocol
24 with the original population package and latest loot presentation. Deployment
audits and 114 public browser/Linux checks passed on 2026-09-08, including field
combat, loot, return movement and account reconnect lifecycle. Refresh an older
open tab before signing in. Existing login accounts are retained; this new
world database has a separate character roster. See [deployment evidence](docs/distribution.md).

The local worktree now expects protocol 25 for persisted multi-event skill casts.
The public endpoint remains protocol 24. Use matching regenerated bindings and a
fresh test database for this local change; do not overwrite the public world.
Additional skills are not enabled by the schema change alone.

Local mob threat behavior now has a reusable two-account passive
retaliation and target-switching scenario (42 checks passed). See the
[development replay instructions](docs/development.md#test-scope-and-passive-mob-replay).
The worktree now uses protocol 25 with selectable mob packages and a shared mob
content hash. Its selected-registry training replay passed 74 checks, including
leader replacement, surviving followers and reconnect. The original Yongan population now runs locally: 2,835 mobs across 44 species,
with 22 two-client population/movement/reconnect checks passed. Full-population
exports now boot locally in browser/Linux with matching population subscriptions.
Both exports now render original mobs on a generated hunting-ground route.
The exported field/account lifecycle run now passes 110 checks. The focused performance replay now passes 42 checks; pausing test snapshots
measured about 34 FPS in Chrome versus 18 with snapshots on this workstation.
Hidden debug work and distant NPC instances are reduced. Release performance and
all-species combat qualification remain pending. The first original field encounter
now passes 47 exported checks, including inventory equipment, pointer selection,
held-Space damage and a full-health Hungry Stray Dog kill observed by both clients. Nearby mob presentation now
uses the original view range; 41 focused Main-scene checks pass with a 2,800-row fixture. The [client package installer](docs/development.md#install-converted-mobs-in-the-client)
now installs the selected 44-mob presentation catalog, 19 shared models and their
projectile resources; the installed Main scene passed 31 controlled checks.
Held attacks now wait for request completion instead of repeatedly sending from a
stale idle row. Focused scheduler/actor checks and 74 exported lifecycle checks
pass; cooldown/late-input notices and a combined field-return timeout remain under
investigation. The public build now uses protocol 24.

Original coin-pile and red-potion ground models are now installed locally through
[the reusable ground-item pipeline](docs/ground-items.md). The exported field/drop
replay passes 48 checks. A shared screen-space loot-label layout now separates
nearby names in native fixtures (21 layout and 30 item checks) and reviewed browser/
Linux field captures. The updated local two-client replay passes 49 checks. This
slice is now deployed and verified publicly; original drop effects remain pending.

Public test exports now make diagnostics opt-in. The latest focused public replay
passes 52 checks, including all eight character previews, field mobs, ordinary
browser reentry and peer-observed movement without the probe. Short browser
frame-cadence samples measured about 37 with capture and 59 without; this is not
engine FPS or a controlled release benchmark. Accounts and characters were preserved.

The latest public map-loading update also passes 43 focused two-client checks.
Streamed scenery now restores its resource IDs before loading; the ordinary
browser replay reports zero warnings or errors. All 20 isolated map sections pass
texture/dependency audits. Accounts and characters remain unchanged.

Items, future quests, mobs and classes follow the
[data-based content authoring contract](docs/rebuild/content-authoring.md):
versioned definitions select shared mechanics, with server-owned progress and
rewards. The first item registry now drives grid/stack rules, equipment
requirements, weapon power, names/icons and shared recovery effects. General
quest/mob registries and quest execution remain upcoming work. A selected
[classic character catalog and automated importer](docs/characters.md) now drive
the four classes, both sexes, starting stats and model/animation selection.

Quests are deferred while development prioritizes gameplay, mobs, map NPCs,
scenery, classes and abilities. The new [world-content workflow](docs/world-content.md)
adds validated population profiles and an isolated Godot development preview.
The [next mob pipeline](docs/mobs.md) now discovers selected original wildlife
stats and converts five models with 68 reachable clips. Native asset QA passes
304 checks. The candidate gameplay compiler links nine weighted attack variants,
per-species movement and recovery timing to those converted models; additional
enemy gameplay is not live yet.
The wildlife presentation fixture now passes 125 rendered Godot checks across
all five species and nine attacks, including slower playback, recovery and
death/respawn. This uses controlled state rows; server population integration
and exported multiplayer qualification remain pending.
The original Yongan population audit resolves 945 regeneration entries into
54 groups and 44 mob definitions across 12 source model folders. The current
five-definition selection covers no complete original selector; see
[population discovery](docs/mobs.md) before extending world spawns.
The derived `yongan-population.json` profile now resolves all 44 definitions and
covers every original entry's references. Skin-remap support preserves color
variants; three additional variants pass 179 rendered asset checks. This is
source/asset preparation, not an installed 44-mob population.
The full selection is now converted: 44 definitions share 19 textured GLBs with
271 clips, reducing model storage from 56 MB to 25 MB. The native Godot gallery
passes 2,818 checks. Group spawning and combat integration, including the recorded
projectile events, remain pending before these enemies can populate the live map.
The offline [regeneration stress tool](docs/mobs.md#original-regeneration-runtime-contract)
exercises the new Rust scheduler across the full inventory, including surviving
followers and replacement leaders. Live database integration remains pending.
The companion `population_placement` developer command checks original group
placement against the real server map; seed 42 places 2,853 members across all
945 groups, covering all 44 definitions. This is an offline placement report.
The full candidate gameplay catalog now links 78 attacks: 52 melee variants and
26 original projectile launches. The compiler also emits typed Rust combat tables
for the server; they are not installed as a live population yet. Projectile
presentation and magic damage still
need runtime integration; no additional enemy is live yet.
The [flight-definition importer](docs/mobs.md#flight-definition-discovery) now
resolves their four shared flight scripts and eight effect dependencies, preserving
original parameters and explicitly recording malformed source trails.
The original arrow mesh now converts through the shared Blender pipeline and passes
native Godot frame/geometry checks. Its opaque-target material now passes a
256-level pixel ramp; original-client blending parity remains unqualified.
The seven particle effects now have converted recipes and 12 pixel-verified
textures covering 22 systems. The reusable importer preserves curves, attachment,
texture-frame order and original render settings. See [particle conversion](docs/mobs.md#particle-effect-conversion).
The shared Godot emission/lifetime component passes 90 actual-engine checks across
all 22 systems. Particle motion now passes another 89 actual-engine checks,
including moving emitters and original gravity/drag order. The seven effects now
render in an isolated Godot gallery with 62 checks and reviewed captures;
live combat integration and browser qualification remain pending. The four original
flight definitions now pass 80 Godot trajectory/homing checks. All four flights
now connect to rendered particle/mesh attachments, trails and impacts, passing
61 native checks with reviewed arrow captures. The full mob presentation gallery
now passes 1,440 checks, including all 26 bone-based launch declarations, source
timing and resync deduplication. A world projectile component now resolves the captured target life and passes
125 native checks, including lost-target and cleanup behavior. A portable
projectile package and Godot loader now pass 145 native checks, including exact
particle texture pixels. Main now loads required projectile resources, connects
mob launch signals and resolves rendered target body centers. Its isolated native
fixture passes 31 checks, including active-shot disconnect cleanup. Server damage,
live population integration and exported/browser qualification remain pending.
Yongan's six authored Wild Dog homes pass **107 two-client checks** on a fresh
local database. The original City Guard is installed in the playable map layer,
with original placement, weighted idle animations and its attached weapon.
Its main-scene lifecycle and picking pass 38 native checks; the connection in that focused
fixture is simulated. A separate **103-check authenticated Web/Linux run**
qualifies approach, dialogue, Close/Escape, WASD and account lifecycle. Another
59 live checks cover private sessions, rejection, expiry and reconnect.
The updated development build is served at **http://127.0.0.1:8186** against
`mt2-p2-npc-areas-qa-r1-20260908`. Click the City Guard to approach and talk;
Close or Escape dismisses the dialogue, and movement resumes normally.
Character creation shows Warrior, Ninja, Sura and Shaman together, with the
selected class in front, original intro idle animations, hair, titles and
portraits. Both sexes are available. Native creation UI passes 61 checks.
Holding Space repeats attacks and links the common four-step Sword+0 chain for
Warrior, Ninja and Sura, and the Fan+0 chain for Shaman. Both Shaman appearances
receive the original starter fan, with its converted model and inventory icon.
Starter weapons are selected by class data; equipment and damage remain server-owned.
The fan milestone passes 106 live two-client checks, 69 rendered Godot checks
and 105 Chrome/Linux checks. The left hotbar button uses the original attack icon.
See the [status ledger](docs/rebuild/implementation-status.md) for evidence.
Both Warriors now use their original fourth-hit camera-wave timing and range.
The shared catalog importer adds supported events from the pinned motion data;
classes without such events receive no invented shake. This follow-up passes
76 isolated Godot checks and 106 exported Chrome/Linux checks.
Sura and Shaman fourth hits now knock surviving mobs back using their original
GREAT-hit metadata and the shared collision/recovery system. Mob attacks also
restore the correct normal animation after knockdown.
Sword+0 and Fan+0 now apply their original +22/+26 attack-speed bonuses to
server combat timing and client playback. Status and item tooltips expose those
values; equipment changes cannot retime an accepted attack. This slice passes
144 live two-client checks, 87 rendered actor checks and 106 Chrome/Linux checks.
The first Warrior ability, [Sword Spin](docs/skills.md), is available locally with
level-5 learning, point-based upgrades, original motions/icons and authorized
`/skill` rank commands. It passes 50 live skill/combat checks, 13 rendered UI
checks, 116 actor checks and 108 exported Chrome/Linux checks.
Trees, new mob types, additional weapon modes and further abilities remain pending. The local build uses a fresh
character database; previous databases and auth accounts are preserved. The public
endpoint remains unchanged.

The protocol-17 [training dummy](docs/training-dummy.md) is available near the
Yongan entry point in the local build. Its authored Blender model and passive,
reward-free behavior are profile driven. It passes 16 native presentation checks,
45 live two-client checks and 82 actual Chrome/Linux checks, with matching exports. All 44 classic abilities have been discovered and
converted for both appearances, but their full server mechanics are not yet live.
Dummy customization can be checked without Blender using
`python3 tools/build_training_dummy.py --profile /path/to/dummy.json --check-profile`;
see the [profile workflow](docs/training-dummy.md) for supported fields.

The [town-NPC package](docs/world-content.md) is now live locally: 32 original
NPC definitions at 41 placements, including the existing guard, merchants,
teachers, blacksmith, fishermen and static landmarks. Its latest expanded build
passes 53 isolated map-scene checks and 114 actual Chrome/Linux checks.
Opening an NPC conversation
also clears a previous combat target. Shops and quests remain pending.

The [latest NPC expansion](docs/world-content.md#remaining-original-point-placements)
adds six townspeople plus Weol Memorial and Nameless Flowers. The importer now
supports explicit source folders, model-local textures and truly static models.
Both actual export audits verify all 32 models; the browser route checks 23 entry
NPCs. One initial native connection drop did not recur in the unchanged repeat.

Six further original townspeople are converted and pass 144 native gallery checks.
Their [random-area spawn definitions](docs/world-content.md#original-area-spawn-npcs)
now use persistent server-owned positions and Godot subscriptions in a separate
protocol-18 QA database. Two-client replication passes 51 checks; the real map
scene passes 122 native checks with captured rows. Matching Web/Linux exports
now serve 38 NPC definitions at 47 placements on the local development endpoint;
browser qualification is recorded in the status ledger.

The current worktree is protocol 19 / trusted content schema 8 (item registry schema 2). Item actions
carry the server item's revision, rejecting stale/replayed mutations. Quantity
changes have a private transactional audit history and an offline reconciliation
tool. See the [item security contract](docs/architecture.md#item-integrity-and-replay-protection).
Its two-client security scenario passes 110 checks; another 10 Godot checks verify
revision payloads without optimistic item mutation. These changes are local and
are not deployed publicly.

The preceding protocol-11 isolated
two-client item scenario passes 50 checks: small/medium potions restore 300/800
HP gradually, reject invalid/repeated uses and consume exactly once; disconnect
clears pending recovery without refund or replay. The Godot component suite
passes 130 checks, and the rendered inventory test passes 21 checks. A further
94 live melee checks and 14 rendered tooltip checks passed. This is
historical local test evidence; the public endpoint remains protocol 4.

The preceding physical-damage slice integrates generated
weapon/mob values, server-owned Attack/Defense projections, and matching
protocol-10 bindings from fresh local test databases. Focused two-client runs
pass 101 melee and 65 area-finisher checks. The twenty-kill progression run
passes all 1,063 checks, including level two, private STR/VIT/DEX allocations,
damage changes and queued-action stat capture. A further 49 checks verify
pending-area cancellation and reconnect without replay. Web/Linux pass 94
functional checks, but the run's clean-engine-log gate fails on a separately
reproduced Godot embedded-tooltip issue. That older build is retained as test
evidence; the public endpoint remains unchanged.

`tools/content_compile.py diff` now compares saved/current generated content
pairs and reports changed fields plus the affected QA scope. See the
[content comparison workflow](docs/content-import.md#compare-a-content-update).

The latest local combat checkpoint accepts the selected four-hit Sword+0 combo,
area damage, knockback/standup and camera shake. Its **154-check exported
Chrome/Linux run** also passes account/reconnect lifecycle and both real session
refreshes, with zero position drift and no browser engine errors. Character
facing, hair and sword-alignment corrections are verified locally. See the
[acceptance record](.local/p2-finisher/root-acceptance-review.json) and
[implementation status](docs/rebuild/implementation-status.md). This protocol-9
checkpoint has not replaced the public protocol-4 build below.

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
Entry enables one real server/channel, Shinsoo/Yongan and all four classes in
both appearances. Sword Spin is the first supported Warrior skill; other
abilities, empires and social systems remain pending. Matching
original fonts, intro animations and complete behavior has not been established
against a running original client. The equipped sword is projected through a
small public presence row so peers can attach it without reading another
account's inventory. The bounded P2 slice adds source-backed level 1 male
Warrior stats, experience through the level-99 cap, quarter-step stat points
and automatic potion grants. Quests, death penalties, party experience and full Metin2 combat/stat balance
remain unimplemented.
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
make characters-build BLENDER=/path/to/blender
make skills-build
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

# Convert the selected stationary NPC, then install its public map-bound catalog.
python3 tools/import_npc_content.py --profile content/profiles/yongan-city-guard.json \
  --blender /path/to/blender --output .local/npcs/city-guard
make npc-install
make test-npcs GODOT=/path/to/godot

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
Makefile's retained legacy placeholder is `mt2-yongan-v2`; current protocol-9
Slice D development should pass a fresh explicit `DB`, such as
`DB=mt2-p2-finisher-yongan-local`. Slice D remains pending two-client
qualification. Public P1 exports/deployment still use `DB=mt2-p1-v4` until a
separately qualified rollout.

Two clients on one machine use different local profiles and separate accounts:

```sh
make client SERVER_URL=http://127.0.0.1:8184 PROFILE=alice
# In another terminal:
make client SERVER_URL=http://127.0.0.1:8184 PROFILE=bob
```

Make enables the `yongan` Cargo feature by default, requiring the ignored
`server/content/yongan.bin` and `.sha256` produced by `make bake-map`.
For the smaller training world, use a fresh protocol-9 name such as
`make server-publish SERVER_FEATURES= DB=mt2-p2-finisher-training-local`, then
select that database in both clients. Raw Cargo without `--features yongan` also
selects training.
Both variants use application protocol 9. Earlier databases do not contain all
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
| Space | Attack the selected exact monster, or the nearest valid enemy when no target is selected; Sword+0 accepts the current four-step server-timed common chain, whose Slice D qualification remains pending |
| E / Z | Collect nearby gold/items with server distance/ownership validation |
| I / Inventory button | Open the two-page inventory |
| Item left click, then destination; drag/drop | Carry or move an item between valid bag/equipment/quickslot locations |
| Item right click | Equip/unequip the sword or consume a potion |
| 1–4 / F1–F4 | Activate one of the eight visible quickslots |
| Shift+1–4 / quickslot arrows | Select a quickslot page |
| M / minimap atlas button | Open/close the draggable original Yongan area map |
| K / Skills tab | Open skill learning/upgrades; drag learned skills to quickslots |
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
source-defined input window requests `combo_2` or `combo_3`; a fourth request
inside `combo_3`'s window queues terminal `combo_4`. The server alone schedules
and publishes each transition; both clients keep presenting the current action
until its subscribed row changes. An accepted movement intent or target clear
cancels a queued link, while renewing the same exact target preserves it. The
current accepted action's authoritative root travel and hit continue after those
queue cancellations; stored ordinary locomotion begins after the attack hold
ends. Target death clears future links but the lethal action continues its root
travel through clip end. A targetless or missed chain may animate and travel
without inventing damage or a new selection.

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
client/spacetime_bindings/   Generated current-protocol schema and provenance
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
