# Development workflow

## Staging selected charge skill content

`tools/build_skill_catalog.py --profile PROFILE --output CANDIDATE --offline`
builds a candidate without replacing the installed catalog. Omitting `--output`
retains the existing install destination. `physical_charge_v1` profile entries
use `weapon_class: "sword_or_two_handed"` and `hits_per_life: 1`; the currently
supported source charge is Warrior Dash, vnum 5, motion `skill_5`, minimum level
5 and maximum rank 20. Both appearances must already be imported.

The compiler preserves charge motion collision events as `source_hit_events` for
inspection. They are not damage deadlines. A typed `charge` policy carries speed,
duration, push distance and main-target stun; ordinary skill event windows are
rejected on charge entries. Validate Rust generation with:

```sh
cargo run --manifest-path server/Cargo.toml --locked --offline \
  --example compile_live_skills -- CANDIDATE DEFINITIONS_RS
```

This produces Rust source; it does not build or publish a module using that
candidate. To build an isolated candidate module, set `MT2_SKILL_CATALOG` to its
absolute path for the Cargo build. The selector defaults to the installed catalog;
leave it unset for normal builds and the default compiler fixture tests. This
does not install client assets or publish a database.

Protocol 29 permits explicit `begin_charge(vnum, expected_revision)` activation
with an equipped sword while preserving a selected target. The normal
`cast_skill` intent validates the selected target for completion. The
working candidate also implements immediate target strikes and active-charge
consumption. CRUSH/stun is now wired for surviving ordinary monsters, with public
exact-life `monster_stun` state; the two-client Brown Bear replay verifies push,
stun and expiry. Death-during-stun and reaction-arrival-during-stun/expiry replays
also pass; reverse ordering and rendered playback remain unqualified.
Two-handed weapon runtime support remains pending.
The normal four-skill profile remains the installed and public selection; the
public release is still protocol 26. Use matching regenerated bindings and a
fresh disposable database for protocol-29 QA.

`tools/test_progression_admin.py charge --fixture PRIVATE --report REPORT` uses
the existing retained-account workflow to exercise charge payment, shared status,
boosted movement, expiry, rejection, disconnect and reconnect. Supply the normal
`--server`, `--game-server`, `--database` and `--godot` arguments. It requires a
fresh five-skill candidate database with only the first fixture account authorized
for the level-five setup command; the second account remains unprivileged. Do not
reset an existing world or repeat this setup against already-mutated skill rows.
The latest replay passes 34 checks. Normal `--network-only --movement-attacks`
account QA passes 84 checks against the same protocol-27 schema. This is headless
network acceptance, not normal UI, rendered effects or exported-browser evidence.

The `charge_strike` phase uses the same arguments and fresh-database requirements
to exercise immediate and previously activated strikes against the training
dummy, range rejection, payment, shared damage/removal, cooldown preservation and
replayed requests. Use a separate fresh database from the `charge` activation
phase because both phases learn the skill from revision zero. Check the current
implementation ledger for actual replay results; adding a phase is not evidence
that its gameplay acceptance passed.

The `crush` phase uses the same retained-account arguments with a fresh training
database whose placement 1 is original Brown Bear vnum 113 (845 HP). Compile a
current imported mob package with `build_mob_catalog.py`, select it using
`MT2_MOB_CONTENT`, and select the authored training placement using
`MT2_POPULATION_PROFILE`. Keep the five-skill Dash candidate and QA-only bootstrap
authorization. The replay checks a surviving monster's shared displacement,
four-second stun, held position, no attacks/damage during observation, expiry and
AI recovery. The ordinary dummy phase cannot qualify these effects because the
dummy is intentionally stationary. Never publish a bootstrap QA module publicly.

The `crush_death` phase uses that same module on another fresh database. It
prepares level 99/rank-20 Sword Spin through authorized admin commands, then uses
normal Dash and Sword Spin damage to kill the original bear before stun expiry.
It checks shared stun removal, a new respawned life, full health and no restored
stun. Its two-leg approach deliberately establishes facing toward the target:
Sword Spin follows the caster's current facing and does not require a target.

The `crush_overlap` phase uses the same fresh Brown Bear module/placement contract
and prepares rank-one skill 16 through authorized setup. It schedules a GREAT
reaction during Dash stun and verifies that the reaction chain crosses the stun
deadline, then checks shared motion cancellation, no queued restart and AI
recovery. Use the updated module containing the motion-queue fix; the older
CRUSH/death frozen modules predate it.

Opening an installed actor package in Godot may create a PNG alias that removes
an embedded image's `.dds` suffix (for example, `actor_face.dds.png` becomes
`actor_face.png`). The shared character/NPC package validator permits this exact
alias only after comparing decoded RGBA pixels and dimensions against the
hash-checked GLB. Changed aliases and unrelated files still reject. Preserve the
editor's generated files; do not delete them or bypass package validation to make
exports pass. Export staging reapplies the standard actor texture import policy
to both canonical and alias PNGs.

## Streamed resource identities

`StreamResourceUids` (`client/scripts/world/stream_resource_uids.gd`) restores
saved dependency UID mappings after verified scenery packs are mounted and before
loading a chunk. It reads the actual mounted resource dependency graph, validates
all mappings before registration, rejects existing-ID conflicts, and only permits
map resources plus the shared terrain shader. Completed graphs are cached per
stream instance. This avoids relying on the full export's UID cache after splitting
world resources away from the browser startup pack.

`tools/check_world_packs.py` stages this same helper and rejects invalid-UID
warnings while checking each of the 20 chunks in a fresh loader. The focused
`client/tests/stream_resource_uids_smoke.gd` takes an exported world directory and
must run in a clean project containing the helper, without an imported map UID
cache. It covers namespace/missing-resource rejection, collision preservation,
successful registration, repeat calls and actual chunk instantiation.

## Account/network-only qualification

`tools/test_accounts.py --network-only` exercises authenticated ownership,
subscriptions, bidirectional movement, rejected intents, character switching,
disconnect and reconnect without invoking the older basic-combat fixture. Reports
label this scope `account-network`; the default remains `account-combat` and the
flag cannot be combined with `--progression`. It does not qualify skill casting.
Use it for protocol/schema work and run the relevant combat replay separately.
The legacy combat fixture still expects one-second basic swings and fixed 35
physical damage; its failures must not be reported as passing network-only QA.

Add `--movement-attacks` to `--network-only` to exercise moving into an accepted
attack, matching attack clocks, recovery and resumed movement for both clients.
The report uses scope `account-movement-attacks`; it adds ten checks without
invoking the old damage fixture. `client/tests/movement_attack_smoke.gd` holds the
focused replay and is staged by the runner. This proves acceptance/subscriptions,
not exact sub-tick displacement, damage balance or rendered animation. The latest
fresh local replay passes 84 checks; the unextended network replay passes 74.

## Test scope and passive mob replay

The original-population browser replay distinguishes installed catalog species
from the live census. Random group variants and failed terrain placement mean
not every possible species must exist simultaneously. `population_summary`
requires matching instance-ID/species maps in both client subscriptions, unique
valid IDs, finite positions and registered species, retaining the full-world
minimum of 2,001 ordinary mobs. It reports catalog/observed counts and unobserved
species separately. Package audits prove installed definitions; a census does not
prove all-species combat or all regeneration entries. Four focused browser event/
census/drop tests are in `tests/test_browser_mob_events.py`.

Hunting routes target positions, not regeneration identities. A route captured
against one database may end outside the camera/combat range of another database's
randomly placed groups. Use `server/examples/world_route.rs` with the observed
database's subscribed mob position to generate a terrain/collision-checked route;
do not move or reseed server mobs to fit a replay. The public population rollout
uses `.local/public-population-r1/hunting-route.json` (goal `[780,570]`, near its
observed Wild Dog group), while the committed route remains the local fixture.
The field replay retains its completed evidence in `samples.field_mobs` even if
a subsequent return-to-town check fails.

Use targeted checks for changed code and affected behavior during implementation.
Reserve full-suite runs for major milestone completion or demonstrated broad
impact. Repeat a passing check only after a relevant change or unresolved finding;
required multiplayer/export checks still apply to their corresponding changes.

The training-only passive mob fixture exercises normal authoritative combat with
two authenticated clients. Build without `--features yongan`, freeze the module,
and publish to a fresh `mt2-p2-` database (never reset an existing database):

```sh
MT2_COMBAT_TEST_FIXTURE=passive-wild-dog-v1 \
MT2_AUTH_ISSUER=http://127.0.0.1:8186/auth MT2_ALLOW_GUESTS=0 \
cargo build --manifest-path server/Cargo.toml --locked --offline \
  --target wasm32-unknown-unknown --release
# Copy the resulting module.wasm and publish it to a new disposable database.
.local/venv-dev/bin/python tools/test_physical_combat.py \
  --server http://127.0.0.1:8186 --game-server http://127.0.0.1:13223 \
  --database mt2-p2-<fresh-name> --scenario aggro \
  --godot /path/to/godot --report .local/<fresh-report>.json
```

The build rejects this fixture combined with Yongan or a population override.
Do not deploy its training module to the public endpoint. The scenario checks the
explicit fixture marker before exercising passive proximity, retaliation,
higher-threat switching and victim disconnect. Evidence is recorded in
`.local/mobs/passive-runtime-r1/acceptance.json`: 42 live checks passed. The
previously started all-target Rust run (152 library tests) and full development
lint also passed; these are not a requirement to repeat after each small edit.


The shared combo smoke helper validates attack duration against the public action's
captured speed using ceiling-rounded source timing. Sword+0's +22 bonus must not
be tested as a one-second unscaled animation. The population scenario uses this
helper; use a new database after its kill/reward/respawn sequence when repeating
the full initial-state fixture.

Run commands from the repository root. The game uses standard Godot with
GDScript and a Rust SpacetimeDB module. Python runs development and asset tools;
Node runs the authentication service and local development proxy/MCP tools.
The auth service is deployed separately; no Python/Node runtime belongs inside
a player's Godot client build.

After wildlife conversion, `tools/build_mob_catalog.py --content CONVERTED_DIR
--output NEW_DIR` compiles the candidate motion/gameplay catalog and checks it
against the conversion receipt and exact Blender animation report. See
[mob tooling](mobs.md) for its source timing policies and remaining runtime work.
The command also emits `combat-registry.rs`: candidate Rust combat tables using
the server’s existing definition types, with its hash recorded in the receipt.
The tables include species health, movement, collision, reaction and XP/gold
values. AI, spawn/regeneration policy and item drops are not installed by this
command.
The command is offline and does not install content or restart services.
The full selection now compiles projectile launch declarations separately from
melee windows. Catalogs and receipts expose `unimplemented_runtime_requirements`;
successful compilation does not establish that those mechanics are playable.
The `test_actors.py --scenario mobs` timing fixture now accepts the full selection,
including source-timed projectile signals and converted attachment bones. It uses
controlled state rows and does not qualify live combat or network delivery;
`test_npc_content.py` remains the separate converted asset gallery.
It also writes `presentation.v1.json`. Use `tools/test_actors.py --scenario mobs
--mob-content CONVERTED_DIR --native --godot GODOT --output NEW_DIR` to check the
candidate through the real PvE actor in an isolated project. This runner merges
the candidate into its disposable fixture only; it does not modify the installed
manifest or establish server subscriptions.

`tools/discover_mob_population.py --output NEW_DIR` audits original Yongan
regeneration/group dependencies from the pinned local server checkout. Override
`--source-checkout`, `--map` and `--profile` for another reviewed source map or
definition selection. It reads committed blobs, records hashes and never installs
spawns, fetches assets or alters a database. See [population discovery](mobs.md).
`tools/build_population_profile.py --population POPULATION_JSON --output NEW_JSON`
derives a bounded selection from that audited dependency closure, retaining
existing actor IDs from the base profile. The checked-in Yongan population profile
was generated this way; `tools/discover_mobs.py --profile PROFILE --offline
--output NEW_DIR` verifies its cached model/race/motion metadata without installing
assets. Omit `--offline` only when the selected pinned metadata needs fetching.

Pass `--profile content/profiles/yongan-population.json` to
`tools/import_mob_content.py` to convert the full selected population. Conversion
deduplicates identical model inputs while retaining all definition IDs and hashes
both the unique Blender report and its expanded per-definition report. The existing
`tools/test_npc_content.py --content CONVERTED --native --godot GODOT --output NEW`
gallery checks every alias against the actual shared GLB clips. See
[mob conversion](mobs.md#convert-and-inspect-selected-wildlife) for report semantics.

## Attack target protocol fixture

The worktree requires protocol 20; the current public export remains protocol 19. To run `test_physical_combat.py --scenario melee`,
publish a fresh **training** module (build without `--features yongan`) to a new
`mt2-p2-...` database. The scenario intentionally expects one dog on the training
map; a Yongan module is not interchangeable. Use `--server` for the authentication
origin and `--game-server` for the direct local SpacetimeDB endpoint when the
development proxy only allows its currently served database. Generate bindings
from the new module before running the test. Preserve existing databases.

## Original population diagnostics

`tools/test_particle_emission.py --godot GODOT --catalog PARTICLE_CATALOG
--output NEW_DIR` runs the actual GDScript emitter lifecycle in an isolated Godot
project. Use `--expected-systems COUNT` for a different selected emission fixture;
the default remains the 22-system projectile fixture. Its source-bound report distinguishes emission checks from rendering
and server integration, which are not exercised. See [emission lifecycle](mobs.md#godot-emission-lifecycle).
Add `--scenario motion` to exercise the connected particle kinematics, moving
emitters and deterministic replay; this is still non-rendering QA.
`--scenario render` instead runs a native Linux/Xvfb Compatibility gallery with
the converted textures and hashed captures. See [particle rendering](mobs.md#selected-particle-rendering)
for its observed driver and remaining original-client/browser comparison work.
`--scenario flight --catalog FLIGHT_INVENTORY` exercises all four source trajectories
and homing in headless Godot. This scenario consumes the flight inventory rather
than particle recipes; see [flight trajectories](mobs.md#original-flight-trajectory-component).
Use `--scenario projectile --catalog PARTICLE_CATALOG --flights FLIGHT_INVENTORY`
for the native combined flight/attachment/impact/trail gallery. Add `--meshes
MESH_CATALOG` to include the converted arrow; omitting it checks the three particle
flights and rejection of a missing mesh resource. Use `--scenario mesh --catalog
MESH_CATALOG` for the arrow animation/color-ramp checks. These native scenarios
use isolated Linux/Xvfb projects, verify copied asset hashes and preserve reports;
timed-out gallery runs terminate their isolated process group. See
[combined projectiles](mobs.md#combined-particle-projectiles). The same gallery
now checks the world component
[against controlled target replicas](mobs.md#world-projectile-lifecycle-component),
including exact-life tracking and lost-target behavior.

`tools/build_projectile_catalog.py --particles PARTICLES --flights FLIGHTS
--meshes MESH_CATALOG --output NEW_DIR` assembles verified converted dependencies
into a portable runtime package. Test it with `test_particle_emission.py
--scenario package --catalog NEW_DIR/catalog.v1.json --godot GODOT --output QA_DIR`.
Copy the generated texture import sidecars with its assets; default Godot import
changed a source texture during QA. See [portable package](mobs.md#portable-projectile-package).

`tools/test_world_projectiles.py --godot GODOT --mobs CONVERTED_MOBS
--projectiles PROJECTILE_PACKAGE --output NEW_DIR` stages the candidate mob catalog
and portable projectile package in an isolated copy of the actual Main scene.
It uses controlled state rows and a connection spy, captures all four projectile
types, and checks source removal, animation deduplication and active-shot disconnect.
The fixture controls Main's simulation clock during rendering; it does not prove
live subscriptions, server damage, browser behavior or installation readiness.

`python3 tools/import_particle_effects.py --effect VIRTUAL_MSE --output NEW_DIR`
converts explicitly selected particle recipes and their referenced textures.
Repeat `--effect` for a bounded selection; use `--offline` after caching the
selected sources. The tool verifies decoded texture pixels and records source/tool
hashes, without installing content. See [particle conversion](mobs.md#particle-effect-conversion).

`tools/import_projectile_mesh.py --effect VIRTUAL_MSE --blender BLENDER --output NEW_DIR`
converts selected mesh-only projectile geometry through the shared Blender path.
Use `--offline` once its MSE/MDE/texture sources are cached. The output retains
the original material recipe and marks runtime rendering requirements; it is not
installed automatically. See [projectile meshes](mobs.md#projectile-mesh-conversion).

`python3 tools/discover_projectiles.py --catalog GAMEPLAY_JSON --offline --output NEW_DIR`
discovers the exact MSF set selected by the candidate mob attacks. Omit `--offline`
when those pinned text assets need fetching. The hash-bound inventory records flight
parameters and resolves MSE dependency paths; it does not install effects or run
original code. See [flight discovery](mobs.md#flight-definition-discovery).

For offline original-population lifecycle diagnostics, use
`cargo run --manifest-path server/Cargo.toml --offline --features yongan --example
regeneration_stress -- /path/to/population.v1.json`. The command checks inventory
integrity and exercises leader destruction/refill using the reusable Rust scheduler.
It never contacts a server or places actors on the map. See [mob regeneration](mobs.md)
for the scenario assumptions and pending live integration.
Append `--checkpoint NEW_FILE` to save the initialized stress fixture, then run
the command in a separate process with `--resume FILE` to exercise restoration.
The tool refuses to overwrite an existing checkpoint. These are offline developer
files; they do not restore a live database.

`cargo run --manifest-path server/Cargo.toml --offline --features yongan --example
population_placement -- /path/to/population.v1.json 42` emits seeded group positions
using the shared sampler and real server collision data. Redirect stdout to an
ignored JSON report. Change the seed to inspect another placement; no server or
editor is modified.

## Classic character builds

Use `make characters-build` for the selected four-class/eight-appearance pipeline,
with `BLENDER`, `CHARACTER_OUTPUT` and optional `CHARACTER_FLAGS='--offline --replace'`.
Each output is a new revision; replacement preserves the previous installed
package. The [character workflow](characters.md) documents inputs, receipts,
runtime limits, the two-client `make test-classes` command, and exported
`tools/test_browser_accounts.py --classes` qualification.
The item package now includes Fan+0; run `make content-build` and the UI importer
when updating selected weapon models/icons. `tools/test_actors.py --scenario fan
--native` checks both Shaman attachments and held input. For a focused live replay,
use `tools/test_physical_combat.py --scenario classes --class-id 3` with the usual
explicit server, database, Godot and report arguments.

The class-2 and class-3 scenarios now land ordinary fourth-hit knockback on
separate real Wild Dogs for both sexes, then check subscribed displacement and
recovery. Run against a fresh explicitly named disposable database; reusing a
damaged dog is not a fresh replay. Their `CLASS_ACTION_EVIDENCE` log includes
both clients' force traces. The native actor fixture additionally checks the
normal attack clip after knockdown, with its normal animation blend allowed to
settle before capture.

Use separate `--work-dir` and `--output-dir` values when running Web/Linux exports
concurrently. Each `tools/export_playable.py` invocation also supplies its own
`TMPDIR`, since Godot uses a fixed `tmpproject.binary` name while exporting packs.

The current application protocol is 18. The local endpoint serves the matching
area-NPC exports against `mt2-p2-npc-areas-qa-r1-20260908`. Class-aware creation and progression
require regenerated bindings and the same installed character catalog used for
the server build. Publish incompatible schemas to a fresh database and preserve
existing data. A local auth issuer build must stay on its matching local endpoint.

The isolated `tools/test_target_client.py` runner requires the installed base
actor, UI and character packages. It stages all three, including the character
catalog hash in its report. Run `--suite content_gate --suite screen_wave` to
check class-aware camera-event routing and the existing screen-wave timing and
lifecycle rules. Class routing uses synthetic events on registered motions;
this routing fixture is separate from `screen_wave`, which now also checks the
actual imported events on both Warriors. The exported account runner accepts
`--classes --warrior-effects` for the female Warrior finisher scenario; ordinary
`--classes` retains the Ninja/Shaman scenario.

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
P1 exports and deployment explicitly target `DB=mt2-p1-v4`, retaining the
preceding account and guest databases. This does not change the tested local
default.

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

For an isolated database that is intentionally not on the proxy allowlist, keep
authentication on the issuer origin and select the game service separately:

```sh
python3 tools/test_accounts.py --server http://127.0.0.1:8186 \
  --game-server http://127.0.0.1:13223 --database mt2-p1-final
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
Those historical guest Yongan/training reports used application protocol 4 and
`SERVER_FEATURES=` for training. The later authenticated progression and target
slices use separate databases and synchronized protocol 5 and 6 clients,
respectively.

For gameplay changes, verify two independently authenticated accounts see each
other, each movement reaches the other subscription, and disconnect removes
presence. Include rejected reducers and reconnect when changing lifecycle.
The server validates actions even when the UI limits inputs. A database query
or plausible snapshot alone does not prove subscribed or rendered behavior.

The development scene exposes `dev_snapshot()` for runtime inspection. Use it
with scene trees, screenshots and actual input. Debug controls send normal
validated reducers; privileged actions require explicit server authorization.

## Maintaining the full-game plan

[docs/full-rebuild-plan.md](full-rebuild-plan.md) is the entry point for the
source-backed roadmap. The canonical feature/system records are
`docs/rebuild/plan.json`; `feature-catalog.md` is generated from them. Keep source
pins, project status, implementation prerequisites and behavioral coupling
distinct. New evidence must update the corresponding source inventory/audit;
do not turn upstream enum presence into an implemented-project claim.

```sh
make check-plan
# After editing the canonical JSON:
python3 tools/check_rebuild_plan.py --write
```

`make check` includes `check-plan`. The checker requires valid IDs, source
provenance, scope/status/evidence, known prerequisites, acyclic implementation
order, existing JSON inventories and a current generated catalog. It is an
offline structural check, not proof of source semantics or full-game parity.
The audit documents preserve source and runtime evidence limits separately.

The [tooling plan](rebuild/development-and-admin.md) proposes general content,
animation, quest, map, admin and test automation. Its future CLI names are not
implemented commands. Continue using the tested commands elsewhere on this page
until a vertical slice implements and documents their replacements.

## Protocol 6 target locking

Target Slice A uses the same trusted action definitions and argument-free
`perform_attack()` reducer as the preceding combat slice. Build outputs in this
slice must use an isolated Cargo target directory so they cannot replace the P1
module artifact:

```sh
MT2_AUTH_ISSUER=http://127.0.0.1:8186/auth \
MT2_ALLOW_GUESTS=0 \
MT2_PROGRESSION_BOOTSTRAP_IDENTITIES= \
MT2_COMBAT_TEST_FIXTURE= \
CARGO_TARGET_DIR="$PWD/.local/p2-target/server-target" \
cargo build --manifest-path server/Cargo.toml --locked --no-default-features \
  --target wasm32-unknown-unknown --release
```

With no fixture selector, training and `--features yongan` each retain their
normal single Wild Dog. The disposable two-target module is a training-only
build:

```sh
MT2_AUTH_ISSUER=http://127.0.0.1:8186/auth \
MT2_ALLOW_GUESTS=0 \
MT2_PROGRESSION_BOOTSTRAP_IDENTITIES= \
MT2_COMBAT_TEST_FIXTURE=dual-wild-dog-v1 \
CARGO_TARGET_DIR="$PWD/.local/p2-target/server-target" \
cargo build --manifest-path server/Cargo.toml --locked --no-default-features \
  --target wasm32-unknown-unknown --release
```

The selector accepts only `dual-wild-dog-v1`; combining it with `yongan`
fails at build time. Leave the selector unset for the required all-features
clippy check. The reviewed JSON fixture contains two Wild Dog 101 placements
with independent trusted AI/leash/respawn homes and exposes a distinct
`training-v2-dual-wild-dog-v1` content identity. Publish it only to a fresh,
disposable database; it adds no runtime spawn reducer or capability.

After publishing the exact default-deny dual artifact and generating matching
Godot bindings, run:

```sh
python3 tools/test_targets.py \
  --server http://127.0.0.1:8186 \
  --game-server http://127.0.0.1:13223 \
  --database <fresh-protocol-6-dual-target-database> \
  --report .local/p2-target/targets-report.json
```

The runner checks auth health, the target schema, trusted definitions, an
isolated Godot import and the real script parser before registering its two
accounts. It then exercises the private target projection, same/clear/reselect
deadline, stale and missing generations, selected-far/no-near-fallback behavior,
fallback on-hit presentation, immutable pending hits, reconnect and both owner
and monster-life cleanup. It restores a retained damaged test monster only by
ordinary validated combat and natural production respawn.

The accepted run in
`.local/p2-target/targets-root-reconnect-fixed-20260907.json` passed 53 of 53
checks with no engine or script errors. Its reconnect step completed within 850
ms and opened the same account with the same still-valid JWT; the separate
exported progression QA covers real auth-token refresh timers and full
`AccountFlow` behavior. The local result does not qualify the public P1 route.

## Protocol 7 bounded Sword combo

Slice B extends the generated trusted action schema with the first two declared
male-Warrior one-hand actions and their source-normalized combo input timings.
Build it in its own target directory with the normal one-dog fixture and default
deny settings:

```sh
MT2_AUTH_ISSUER=http://127.0.0.1:8186/auth \
MT2_ALLOW_GUESTS=0 \
MT2_PROGRESSION_BOOTSTRAP_IDENTITIES= \
MT2_COMBAT_TEST_FIXTURE= \
CARGO_TARGET_DIR="$PWD/.local/p2-combo/server-target" \
cargo build --manifest-path server/Cargo.toml --locked --no-default-features \
  --target wasm32-unknown-unknown --release
```

The client continues to send only `perform_attack()`. The server classifies its
own receipt time against generated `combo_1` timing, publishes `combo_2` only
after an accepted link, and keeps each pending hit immutable. Run the focused
static checks with the same isolated target directory:

```sh
CARGO_TARGET_DIR="$PWD/.local/p2-combo/server-target" \
cargo test --manifest-path server/Cargo.toml --all-features

CARGO_TARGET_DIR="$PWD/.local/p2-combo/server-target" \
cargo clippy --manifest-path server/Cargo.toml \
  --all-targets --all-features -- -D warnings
```

After generating bindings that match one of the reviewed fresh protocol-7
databases, run the authenticated two-client smoke:

```sh
python3 tools/test_combos.py \
  --server http://127.0.0.1:8186 \
  --game-server http://127.0.0.1:13223 \
  --database <fresh-protocol-7-combo-database> \
  --report .local/p2-combo/combo-report.json
```

The runner checks auth health, schema fields, trusted-definition identity, an
isolated Godot import, generated bindings and the real script parser before its
only two registrations. It never retries a rejected signup. The live phases use
two authenticated subscriptions and record public action timestamps plus exact
reducer-result timestamps. They cover targetless zero-damage chaining, selected
far misses, duplicate queue preservation, two 35-damage hits, a real equipment
mutation while the first hit is pending, target death/new life, two-way movement
and queued disconnect/reconnect cleanup. Retained fixture damage is restored
only with normal combat and the production 12-second respawn. This smoke is
deliberately limited to the flat `training` map with exactly one dog. It parks
the observer at `(-18, 6)` and uses `(-18, 3)` as the actor's safe waypoint,
both inside the 32 m bounds and outside the dog's 16 m home-chase radius. Before
far or targetless cases it requires authoritative arrival plus a dog idle at its
trusted `(3, 3)` home for 0.5 seconds.

The isolated implementation checks currently pass 60 server unit tests, four
Rust build-boundary tests, one generated-definition test, clippy with all targets
and features, GDScript formatting/lint and the real Godot parser. Root's
source-verified `.local/p2-combo/build-manifest-root.json` records the gameplay
hash and three default-deny WASM hashes. The fresh local training, dual-training
and Yongan database identities are in
`.local/p2-combo/publication-root.json`; publication used `delete_data=never`.
The focused two-client run passes all 71 checks in
`.local/p2-combo/combo-root-safe-fixture-20260907.json` (SHA-256
`becc30159ffab215cdb3c25f7d2c8453fe338383960daba53da93136c4b6e7ad`).
Its targetless direct input arrived at 558813 microseconds. Its equipment test
recorded accepted queue and unequip receipts at 186291 and 186329 microseconds,
both before the immutable first hit at 192308 microseconds, followed by exactly
35 damage and no second step. `.local/p2-combo/root-headless-acceptance.json`
binds this report and the frozen harness SHA to the reviewed server manifest.
This qualifies the headless server slice. It does not establish later chain
steps, root motion, skills, automatic chase, public deployment, exported-client
behavior by itself or full P2 completion.

The protocol-7 dual-target regression passes 51 checks in
`.local/p2-combo/targets-root-first-20260907.json`. The instrumented Web and
Linux packages pass their actual-PCK audit in
`.local/p2-combo/exports-probe2-root-reviewed.json`: 832/1635 paths, 226 exact UI
images, three actors, 40 clips, 20 Web world sections and two 11-frame target
effects. The source freeze covers 212 unchanged files.

Run the complete instrumented local export composition with:

```sh
.local/venv-dev/bin/python tools/test_browser_accounts.py \
  --url http://127.0.0.1:8186 \
  --database mt2-p2-combo-yongan-20260907 \
  --native .local/p2-combo/native-probe2/MT2Spacetime.x86_64 \
  --output .local/p2-combo/browser-combo \
  --hardware --headless \
  --progression --targeting --combo \
  --actors --inventory --panels --session-refresh
```

That actual run passes all 288 checks. Browser and native queues are accepted at
249435 and 284780 microseconds after step 1, with step 2 published at 536850 and
540570 microseconds and health `100 -> 65 -> 30` on both clients. Same-target
renewal preserves each queue. Held/released WASD, a real ground click and target
clear remove three separate queues while each captured first hit still deals 35.
The composed actor, inventory, target, progression and account lifecycle paths
pass through both real four-minute refresh timers. The 53-row refresh trace has
52/50 valid Web/native position rows and 1/3 transient pending rows during
lifecycle; every valid row has zero authoritative coordinate drift and no row is
invalid. No browser engine errors or native engine-log errors were observed; the
intentional ownership reducer rejection remains recorded. The native snapshot
reader recovers three torn writes in at most two attempts with zero unavailable
reads; these file reads are not gameplay retries. The accepted report is
`.local/p2-combo/browser-root-independent-followup-20260907/report.json`, whose
SHA-256 is
`5d015eb38261ed2daa25fe447c6f4bc1b9a8c48c213932160dd5451239c8cc9c`.
`.local/p2-combo/root-acceptance-review.json` binds the final report, headless
report, server build and instrumented PCK audit; its SHA-256 is
`3299380864b684aea3d6ad582392753c625a3c0eb675ee252512ed28820e0628`.
It records 65 Rust tests, 143 Python tests, 71 actor checks and 56 focused
component checks; the configured lint suite passes.

Earlier diagnostic reports remain preserved under `.local/p2-combo`. The final
headless harness records exact reducer receipts, extrapolates from the received
server-clock callback, keeps the strict pre-hit boundary and waits at reviewed
training waypoints. The exported helper schedules its one follow-up from the
first accepted ACK, independently latches rendered/public step 1, and waits for
authoritative and rendered monster-home stability before one movement input.
These synchronization rules are test setup, not gameplay authority.

Slice B is accepted only as this bounded local instrumented Web/Linux slice.
Normal exports exclude the fixed-input probe and were not exercised here.
Public Slice B gameplay/deployment, Windows execution, Godot MCP and
original-client parity remain unverified; later combo steps, root movement, full
P2 and the full game remain incomplete.

## Protocol 8 three-step combo and root displacement

Slice C extends the same argument-free `perform_attack()` intent through the
common `combo_3` action and adds server-owned displacement for all three combo
steps. Trusted schema 4 derives exact local-space endpoints and durations from
the pinned GR2 metadata. Runtime movement uses bounded action-relative 50 ms
quanta and the existing terrain/sweep rules; its linear endpoint policy remains
an approximation of the unavailable proprietary Granny within-cycle curve and
transition blend. Root-enabled actions also retain the heading captured at
action acceptance across their hit; established rootless target-facing behavior
is unchanged.

Run the server checks in the isolated Slice C target directory:

```sh
CARGO_TARGET_DIR="$PWD/.local/p2-rootmotion/server-target" \
cargo test --manifest-path server/Cargo.toml --all-features

CARGO_TARGET_DIR="$PWD/.local/p2-rootmotion/server-target" \
cargo clippy --manifest-path server/Cargo.toml \
  --all-targets --all-features -- -D warnings
```

The accepted Slice C report below used protocol 8. The current regression
runner follows the same paths on protocol 9 and additionally accepts a safe
targetless `combo_4`, checks its root endpoint, then rejects a fifth input.
After root publishes a fresh default-deny protocol-9 training database and
generates matching bindings, run the single-process, two-account headless smoke:

```sh
python3 tools/test_combos.py \
  --server http://127.0.0.1:8186 \
  --game-server http://127.0.0.1:13223 \
  --database <fresh-protocol-9-training-database> \
  --report .local/p2-finisher/combo-regression-fresh.json
```

The runner stages and parses both the accepted combo base and focused root
script before its only two registrations. It uses only normal authenticated
movement, targeting, attack and equipment reducers. The composed phases cover
two-way subscriptions, retained-dog restoration through ordinary combat,
the targetless four-step chain, a far-missed three-step chain, exact
`35 + 35 + lethal 35`
damage, terminal target-death root continuation, the flat training stone's
swept collision, equipment queue cancellation with the current trajectory
preserved, and disconnect/reconnect without residual movement replay. Reducer
receipts and the first public action-transition rows anchor timing and position
evidence. This smoke requires the flat one-dog training fixture; it does not
reset or mutate an existing database outside normal gameplay.

The accepted revision-2 composed headless run passed 91 checks in
`.local/p2-rootmotion/revision2/headless-root-20260907.json`. It covered every
phase listed above with two authenticated clients on the fresh revision-2
fixture, including ordinary dog combat and natural respawn. A deliberately
crossed target also proves the root-enabled public heading remains equal to its
captured action heading after the hit; the old target-facing bearing differed by
pi.
Open-terrain endpoint errors were 0.97--11.44 micrometres. The direct
step-2/step-3 receipts were 558,770/572,670 microseconds after their action
starts, and the equipment cancellation receipts were accepted at
184,369/184,465 microseconds, before the 192,308-microsecond captured first hit.
The frozen revision-2 harness, report, server build and publication are bound by
`.local/p2-rootmotion/revision2/root-headless-acceptance.json`. The initial
88-check result remains preserved under `.local/p2-rootmotion/` as superseded
historical evidence.

Current isolated checks also pass 67 training gameplay tests and 72 all-feature
gameplay tests, plus five build-boundary and one generated-definition test in
each configuration. All-target/all-feature clippy, the complete configured
lint, 148 Python tool tests, GDScript parsing and the runner's pre-registration
checks pass. Revision-2 build and fresh local publication evidence is recorded
in `.local/p2-rootmotion/revision2/build-manifest-root.json` and
`.local/p2-rootmotion/revision2/publication-root.json`. The reviewed revision-2
test-probe package audit in
`.local/p2-rootmotion/revision2/exports-root-reviewed.json` covers 832 Web paths,
1,635 Linux paths, 226 UI images, three actors, 40 clips, 20 Web world sections
and both 11-frame target effects.

Run the composed exported-client check with a fresh output directory:

```sh
.local/venv-dev/bin/python tools/test_browser_accounts.py \
  --url http://127.0.0.1:8186 \
  --database <fresh-protocol-8-yongan-database> \
  --native <matching-test-probe-linux-export> \
  --output .local/p2-rootmotion/browser-rootmotion-fresh \
  --actors --hardware --headless --inventory --panels \
  --progression --targeting --combo --session-refresh
```

The accepted instrumented Web/Linux run passed 297 checks in
`.local/p2-rootmotion/revision2/browser-root-lifecycle-20260907/report.json`.
On both clients it observed the exact `100 -> 65 -> 30 -> 0` health sequence,
three public and rendered actions, same-target renewal before both transitions,
constant per-action heading and terminal endpoint error no greater than
0.452 mm. Web queue receipts were 271,275/237,314 microseconds and native queue
receipts were 310,395/196,039 microseconds after their source action starts;
the respective transitions were 572,074/544,167 and 543,862/549,354
microseconds. Held/released WASD, ground click and target clear each canceled
the future link while preserving the current hit and root. Disconnect/reconnect
added no movement, both clients agreed on the Yongan wall's clipped
0.92199707 m travel, and both real four-minute refresh timers passed.

The matching exact-manifest actor and target regressions pass 77 and 51 checks,
the focused client component report passes 66, and the Python tooling suite
passes 148. Root's acceptance record at
`.local/p2-rootmotion/root-acceptance-review.json` binds those results, the
91-check headless run, the 67/72 Rust gameplay suites, the five build-boundary
tests, the generated-definition test and the audited probe packages.

This qualifies the bounded local instrumented protocol-8 Slice C path. Public
Slice C gameplay/deployment, normal exports without the fixed-input probe,
Windows execution, current Godot MCP inspection, exact Granny within-cycle and
100 ms transition-blend parity, terminal combo step 4, skills, full P2 and the
full game remain unqualified.

## Protocol 9 terminal finisher, area hit and Wild Dog reaction

Slice D extends the common type-0 Sword chain through terminal `combo_4`.
`perform_attack()` remains argument-free. The server classifies the fourth
receipt against the generated `combo_3` window, advances the accepted action's
root position, creates the fixed area at its canonical action-relative boundary
and owns all damage, reaction and knockback movement. The client supplies no
event time, victim list, displacement or action identifier.

Run the server checks in an isolated target directory. An empty fixture selects
the normal build; the reviewed finisher selector is training-only and cannot be
combined with Yongan.

```sh
MT2_COMBAT_TEST_FIXTURE= \
CARGO_TARGET_DIR="$PWD/.local/p2-finisher/server-target" \
cargo test --manifest-path server/Cargo.toml --all-features

MT2_COMBAT_TEST_FIXTURE=triple-wild-dog-finisher-v1 \
CARGO_TARGET_DIR="$PWD/.local/p2-finisher/server-target" \
cargo test --manifest-path server/Cargo.toml

MT2_COMBAT_TEST_FIXTURE= \
CARGO_TARGET_DIR="$PWD/.local/p2-finisher/server-target" \
cargo clippy --manifest-path server/Cargo.toml \
  --all-targets --all-features -- -D warnings
```

After root publishes a fresh default-deny protocol-9 training database with the
matching generated bindings, run the focused two-account smoke once:

```sh
python3 tools/test_finishers.py \
  --server http://127.0.0.1:8186 \
  --game-server http://127.0.0.1:13223 \
  --database <fresh-protocol-9-finisher-training-database> \
  --report .local/p2-finisher/finisher-report-fresh.json
```

The runner checks the live schema and parses the generated bindings, accepted
combo/root scripts, positive finisher script and composed lifecycle script
before registering its only two accounts. Its ordinary setup retains a
source-timed attack lock for selected dog A while keeping dog B healthy and
within 0.5 m, makes `combo_1` miss, then
proves `combo_2` and `combo_3` reduce A from `100 -> 65 -> 30`. The terminal
area must defeat A, damage B exactly once, leave dog C unchanged, preserve its
captured event through target clear and sword unequip, continue the current
player root, and publish the second dog's front knockdown, front standup and
collision-free 4.732 m server displacement. It uses the build-time
`triple-wild-dog-finisher-v1` fixture at
`server/fixtures/p2-finisher-triple-wild-dog.v1.json`; it does not reset a
database or use an administrative reducer.

Current checks pass 81 training-fixture gameplay tests, 86
all-feature/Yongan gameplay tests, six build-boundary tests and one
generated-definition test. All-target clippy passes with warnings denied in
both configurations, and the new Python and GDScript sources pass Ruff,
`py_compile`, gdformat/gdlint and the real Godot parser. The ordinary-training
protocol-9 regression passes 95 checks in
`.local/p2-finisher/integration-r4/headless-four-step-root.json`. The focused
three-dog path passes 61 checks in
`.local/p2-finisher/integration-r4/headless-terminal-clock-root.json`, with
exact A/B/C terminal health `0/65/100`, 4.731999874 m force travel and a
1.43-micrometre fourth-root endpoint error. The current same-account lifecycle
extension still needs an actual run. The first exported browser attempt reached
25 setup checks and then stopped on its original inventory-tooltip precondition,
before combat; its browser error list was empty. That diagnostic is preserved
at `.local/p2-finisher/integration-r4/browser-finisher-root/report.json`.
Exported Web/Linux finisher gameplay, normal exports, Windows, public gameplay
and Godot MCP inspection remain pending.

## Bounded P2 progression administration

Protocol 5 introduced three typed private command requests, retained by protocol
6: `/help`, `/xp <amount>`,
and `/level <target>`. The client maps those spellings to dedicated reducers;
they are not a general command interpreter. `/help` requires a valid account and
controlling connection. XP and level changes additionally require the fixed
server-side `progression_admin` capability and an actively controlled selected
character. Missing bootstrap configuration is intentionally default-deny.

Bootstrap authorization is an exact account `Identity`, never a username,
character name, email, token claim, or UI flag. The compile-time variable is a
comma-separated list of canonical lowercase 64-hex identities. The build rejects
malformed entries without printing their values. Preserve the variable on the
actual module build invocation; setting it only for a later publish command does
not change the compiled authorization list. For an isolated local P2 artifact:

```sh
MT2_AUTH_ISSUER=http://127.0.0.1:8186/auth \
MT2_PROGRESSION_BOOTSTRAP_IDENTITIES='<exact-64-hex-account-identity>' \
CARGO_TARGET_DIR="$PWD/.local/p2/server-target" \
cargo build --manifest-path server/Cargo.toml --locked --no-default-features \
  --target wasm32-unknown-unknown --release
```

Use a fresh `mt2-p2-*` database for this schema and preserve any existing P1
database. The local two-phase runner first proves default deny and records two
fresh QA accounts in an owner-only fixture. After rebuilding and republishing
the same disposable database with the reported first identity as bootstrap, it
verifies permission, replay, validation, provisioning, revocation, reconnect,
feedback privacy, and public-chat rejection:

```sh
python3 tools/test_progression_admin.py prepare \
  --server http://127.0.0.1:8186 --game-server http://127.0.0.1:13223 \
  --database mt2-p2-progression-20260906 \
  --fixture .local/p2/admin-smoke-fixture.json \
  --report .local/p2/admin-default-deny-report.json

python3 tools/test_progression_admin.py verify \
  --server http://127.0.0.1:8186 --game-server http://127.0.0.1:13223 \
  --database mt2-p2-progression-20260906 \
  --fixture .local/p2/admin-smoke-fixture.json \
  --report .local/p2/admin-bootstrap-report.json
```

Provisioning uses the unshipped structured operator CLI. It prompts for the
bootstrap account username, password, and audit reason, or reads credentials
from an owner-only JSON file and the reason from a separate owner-only text file.
Passwords, account sessions, and game JWTs are never command-line arguments or
report fields. The target remains an exact existing account identity:

```sh
chmod 600 .local/p2/operator-credentials.json .local/p2/operator-reason.txt
python3 tools/progression_operator.py grant <exact-target-account-identity> \
  --server http://127.0.0.1:8186 --game-server http://127.0.0.1:13223 \
  --database mt2-p2-progression-20260906 \
  --credential-file .local/p2/operator-credentials.json \
  --reason-file .local/p2/operator-reason.txt
```

The current public endpoint remains on the P1 database and has not received this
schema or any progression operator. No public user account is provisioned until
its authenticated account identity is explicitly selected.

The local default-deny checkpoint on `mt2-p2-progression-20260906` passed 15
two-account checks in `.local/p2/admin-default-deny-report.json`, including
identity separation, private permission feedback, unchanged progression/items,
and absence from public chat. The structured CLI also returned the expected
bootstrap-required denial and wrote a fresh owner-only `applied: false` report.
The bootstrap-enabled artifact is prepared separately but has not been published;
the authenticated permission/replay/provision/revoke phase remains pending the
explicit privilege approval. These local facts do not qualify the public P1
endpoint or provision a public account.

## World populations and offline dev mode

Use [world-content authoring](world-content.md) for validated map populations,
add/move/remove drafts and the isolated Godot inspector. `make world-validate`
checks the default Yongan profile; `make world-preview` opens a separate offline
project. Set `WORLD_PROFILE`, `WORLD_OUTPUT` and optional
`WORLD_FLAGS='--npc <converted-NPC-directory>'` as needed. The default output
includes a timestamp; an explicitly supplied directory must be new.

Quests are deferred. Yongan's current population contains six Wild Dogs; the
original guard can be installed with
`make npc-install NPC_CONTENT=<converted-directory>`.
`make test-npcs GODOT=/path/to/godot`
checks the real Main scene, map chunk reload and NPC lifecycle in an isolated
native project with an explicit offline connection spy. Changed populations require fresh
development databases until an explicit migration tool is implemented. These
tools do not grant live admin privileges or modify an existing database.

The NPC compiler accepts repeated `--content` and `--population` arguments for
additional converted definitions/maps. See the world-content guide for output,
backup and resource-validation behavior. Normal exports validate this public
catalog and its GLB/texture derivatives, and inspect the actual packaged NPC
skins, materials and idle clips. They also check the public item catalog against
the trusted server item definitions; source metadata remains excluded.

The current local proxy at `http://127.0.0.1:8186` serves the qualified NPC Web
test build against `mt2-p2-npc-interaction-r1-20260907`, preserving the previous
databases and game/auth processes. The corresponding browser/Linux run passes
103 checks. Use `tools/test_browser_accounts.py --world-npcs
tests/fixtures/yongan-city-guard-route.json` with matched test exports; the full
command and scenario limits are in the world-content guide. The public deployment
has not changed.

### NPC interaction authoring and QA

After `make npc-install`, edit `content/worlds/yongan.interactions.json` to link
an existing stable spawn ID to the shared `dialogue` handler and plain text.
The server build reads the installed catalog as a trusted offline input and
advertises its SHA-256. Keep the client and server built from the same catalog.
There are no scripts or rewards in the interaction profile. Adding another
NPC with the same handler requires content records, not a new UI/reducer.

The build script emits content errors into the generated game definitions.
Consequently a missing NPC catalog blocks the game module, while the standalone
terrain inspector can still compile to help create the first catalog. This is
not a server fallback or a fixture that may be published without its assets.

For the protocol-13 interaction slice, publish to a new local database, regenerate
bindings, and run the ordinary-account scenario (the game route can differ from
the auth origin):

```sh
python3 tools/test_physical_combat.py --scenario npcs \
  --server http://127.0.0.1:8186 --game-server http://127.0.0.1:13223 \
  --database mt2-p2-npc-interaction-r1-20260907 --godot /path/to/godot \
  --report .local/npc-interactions/network.json
```

This checks raw private subscriptions, invalid/remote requests, duplicate opens,
foreign/stale session closes, movement/attack cleanup, real 60-second expiry,
leave and reconnect. Export both clients and use the existing `--world-npcs`
browser scenario for actual picking, approach, panel input, Escape and WASD.
Godot MCP is unavailable in the current session; isolated CLI renders and actual
exports provide runtime evidence while preserving the open editor.

## Working with the editor

When available, prefer the configured `godot` MCP tools for live changes. Confirm
`get_project_info` points to this checkout, inspect the edited scene, start the
game, inspect its runtime tree, capture the rendered game, and exercise the input
you changed. Without MCP, use isolated Godot CLI fixtures, rendered exports or the
existing Playwright checks as appropriate. Preserve unrelated open scenes and
unsaved work, and record missing editor evidence rather than claiming it. See
[Godot MCP setup](godot-mcp.md) for installation and troubleshooting.

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

## P1 generated actor fixture

The `p0-warrior-dog` profile compiles a selected male Warrior, starter Sword+0
vnum 10 and Wild Dog 101 into client presentation data and matching server
trusted action definitions. It also selects the original male Warrior
HairIndex 0 model and target skin declared by `warrior_m.msm`. The hair is
linked to the main skeleton only after its positive vertex weights are checked
against the compatible head binding. Run:

```sh
make content-build BLENDER=/path/to/blender
make content-validate
make content-probe
make test-actors
```

The build may retrieve declared pinned inputs on a cold cache; the compiler also
has `--offline` after those inputs are available. Validation compares generated
GLB hashes and structural records with the presentation manifest and checks the
shared gameplay-definition hash against
`server/content/p0-warrior-dog/actions.v1.json`. The probe uses an isolated
Godot project. `test-actors` stages actor resources in a separate project; add
`UI_FLAGS=--native` for rendered captures when Xvfb is available. See
[P1 actor content import](content-import.md) for generated paths, package
exclusions and current evidence limits.

The isolated combined conversion and entry-preview evidence is recorded in
`.local/p2-hair/verification.json`. It includes the pinned hair source hashes,
the exact skinning audit, generated payload hashes and the actual before/after
captures. The same profile declares Sword+0's +90-degree X attachment rotation:
the converted mesh's +Y blade axis then follows `equip_right_hand` +Z in the
pinned combo attack samples. Exact proprietary Granny within-cycle deformation
and blend parity remain unverified; use the native actor capture suite when
changing either attachment. The installed combined manifest passes the
28-check native entry flow in
`.local/p2-finisher/intro-camera-facing/report.json`; its create-screen capture
shows the original hair and the Warrior facing the fixed preview camera.

Open `client/scenes/character_preview.tscn` for the offline presentation
inspector. Its motion selector and Unarmed/Sword+0 toggle read the loaded actor
manifest; pause and timeline scrub affect only that local preview. Right-drag
and scroll preserve the orbit camera controls. It has no server or account
connection.

Current exports require the generated P1 profile; they fail before staging with
the content-build guidance when its manifest is absent. For isolated P1 export
QA, `tools/export_playable.py` accepts `--output-dir` and `--work-dir`; use
separate `.local/p1/` paths so normal `dist/` artifacts are not replaced. The
actual PCK audit retains a legacy branch only for inspecting already-created
legacy packs, never as a fallback for a current export.

Use `make import-ui` after `make dev-setup` for the selected original HUD,
inventory, item icons and stitched Yongan minimap. This converts 224 UI images
and 20 original DDS map tiles into 225 outputs from 293 pinned source files with
Pillow; Blender
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
make test-ui UI_FLAGS="--suite status --native --output .local/classic-status"
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
  --url http://127.0.0.1:8186 --database mt2-p1-final \
  --output .local/p1/browser-source-row-rerun \
  --actors --hardware --headless --inventory --panels --session-refresh
```

The runner uses visible browser controls for registration/login and character
entry, plus an independent exported Linux account. It covers ownership,
creation/selection, leave/switch, movement, reconnect/refresh, logout and wrong
password handling; optional flags add original HUD/panel interactions. It
writes private reports/screenshots under `.local/browser-accounts/<timestamp>/`.
Use `--hardware --headless` for an isolated hidden Chrome run with
`--enable-gpu`; its report records the actual WebGL renderer and avoids desktop
mouse/keyboard input contaminating timing-sensitive checks. `--hardware` by
itself deliberately keeps Chrome visible for desktop observation. Add
`--actors` to exercise only the selected P1 Warrior, Sword+0 vnum 10 and Wild
Dog 101 fixture checks; it is not broad actor/content coverage. These modes
produce scoped evidence and do not by themselves establish a final acceptance
pass.
`--progression` exercises the protocol-5 owner rows through two authenticated
exports, opens Status with real `C` input, checks the taskbar projection, proves
focused slash typing cannot move the character, and routes unknown, `/help`,
and default-denied `/xp` text without putting it in public chat. It expects a
default-deny database; operator success remains separate audited server QA.

```sh
.local/venv-dev/bin/python tools/test_browser_accounts.py \
  --url http://127.0.0.1:8186 --database mt2-p2-progression-20260906 \
  --output .local/p2/browser-progression --hardware --headless --progression
```

Add `--progression-combat` together with `--progression` to kill five normally
respawning Wild Dogs through ordinary exported-client movement/attack inputs,
prove exact +15 XP per life and the first +2 small-potion quarter reward without
pickups, then click the Status VIT plus and verify VIT/max-HP changes without
healing current HP. The mode also checks private progression ownership from both
clients; it is rejected unless `--progression` is present. Combine it with
`--session-refresh` for persistence through both real timers:

```sh
.local/venv-dev/bin/python tools/test_browser_accounts.py \
  --url http://127.0.0.1:8186 --database <isolated-protocol-5-database> \
  --native <matching-test-probe-linux-export> \
  --output .local/p2/browser-positive-progression \
  --actors --hardware --headless --inventory --panels \
  --progression --progression-combat --session-refresh
```

The accepted actual run passes 199 checks in
`.local/p2/browser-positive-progression-fresh-read/report.json`. It recovered
two transient partial native report reads in 11 ms each, had no unavailable
snapshot, and recorded clean browser and native engine results.

For protocol 6 target presentation, run the normal one-Wild-Dog Yongan module
and its matching instrumented Web/Linux exports. `--targeting` runs after both
accounts enter the world and before the runner's generic movement and reconnect
checks. Inventory runs first when requested because its full-health potion
rejection is a precondition; the actor presentation check runs afterward.

```sh
.local/venv-dev/bin/python tools/test_browser_accounts.py \
  --url http://127.0.0.1:8186 \
  --database '<isolated-protocol-6-Yongan-database>' \
  --native '<matching-protocol-6-test-probe-linux-export>' \
  --output .local/p2-target/browser-targeting \
  --actors --hardware --headless --inventory --panels \
  --progression --session-refresh --targeting
```

The reviewed protocol-6 instrumented packages check 832 Web paths and 1,635
Linux paths, including exact decoded RGBA for all 226 UI images, three actor
models, all 40 declared actor clips and all 20 Web world sections. Both packages
also contain the two source-derived target-effect models with all 11 frames and
the four declared textures matching the four engine-derived texture resources.
The report is `.local/p2-target/exports-root-reviewed.json`. The second probe
exports preserve those audits; a 175-file source-freeze comparison finds only
the expected `export_probe.gd` change between the instrumented builds. Normal
exports exclude that test probe. Their Web PCK SHA-256 is
`a727af24fd4a6ba91a3c3973a5567968590a504ee48cc7bedf0d5e767d8dcf80`
and Linux is
`547791d7892d59b7b4dd24430d3849293fcb0cca3f9b9952ab069e1a581761ab`.
The full configured lint suite and 139 Python tool tests pass for this package
checkpoint. Package and static-tool results are separate from the exported
gameplay evidence below.

The Web half uses actual canvas pointer movement and clicks for hover, target
selection, the target-board close control and a ray-verified ground point, plus
ordinary `W` input. The Linux half uses only fixed test-probe `InputEvent`
routes for pointer motion, left click and Space. Movement setup uses the existing
validated move-to/stop actions. The probe has no script evaluator or direct
target reducer action. The mode verifies the authoritative level/name/health
board, owner-only target row, separate hover/target effects, selection retained
through ground and WASD movement, rejection correction, selected-target damage
as observed by the peer, natural death/respawn cleanup, character leave and
`AccountFlow` reconnect. If a retained run left the dog damaged, setup finishes
that life with ordinary Space attacks and waits for the production respawn,
recording restoration separately from the one tested kill.

Native pointer injection first validates a finite in-viewport point, moves the
native test window's cursor there, then routes the fixed motion/button event.
This cursor move exists only in instrumented exports through a test probe that
normal exports exclude, so the production client's periodic pointer poll sees
the same position as its input handler. An
isolated focused Xvfb/Godot 4.7.2 check showed that both `Viewport.push_input()`
and `Input.parse_input_event()` delivered an event without changing the native
cursor position, while `Viewport.warp_mouse()` updated both display and viewport
positions. The no-network evidence is retained in
`.local/p2-target/probe-pointer-semantics-20260907.log`.

`--targeting` is rejected with `--progression-combat`; the latter owns a separate
five-life progression precondition. The normal fixture does not repeat the
dual-target no-fallback proof from the accepted 53-check server run.

The accepted protocol-6 exported run passes 174 checks in
`.local/p2-target/browser-root-final-20260907/report.json`. Its one ordinary
unarmed kill advances the Wild Dog from life 2 to 3 through four exact 25-damage
hits and observes the production respawn after 11.946 seconds against the
server's 12-second schedule. It also covers the complete target flow above,
actor/inventory/panel composition, mutual movement, reducer rejection,
character switching, reconnect, page reload, logout/login and both real
four-minute refresh timers. The 53-row refresh trace contains 51 valid positions
per client with zero maximum authoritative drift; two transient unavailable
position rows per client occur during the exercised lifecycle transitions.
Three partial native JSON reads recovered within 52 ms with no unavailable
snapshot; the report's 72 ms maximum includes first-attempt file I/O. Browser
and native engine error lists are empty.

An earlier retained 85-check diagnostic run clicked a momentarily valid respawn
projection while the rendered dog was still 1.82 m behind its authoritative
position. The independent cursor record in
`.local/p2-target/browser-root-settled-20260907/root-pointer-review.json` showed
that the actual OS cursor
matched the requested viewport point plus the 112-pixel window offset, then the
projection moved by more than 100 pixels on the next refresh. The runner now
requires a ray-verified point to remain within one pixel for at least 0.5 seconds
and checks both rendered actors against their authoritative positions before
each lifecycle click. It sends one pointer event after the gate succeeds.

The native pointer and Space route is confined to the fixed instrumented test
probe, which normal exports exclude; the Web path uses real canvas input. Godot
MCP was unavailable for this
checkpoint, so the evidence comes from the actual instrumented Web/Linux exports
and the isolated native checks. This run is one-kill target evidence. The
protocol-5 five-kill progression result remains the separate 199-check report
above. Neither result establishes public protocol-6 deployment, native Windows
execution, or an original-client side-by-side pixel comparison.

Account registration is rate-limited. Honor the auth response's retry interval
and do not infer readiness only from a count of recent registrations; the
observed limiter required 300 seconds without an allowed signup after its last
accepted request updated the window timestamp.

The root acceptance record
`.local/p2-target/root-acceptance-review.json` binds the 175 unchanged client
sources, 17 server source hashes, three module artifacts and both accepted PCKs.

Add `--session-refresh` to wait for both clients' real four-minute refresh
timers and verify that they reconnect into the same world state; this is a
longer test, not an accelerated timer simulation. The latest local P1 run uses
the command shape above and passes 111 checks in
`.local/p1/browser-source-row-final/report.json`. It covers the selected
Warrior/Sword+0/Wild Dog actors, entry, inventory/panels, system-menu
interactions, combat, movement, switching, reconnect, page reload, logout,
wrong-password retry and both real timer renewals. It used AMD hardware through
headless Chrome and an independent exported Linux client, retained both self and
peer actors after renewal, and recorded no browser engine errors.

The idle-renewal diagnostics distinguish input and state sources. A prior
visible run recorded contaminating DOM mouse/WASD events. A later transient
`[0,0,0]` convenience snapshot came from deferred local-actor reconciliation,
while the matching subscribed online player row remained valid. The runner now
uses that own-identity row for its authoritative baseline and drift, and still
requires final self/peer rendering in both clients. The accepted report's
post-hoc 55-sample XYZ audit records zero drift and zero DOM events in
`.local/p1/browser-source-row-final/xyz-drift-audit.json`.

The earlier account-flow exports passed 103 checks in
`.local/browser-accounts/20260906-193823/report.json` on loopback and
`.local/browser-accounts/20260906-194508/report.json` on the public account
database. That public evidence belongs to release `20260906T173802450337Z` and
is separate from local P1 acceptance. The P1 development build is now live as
release `20260906T204513591109Z` on `mt2-p1-v4`; publication verified HTTPS,
database availability and the served manifest without deleting data; the HTTP
record is `.local/p1/public-http-report.json`. Public exported-gameplay
qualification is still pending. The 19-check native UI suite separately verifies
menu centering/resizing/clicks.

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

Current native probes write a complete temporary snapshot and atomically rename
it over the published report. Readers retain bounded retries for startup and
older exports, and must report unavailable snapshots instead of substituting an
empty world. Screen-wave checks distinguish received event state from samples
actually applied to the camera. Keep Yongan minimap/atlas checks separate from
the flat finisher fixture, which has no original-map metadata.

Use the [content verification matrix](rebuild/content-authoring.md#authoring-tools-and-verification-scope)
to select checks for future content changes. Visual-only additions use import
validation and previews; shared gameplay and release changes need the relevant
multiplayer/export evidence. Account and token-refresh tests are not prerequisites
for every content edit.

For the original small training-ground proof, build/publish with
`SERVER_FEATURES=` and export with `INCLUDE_MAP=` to omit Yongan. Keep its database
and reports distinct from Yongan evidence. Exporting Linux or Web with
`--test-probe` adds only the explicit local test interface; normal exports remove
all `client/tests/` sources and MCP bridges.

## Attack-speed qualification

The local protocol-15 build at `http://127.0.0.1:8186` uses
`mt2-p2-attack-speed-r1-20260908`. Previous databases are retained; this is a new
schema, not an in-place data reset. Rebuild the selected content with the normal
`content_compile.py build --offline --blender ...` command before compiling this
server. Publish to a fresh database, regenerate bindings from it, and export
matching clients. The gameplay hash includes item attack-speed applies.

The focused `tools/test_physical_combat.py --scenario classes --class-id 3` run
on separate `mt2-p2-attack-speed-qa-r1-20260908` passes 144 checks. It includes both
Shaman appearances, scaled unarmed/fan durations, queued/direct combos, ordinary
mob force/recovery, private speed projections, active-swing unequip capture,
movement and disconnect/reconnect. Its runner stages the shared timing helper
and parses all scripts before creating accounts. Use a fresh test database and
ordinary accounts; respect the existing signup rate limit.

`tools/test_actors.py --native --scenario fan` passes 87 rendered checks, including
1.26 playback, late-subscription seeking, held-input boundaries and idle reset.
`tools/test_target_client.py --suite content_gate` includes exact scaled camera
activation, deduplication, per-appearance routing and unchanged 200 ms duration.
The `--physical_ui` component tests the status value and original item bonus text.
The exported `tools/test_browser_accounts.py --classes --warrior-effects` scenario
passes 106 checks with actual held Space and both clients presenting 1.22 sword
playback; it also covers the Warrior camera event and account lifecycle.
Artifacts and detailed outcomes live under `.local/p4-attack-speed/`; see the
[implementation ledger](rebuild/implementation-status.md) for final acceptance.
Connected Godot editor/MCP inspection is unavailable in this session. Isolated
native and exported-client evidence does not establish editor or Windows behavior.

## Focused physical-damage qualification

For the protocol-10 physical-damage slice, run the focused test against a fresh
training database with matching generated bindings. When the auth proxy and
game database use separate local routes:

```sh
python3 tools/test_physical_combat.py \
  --server http://127.0.0.1:8186 --game-server http://127.0.0.1:13223 \
  --database mt2-p2-physical-training-r1-20260907 --godot /path/to/godot \
  --report .local/p2-physical/combat-report.json
```

With a shared auth/game origin, use `make test-physical SERVER_URL=... DB=...`.
This runner checks the actual schema and parses its isolated Godot project before
creating accounts. It uses two ordinary authenticated identities, retains
redacted evidence and logs out its fixture sessions. The focused scenario covers
initial physical damage, owner-private display values, equipment capture,
movement, a kill/respawn and reconnect/switching. The older combo/finisher browser
scenarios still encode their protocol-9 fixed-damage expectations; their recorded
passes are historical until adapted for the variable physical formula.

The content verification matrix applies: this focused test does not rerun the
four-minute auth-refresh scenario because the authentication implementation is
unchanged. Select `--scenario finisher` with the separate three-dog database to
check variable per-victim area damage and captured equipment through force and
standup. Select `--scenario growth` with the one-dog training database to earn
twenty kills in four sessions with refreshed credentials, then check level-two
display values and STR/VIT/DEX allocations. The observer finishes an injured
monster left by a previous failed run through ordinary combat, preserving zero
starting XP for the measured character. No database reset or privileged XP grant
is used. Reports include frozen staged-source hashes and respawn clock timings.

Select `--scenario lifecycle` with a fresh separate three-dog finisher database
to disconnect before the fourth attack's area activates. The observer checks
presence removal before activation and unchanged monster health/lives; reconnect
checks that neither the cancelled attack nor its root motion is replayed.

For the item-recovery slice, use `--scenario recovery` against a fresh local
training database built with `MT2_ITEM_TEST_FIXTURE=recovery` and a loopback
`MT2_AUTH_ISSUER`. That bounded test fixture adds two medium potions to the
otherwise unchanged starter loadout and advertises `training-item-recovery-v1`
as its map content identity. The build rejects unknown item fixtures, Yongan,
non-loopback issuers and simultaneous combat fixtures. It enables neither guest
access nor privileged commands. Preserve existing databases and do not deploy
this fixture publicly. Normal builds omit `MT2_ITEM_TEST_FIXTURE`.

The recovery scenario earns its health deficit through ordinary dog attacks,
then checks small/medium recovery timing, capped totals, exact item consumption,
full/pending/foreign/unsupported rejections, mutual movement and reconnect without
replaying recovery. Its source/schema preflight runs before account creation.
Current application protocol is 15 with trusted content schema 8 and item registry 2; the SpacetimeDB
schema HTTP endpoint's `version=10` parameter is a separate wire/API version.

For item integrity, select `--scenario security` against a fresh protocol-12
training database with matching bindings (the recovery fixture is supported).
It checks forged/foreign/inactive-character item intents, exact revision replay,
consumption and ID persistence through reconnect, ordinary kill/drop production,
competing pickups, quantity conservation and private audit query rejection. It
uses ordinary authenticated accounts and normal combat, without granting privileges.
The raw scenario helpers append the subscribed item revision unless a test
explicitly supplies a stale/forged value. No automatic retry changes the tested intent.

The offline operator checker accepts a consistent JSON snapshot with `inventory`,
`drops` and `audit` arrays; order `audit` by ascending `id` and include its complete
history from creation. Use the exact trusted definitions for that database:

```sh
python3 tools/audit_items.py .local/private-item-snapshot.json \
  --definitions server/content/p0-warrior-dog/actions.v1.json \
  --report .local/item-integrity-report.json
python3 tools/test_target_client.py --godot /path/to/godot \
  --suite item_intent --output .local/item-intent-check
python3 tools/test_target_client.py --godot /path/to/godot \
  --suite physical_ui --native --output .local/item-tooltip-check
```

The first command is offline reconciliation, not an export mechanism. An
operator snapshot-export route and archive/retention workflow are still pending;
do not weaken the account gate or expose private tables to obtain snapshots.
`--native` uses an isolated Xvfb render and currently supports only the single
`physical_ui` suite. It saves `physical-ui-component.png`; it does not inspect the
user's open Godot editor or qualify an exported client.

For the matching Web/Linux test exports, use
`tools/test_browser_accounts.py --physical --url <origin> --database <database>
--native <exported-Linux-binary> --chrome <browser> --hardware`. This focused
Training UI scenario checks Attack/Defense, Sword+0 tooltips and equip/unequip
through actual Web/native input, plus the standard account lifecycle. Omit other
feature flags. Review its captures and engine logs as well as interaction checks.
It does not replace the headless variable-damage scenarios.

Godot 4.7.2 release exports have a reproduced embedded-tooltip issue matching
[Godot issue 89657](https://github.com/godotengine/godot/issues/89657): removing
a standard tooltip can log nonexistent `focus_entered`/`tree_exited` signal
disconnects. The minimal local reproduction and external-popup comparison are
under `.local/p2-physical/popup-repro/`. The game remains on the pinned engine
and embedded UI; the exported QA error gate remains enabled. Record any affected
run as functionally exercised with a failed clean-engine-log gate.

## Deploying an update

The current public release is `20260908T121524155504Z`, database
`mt2-public-progress-v19-20260908` (protocol 19). Its matching Web/Linux test-probe
exports passed 114 actual public checks; see [distribution](distribution.md).
Build with `MT2_AUTH_ISSUER=https://kcanakdag.com:8443/auth MT2_ALLOW_GUESTS=0`
and `--features yongan`, export for that same database and origin, then deploy
with the matching `DB`/`WEB_DIR`. Use a new database for incompatible schema
changes; preserve existing databases. This changes only
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

The P1 development rollout creates a new public database while preserving the
preceding account and guest databases. With matching instrumented exports
targeting `mt2-p1-v4`:

```sh
make deploy DB=mt2-p1-v4 WEB_DIR=dist/web-test DEPLOY_FLAGS='--allow-test-build'
```

This invocation does not reset a database or remove a volume. The old
`mt2-yongan-v2` and `mt2-accounts-v3` databases remain stored, and the proxy
exposes only `mt2-p1-v4`. Auth accounts, signing material and SpacetimeDB issuer
keys persist. The public P1 development deployment completed as release
`20260906T204513591109Z`, with verified HTTPS health/discovery, database
availability and served manifest. Its exported browser/Linux gameplay
qualification remains pending. The preceding account release's public run
passed 103 checks, including real timed refresh. Local apply-script command
fixtures cover failure recovery and optional reset scope; they are not a real
Docker restore drill.

After deployment, verify HTTPS and two actual accounts in browser/native
clients. Health checks and successful container startup do not establish
private subscriptions or gameplay. Normal exports omit probes; the development
test build is explicitly authorized. See [distribution](distribution.md) for
prerequisites, phase status, failure behavior and recorded evidence.

Implementation guidance for agents lives in [AGENTS.md](../AGENTS.md). Update
these notes when the tested workflow changes.

## Skill definitions and progression

Protocol 16 adds owner-private learned skills and a shared catalog hash. See
[the skill contract and build/test workflow](skills.md) for level-5 learning,
validated casting, developer commands, selected source policy and current limits.

## Authored practice target

Run `make dummy-build BLENDER=/path/to/blender` before exporting protocol-17 clients.
See [training-dummy.md](training-dummy.md) for configurable stats/placements,
background Blender generation, multiplayer fixtures and content-hash matching.
The exported browser scenario adds `--training-dummy` to
`tools/test_browser_accounts.py` and checks actual pointer/Space input against
the normal authored target. The qualified dummy build is served locally on
`mt2-p2-dummy-dev-r1-20260908`; previous databases and exports remain preserved.
## NPC area placement qualification

After converting `content/profiles/yongan-area-npcs.json`, run
`python3 tools/test_npc_placements.py --content <conversion-directory> --seeds 100 --output <new-report-directory>`.
The tool compiles the pinned offline Rust example and samples against the actual
Yongan terrain. Outputs are explicitly preview data, not authoritative database
rows. The report includes code, terrain and binary hashes; changing an input during
qualification fails the run. This does not replace multiplayer placement,
reconnect or disconnect tests when runtime subscriptions are implemented.

## Allocated mob combat fixture

Build a training module using `MT2_COMBAT_TEST_FIXTURE=allocated-wild-dog-v1`
and the intended local auth issuer/guest policy, without `--features yongan`.
Freeze and publish it to a fresh `mt2-p2-` database, then run
`tools/test_physical_combat.py --scenario melee` against that database, using the
same auth/game-server options as the passive replay above. This exercises the
normal two-client combat scenario against a database-allocated dog ID (900002).
Do not deploy this training fixture to the public map. Protocol 22 is required.
The fixture tests allocation and existing respawn, not original regeneration.

## Two-member regeneration replay

Build with `MT2_COMBAT_TEST_FIXTURE=regenerating-wild-dog-v1` and the local auth
issuer/guest policy, without Yongan. Freeze and publish to a fresh `mt2-p2-`
database, then run `tools/test_physical_combat.py --scenario regeneration` with
the same auth/game-server options as the other combat replays. Protocol 23 is
required. The scenario uses ordinary sword attacks to kill leader 900002, checks
that follower 900003 survives and replacement members 900004/900005 appear, then
checks stale-target rejection, disconnect and reconnect. Use a fresh database for
each replay because successful runs advance the population. Never deploy this
training fixture over the public map.

The regeneration fixture’s JSON `regeneration` object now supplies `id`,
`interval_us`, `capacity` and `startup_jitter_max_seconds`. Rebuild after editing it;
the generated server definition owns those settings and its member-template slice.
Do not edit generated Rust output. Existing replay expectations target the checked-in
five-second, capacity-one configuration; altered content needs matching QA.

The regeneration fixture now also provides optional `group_area` with integer
`bounds_cm` and an array of equal-weight `groups` (each group lists member vnums,
leader first). Only installed species are accepted. The selected fixture uses
passive dogs and checks initial leader placement inside its area before testing
replacement/reconnect. Template IDs are replaced by fresh allocated IDs. The
current explicit fixture marker is `training-v7-regenerating-area-wild-dog-v1`.

The startup jitter setting is a maximum, sampled once when enabled scheduling
starts. Optional `force_aggressive` is a boolean (default false), applied to all
members of the entry’s groups.

## Select a compiled mob package

Set `MT2_MOB_CONTENT` to the absolute output directory from
`tools/build_mob_catalog.py` when building the server. The build validates its
receipt/artifact hashes and links the selected mob registries. For focused QA,
combine it with `MT2_COMBAT_TEST_FIXTURE=regenerating-wild-dog-v1`, the local auth
issuer and disabled guests, then freeze/publish to a fresh database and run
`--scenario regeneration`. Source HP/rewards now apply; the replay records public
world metadata and initial mobs. This is still a training fixture, not a public
map deployment. The normal rendered client additionally requires the matching
`assets/imported/mobs/presentation.v1.json` and converted assets; without them its
content-hash gate intentionally rejects the selected server. Protocol 24 is required.


## Install converted mobs in the client

After compiling the mob catalog and building the selected projectile package:

```sh
python3 tools/install_mob_content.py --content <converted-mob-directory> \
  --catalog <compiled-mob-catalog-directory> --projectiles <projectile-package-directory> \
  --client client
```

The installer verifies package hashes, shared gameplay identity, referenced flights
and allowlisted converted resources before staging the two destination directories.
Only presentation files are installed under `assets/imported/mobs` and
`assets/imported/projectiles`; no original archives or server registries are copied.
Matching installs can be repeated, including after Godot expands texture import
metadata. Required import settings must still match; changed model/image bytes,
unowned directories and different packages are rejected without overwriting them.
To stage a different package, use a fresh isolated client directory. In-place
package upgrades are not yet supported. A normal client with an installed package
requires a server advertising the same `mob_catalog_hash` (protocol 24).

Focused presentation QA uses `tools/test_world_projectiles.py --godot <godot>
--mobs <converted-mob-directory> --projectiles <projectile-package-directory>
--output <fresh-directory>`. It installs the package into an isolated Main scene,
imports through Godot and exercises four projectile definitions with controlled
rows. This does not establish live networking, browser export or editor behavior.


## Build the original Yongan mob population

Build with `--features yongan`, `MT2_MOB_CONTENT=<absolute-compiled-mob-package>`
and `MT2_ORIGINAL_POPULATION=<absolute-population.v1.json>`. The last input is the
hash-verified original regeneration inventory from the mob population pipeline.
The shared compiler validates its map, lifecycle policy, group references and
species against the selected mob package. Combat fixtures and
`MT2_POPULATION_PROFILE` cannot be combined with this mode. Original regeneration
entries replace authored ordinary mob placements; the practice dummy remains.
The existing terrain and NPC packages must also be present for a Yongan build.

Freeze the module, publish to a fresh `mt2-p2-` database and run
`tools/test_physical_combat.py --scenario original_population --mob-catalog
<compiled-package>/gameplay.v1.json` with the explicit auth/game endpoints,
database, Godot executable and report path. This focused scenario targets the
selected full Yongan inventory (over 2,000 initial mobs); it checks two authenticated
subscriptions, registered unique mob IDs, movement, invalid-target rejection and
reconnect. It does not render actors or exercise combat against every species.
`server/examples/regeneration_compile.rs` uses the same compiler for offline
inspection without installing the emitted registry.


## Exported original-population checks

`tools/export_playable.py` now runs `tools/audit_mob_pack.gd` whenever the staged
client contains a mob manifest. It loads the actual exported mob scenes, skeletons,
meshes and animations, checks the expected gameplay identity, and resolves all
referenced projectile resources through the normal loader. Results are included
under `pack_audit.mobs`. This resource audit does not replace rendered field QA.

Use `tools/test_browser_accounts.py --mob-catalog <compiled>/gameplay.v1.json`
with matching browser/Linux test exports and explicit URL/database/output. This
option targets the full original Yongan fixture: both subscribed populations must
contain over 2,000 unique ordinary mob IDs, every selected species, finite positions,
and the same ID-to-species mapping. The NPC walking route checks its own map, NPC
positions, movement and dialogue; it no longer assumes an unrelated six-dog fixture.
Do not use that population assertion for a deliberately smaller custom map.


## Generate collision-clear developer walking routes

Build `cargo build --manifest-path server/Cargo.toml --locked --offline --features
yongan --example world_route`, then send JSON on stdin to
`server/target/debug/examples/world_route`, for example
`{"start":[660,575],"goal":[788.39,553.6]}`. The offline planner uses the actual
server terrain, player footprint and clear-path function. Its bounded grid search
emits map-hash-bound waypoints with collision-clear segments up to 12 metres.
This is a developer route generator, not gameplay pathfinding or an admin teleport.
It does not account for dynamic players/mobs or guarantee an optimal route.

`tools/test_browser_accounts.py --mob-route tests/fixtures/yongan-hunting-route.json`
walks both actual exported clients to the selected original hunting ground and
back with normal validated movement. It checks common visible animated mob IDs,
captures each exported render and records instrumented FPS samples. Combine with
`--mob-catalog <compiled>/gameplay.v1.json` for full subscription checks. These field
checks replace the old assumption that an authored dog can be rendered from town;
the existing `--actors` fixture still targets its old nearby dog/model package.


For focused rendering/performance iteration, add `--field-only` with `--mob-route`.
The harness registers two clients, enters the world, checks the selected population,
walks to the field, captures and samples it, then stops. It omits the return trip
and unrelated character-switch/login lifecycle checks. Reports explicitly record
`scope: field-only`; native/browser engine failures still fail the run during
cleanup. Field samples include instantiated NPC counts as well as mob counts.
Use the full account scenario at lifecycle changes or broader milestone acceptance.

Add `--profile-probe` to measure a five-second interval at the field destination
without the export probe's periodic full-scene snapshots. The fixed probe action
`profile_performance` pauses snapshot publication, counts process frames using
monotonic microseconds, then resumes publication with `performance_profile`.
Reports preserve both the normal instrumented samples and the snapshot-free
interval. Network subscriptions and gameplay continue; event-history callbacks
remain active, so this is not a completely uninstrumented release benchmark.
Compare results on the same hardware/render backend and record competing load.
The ordinary hidden developer panel no longer constructs full snapshots every
quarter second; opening it restores live diagnostics.

Map NPC presentation uses the same original view-distance policy as mobs when
Main supplies its local player position. Loaded terrain is still required, and
losing the local player removes NPC instances. Catalog previews may omit a viewer
to inspect all loaded placements. Models are still loaded during preparation;
this change reduces scene/animation work, not asset download or initial loading.
Focused native evidence: `.local/npcs/nearby-runtime-r2/report.json` (56 checks),
including leaving/returning, missing local player and guard interaction. The
exported comparison `.local/mobs/debug-cost-field-r1/report.json` passed 42 focused
checks. Field samples were Chrome 18 FPS / Xvfb native 7 FPS with snapshots, then
34.1 / 10.3 mean FPS during the five-second snapshot pause. The reference Metin2
client remained running. These short sequential samples establish probe overhead,
not a controlled release benchmark. Both packaged mob audits passed; reviewed
browser/native captures show textured terrain and original field mobs.

The shared visibility predicate rejects out-of-range rows before querying terrain
readiness. Main resolves the viewer once per pass and allocates actor keys only
for included rows; NPCs avoid a duplicate readiness lookup. The original integer
centimetre distance calculation and loaded-terrain requirement are unchanged.
The focused 2,800-row regression verifies one readiness call when one row is near,
alongside range edges, malformed coordinates, terrain unload and latest-life
re-entry. This is deterministic work-count evidence, not an FPS claim.

Add `--field-combat` with `--mob-route` to exercise combat after reaching the
original population. The current account fixture creates a Warrior; the replay
equips its existing Sword+0 through the inventory UI and verifies the replicated
appearance before combat. It chooses a living, pickable converted mob within six
metres, clicks its actual screen projection, verifies server-confirmed selection
of the exact instance/life, and holds Space until both exports observe damage
and death. Input is released even on failure. Reports retain before/after rows,
pointer coordinates, exact-life health subscription events and a browser capture.
Damage/death checks require events newer than each client’s pre-attack baseline;
corpse removal need not coincide across independently delayed clients. Combine with `--field-only` to omit
unrelated account lifecycle checks; these actions affect the selected development
world normally, without privileged damage or a database reset. This scenario
covers the encountered mob, not every registered species or reward/drop rule.

The held-attack scheduler's focused Godot scenario is
`client/tests/held_attack_smoke.gd`. Run it in an isolated imported client project
with `godot --headless --path <project> --script res://tests/held_attack_smoke.gd`
and isolated XDG data/config directories. It exercises pending acknowledgements,
stale idle observations, release/rejection and reset; it does not replace actual
exported held-Space/combo and reconnect checks.

`client/tests/item_drop_smoke.gd` is a focused rendered scenario for catalog-driven
drop labels/icons. Copy it and the current owned actor/content scripts into an
isolated imported client project, then run
`xvfb-run -a godot --path <project> --script res://tests/item_drop_smoke.gd` with
isolated XDG data/config directories. It writes `user://item-drops.json` and a
capture. The scenario covers multiple definitions, changed/unknown vnums and Yang
labels; it does not establish classic 3D ground-model or multiplayer fidelity.

The [ground-item pipeline](ground-items.md) resolves selected original drop models,
deduplicates them and optionally runs Blender plus an isolated Godot preview.
Its default is the existing Yang/two-potion fixture; it does not install gameplay
assets automatically.

Selected ground models can now be installed with `tools/install_ground_items.py`;
see the [installation and runtime checks](ground-items.md#install-and-render-the-selected-package).
The installer and runtime do not change item ownership, quantities or pickup rules.

## Candidate live skill compilation

`server/examples/compile_live_skills.rs` validates a candidate schema-v1 skill
catalog through the actual live compiler without swapping imported client files.
It emits Rust definitions for inspection; it does not install or publish content.
See [skill authoring](skills.md#fixed-area-authoring-and-runtime) for the command,
current area-handler coverage and remaining Three-Way Cut fidelity requirements.

## Mob flinch compilation and QA

`server/build_mob_reactions.rs` compiles GOOD damage clips from the presentation
bytes already verified by the mob package loader. Its derived table is appended
to the validated registry in build output; the original package stays unchanged.
Default builds compile the small fixture's own presentation manifest. Native
`tools/test_actors.py --scenario mobs` now also exercises every front/back damage
variant through the actual PvE actor. These controlled rows verify clip selection
and playback separately from multiplayer hit/reaction acceptance.

## Three-Way Cut two-client replay

`tools/test_progression_admin.py three_way_cut` uses the existing private two-account
fixture against a fresh QA-operator database. It creates/selects characters, raises
the operator character to level five, learns skill 1 and equips the starter sword.
It validates missing/stale targets, walks to the training dummy through normal
movement, casts once, and compares three health transitions observed by both clients.
Run on fresh characters with skill 1 unlearned; it is not a database-reset command.
Pass the same `--server`, `--game-server`, `--database`, `--godot`, `--fixture` and
`--report` arguments as the other progression replays. Dummy checks do not establish
ordinary mob reactions; use a separate real-mob replay for those.

Build selected skill data before refreshing UI art:

```sh
python3 tools/build_skill_catalog.py --offline
python3 tools/import_metin_ui.py --offline
```

The UI importer includes the installed catalog's original icons automatically.
`--skill-inventory` additionally includes an explicitly discovered pinned inventory.
The skill hash changes when the selected profile changes, so use a matching module
and export; an old server is expected to fail the client content gate.

## Equipped skill animation fixture

`tools/test_actors.py --scenario equipped_skills --native` renders every enabled
Warrior skill on both appearances with the original equipped sword. It resolves
skills across the onehand/general motion modes, finishes transition blending,
seeks and freezes four source-time poses per clip, checks skeleton/equipment bounds,
and captures each pose with a camera centered on the deformed skeleton. It reuses the shared actor fixture’s scene, camera and validation helpers. It covers selected live skills without rerunning
the entire 88-motion candidate suite. It does not qualify browser rendering or
server hit reactions.

## Original mob skill-reaction replay

Authored `MT2_POPULATION_PROFILE` layouts can reference any vnum supplied by the
verified `MT2_MOB_CONTENT` package. Without that package they retain the default
single-mob registry. Unknown definitions reject; selecting a layout never changes
creature stats. `content/worlds/training.skill-reactions.population.json` places
original Grey Wolf 106 on the training map for surviving three-hit reaction QA.

Build a fresh QA module using that profile plus the original mob package (without
`--features yongan`), the existing local auth issuer and the authorized QA operator
identity. Freeze the module, publish to a fresh `mt2-p2-` database, then run
`tools/test_progression_admin.py skill_reactions` with the usual server/database/
Godot/private-fixture/report arguments. It learns Three-Way Cut on fresh characters,
walks to the mob, and records independent damage/reaction/force/recovery observations
from both clients. The original clips can outlast the skill action: the fixture
waits for actual recovery within eight seconds instead of imposing a shorter clip.
No server inspection reducer or mutable creature-stat override is added.

## Compatible skill batch replay

Use `tools/test_progression_admin.py skill_batch` with the existing server,
database, Godot, private-fixture and report arguments against a fresh disposable
`mt2-p2-*` database built with the matching installed skill catalog. Reuse authorized
test accounts; preserve existing databases. The phase learns Warrior skills
1/2/16/17, raises the character to level 8 with server-authorized controls, then
checks both clients observe the expected 3/1/1/1 dummy hits and cooldown rejection.
It respects the one-second operator mutation limit. This phase currently qualifies
these four selected skills; extend its expectations when changing the batch.

`tools/test_actors.py --scenario equipped_skills --native` automatically samples
all selected Warrior skills on both appearances. Run
`tools/test_target_client.py --suite skills_ui --native` for icon, quickslot and
scroll-panel input coverage. The current UI fixture expects the four-skill profile.
Browser and ordinary-mob reaction acceptance remain separate checks.

## Select the ordinary-mob skill reaction replay

`tools/test_progression_admin.py skill_reactions --reaction-skill 16` tests Spirit
Strike; use `17` for Bash or omit the option for Three-Way Cut. Supply the usual
explicit auth/game endpoints, Godot, private fixture and output report. Build the
selected original mob registry with
`MT2_POPULATION_PROFILE=content/worlds/training.skill-reactions.population.json`
(use its absolute path), without Yongan or an original-population override. Each
run needs fresh character progression in a separate disposable database; reuse
the existing private test accounts and preserve previous databases.

The expected hit/flinch/push records live in `tools/skill_reaction_smoke.gd`.
Extend these explicit acceptance expectations when adding another supported
reaction scenario. They are independent expected outcomes, not values copied
from the running server. Spirit Strike and Bash each passed 30 two-client checks
against original Grey Wolf health, knockdown/standup and recovery. No rendering is
performed by this headless network replay; equipped native and browser QA remain
separate scopes.

## Skill-panel input inspection

The existing UI snapshot now reports skill controls by vnum, with viewport-space
slot and learn-button centers, full-slot visibility, learning availability and the
scroll center/offset. Browser automation should scroll until the desired control
is fully visible, then use ordinary mouse input. These are read-only observations;
learning and casting remain normal validated intents. Normal exports still exclude
the browser probe, and these observations do not add privileged commands.

The native `skills_ui` fixture passes 24 checks, including actual learn-button
press/release, scrolled Bash right-click, and drag/drop into a quickslot. The
fixture supplies projected learned state; it does not prove server learning or
browser casting. Synthetic wheel input must include release events: omitting them
interfered with the following right-click even though hover reached the correct
slot. Use viewport-local motion/button coordinates, matching the other UI fixtures.
Evidence: `.local/p6-skill-controls-r7/`; the rendered panel/quickslot capture was
reviewed. Exported browser learning/casting integration remains the next step.

## Focused exported skill controls

`tools/test_browser_skills.py --url <local-proxy> --database <mt2-p2-database>
--fixture <owner-only-account-fixture> --output <fresh-evidence-directory>` runs
Spirit Strike and Bash by default; `--skills` selects the vnums. It reuses exactly
two accounts from the progression fixture, with existing selected characters.
The first account must have server-authorized progression controls; the replay
uses ordinary chat `/level` for sufficient points, then actual learn buttons,
mouse dragging to quickslots, pointer targeting and number keys. It verifies
subscribed rank/cooldown, fresh attack sequences on both clients, matching dummy
damage and surviving target life. Browser engine errors fail acceptance.
The test does not add a privileged probe action or write gameplay tables.

Use an isolated proxy and matching exported client/server content. The replay
spends points (upgrades existing skills on subsequent runs) and moves the character;
retain previous reports and databases. The final local run passes 32 checks with
two hardware-rendered Chrome contexts. It is a focused skill-controls replay,
not a replacement for account lifecycle, ordinary-mob reactions or all-rank balance.

World actor catalogs must load the installed expanded character models, as the
character previews do. `Main` now explicitly selects them at startup and content
reload. The older default catalog mode retains the base Warrior fixture for
fixture consumers; using it for the live player omitted newly imported skill
motions even though native equipped tests using expanded models passed.

## Original motion-effect extraction

`python3 tools/motion_effects.py --msa LOCAL_MSA --msa ANOTHER_MSA --output NEW_JSON`
extracts selected original type-1 effect events into a candidate manifest. It preserves
source hashes, microsecond timestamps, explicit root/bone follow or capture modes,
and converted metre offsets. Unknown fields/invalid flags reject; other unsupported
motion metadata is retained in the report. The output must not already exist.
This command does not fetch assets, install content or enable gameplay. Link referenced
MSE effects and converted skeleton bones before installing motion presentation.

Run `python3 tools/test_motion_effect_playback.py --godot GODOT --output NEW_DIR`
for isolated headless checks of ActorPresentation effect timing, resync, completion
and legacy projectile dispatch. It records source hashes and rejects engine errors.
This tests event signals with a real AnimationPlayer, not effect rendering or servers.

The particle `--scenario render` gallery also exercises `WorldMotionEffects`
with real renderer instances and synthetic actor/bone poses: signal spawning,
follow/capture transforms, actor exit and natural effect completion. This does not
replace equipped animated-character or exported multiplayer effect qualification.

For the actual equipped Warrior effect gallery, run:

```sh
python3 tools/test_actors.py --scenario skill_effects --native --godot GODOT \
  --effect-catalog PARTICLE_CATALOG --effect-links SELECTED_LINKS_JSON --output NEW_DIR
```

The links are selected `{actor_id, skill_vnum, effects}` records from the source
adapter/resolver. The current fixture selects complete effects for skills 1, 2 and
16 across both Warrior sexes. It runs actual clips and source event clocks with
original swords, captures three frames per appearance/skill and checks deformation
and renderer errors. Candidate events are injected only into the isolated test;
no installed catalog is rewritten. This scenario keeps texture import/3D checks,
but the editor texture negative control is opt-in because asset importing is unchanged.

`tools/import_projectile_mesh.py --mixed --effect ORIGINAL_MSE --blender BLENDER
--output NEW_DIR` converts every particle and mesh layer of a selected mixed effect.
The candidate mesh catalog includes `particle_effect`, decoded/hash-verified particle
`textures`, and `layer_order`. The default remains strict mesh-only conversion.
Neither mode installs runtime content. Mesh positions must currently be constant.
Frame delays use a bounded rational Blender timeline with integer key spacing and
`fps_base=1`; geometry, UVs, morph weights and animation boundaries are audited.

Add `--scenario mesh_clock` to `tools/test_motion_effect_playback.py` for isolated
original mesh timing checks (delay, finite/infinite loops, exact deadlines and
bounded catch-up). The default actor scenario remains unchanged. The native
`test_particle_emission.py --scenario mesh` checks the arrow renderer using this clock.

Use `test_particle_emission.py --scenario skill_mesh --catalog MIXED_MESH_CATALOG
--godot GODOT --output NEW_DIR` for Bash's selected native mesh material/animation
checks. It checks additive color ramps against measured framebuffer backgrounds,
all original frames, staggered starts and finite completion, with saved captures.
This scenario checks mesh layers individually, not the complete mixed effect.

Use `test_particle_emission.py --scenario mixed --catalog MIXED_MESH_CATALOG
--godot GODOT --output NEW_DIR` to run the complete Bash particle/mesh gallery.
This checks the combined lifecycle and missing-resource rejection, with native
captures. It does not install effect links or prove browser/world integration.

Add `--mixed-effect-catalog MIXED_CATALOG` to the equipped `skill_effects` actor
scenario and supply all eight Warrior skill/sex links to include complete Bash.
The runner verifies and stages mesh/texture assets separately; the fixture uses
normal resource loading for mixed assets and captures the short Bash burst at
frame 65. This is still an isolated candidate test, not a live package install.

## Motion effect runtime packaging

```sh
python3 tools/build_motion_effect_catalog.py --particles PARTICLE_CATALOG \
  --mixed MIXED_CATALOG --links RESOLVED_LINKS_JSON \
  --skills client/assets/imported/skills/catalog.v1.json \
  --characters client/assets/imported/characters/catalog.v1.json --output NEW_DIR
```

The generated `runtime/` contains only the catalog, hashed PNG/GLB resources and
owned texture import settings. `receipt.json` stays outside that runtime directory.
Every enabled skill appearance must resolve to an installed motion and packaged
effect. The packager checks source resource hashes, canonicalizes PNG encoding
without changing decoded pixels, and rejects conflicting textures or incomplete
links. The current source-to-actor yaw is 180 degrees, matching the character
converter. This command prepares a package; it does not install or deploy it.


For packaged-resource qualification, replace the candidate effect flags with:

```sh
python3 tools/test_actors.py --scenario skill_effects --native --godot GODOT \
  --effect-package NEW_DIR/runtime --output NEW_EVIDENCE_DIR
```

This verifies declared file/import-setting hashes before staging and loads assets
through Godot ResourceLoader. The fixture exercises copy-safe motion event joins,
matching catalog hashes and equipped effects. It does not install the package or
prove normal world subscriptions/browser rendering.


World entry now requires the matching runtime motion-effect catalog at
`client/assets/imported/motion_effects/catalog.v1.json`. Install only the generated
runtime directory (catalog, declared hashed assets and import settings), after
checking character/skill hashes; keep its receipt outside the client. The current
local installation is from `.local/p6-skill-effects-r16/package-r2/runtime`.
The packaged actor scenario now exercises the actual `play_action` event join and
world-controller prepare/clear/rebind lifecycle. Browser/subscription acceptance
remains a separate check.


The browser skill replay also checks new motion-effect instances on both clients
and saves per-context videos under its private evidence directory. Use those
recordings for short bursts that have ended by a post-damage screenshot. The
read-only `motion_effects` snapshot reports the loaded package hash, spawn count,
active instances, bindings and renderer error. It does not expose effect-spawning
commands or confer gameplay authority. Existing visible skill controls are reused
without resetting scroll before a drag.


## Batch class-skill effect discovery

```sh
python3 tools/discover_skill_effects.py --offline \
  --skills SKILL_SOURCE_INVENTORY --characters CHARACTER_IMPORT_PROFILE \
  --output NEW_JSON
```

This uses the pinned skill inventory and character profile to resolve each
appearance's original race script and MSA through archive precedence. It extracts
all supported type-1 effect events, records source hashes, groups referenced MSEs,
and preserves rejected events with reasons and all remaining metadata. Existing
outputs are never overwritten; offline mode fetches nothing from the network.
The report is an unresolved candidate: original/converted bone resolution, MSE
conversion, runtime feature support and gameplay acceptance are still required.
It does not install assets or enable a skill. Adding a skill to the selected
inventory automatically includes both configured appearances in this scan.


Resolve the batch inventory against installed character resources with:

```sh
python3 tools/resolve_skill_effects.py --offline --inventory NEW_JSON \
  --characters client/assets/imported/characters/catalog.v1.json --client client \
  --output NEW_RESOLVED_JSON
```

The resolver checks race/model hashes, reads original bones with the pinned Carbon
reader and counts only GLB skin joints as converted bones. A bone lost in conversion
rejects the batch; an originally absent bone follows the existing source-aware
fallback rules. The output retains unresolved non-type-1 metadata and source
provenance. It does not modify models, convert effects or enable gameplay.


Audit the distinct referenced MSE definitions before scheduling conversions:

```sh
python3 tools/audit_skill_effect_resources.py --offline \
  --inventory NEW_RESOLVED_JSON --output NEW_AUDIT_JSON
```

Omit `--offline` to fetch only the selected MSE definitions through the pinned
archive. The audit preserves every layer kind and parser failure with source hashes
and links to affected skill events. `parsed-not-converted` means syntax/subset
acceptance only: textures, geometry conversion and runtime rendering remain
unqualified. Unknown layers are not discarded to make a partial effect pass.


Scalar particle curves retain signed key times in [-3600, 3600]. Sampling at
nonnegative effect time interpolates across a negative first key; do not clamp
that key to zero during conversion. Start delays remain nonnegative. The existing
particle emission fixture includes negative-key interpolation, ordering/bounds
rejection and live emission checks.


The native `skill_mesh` scenario now sweeps selected mesh color operations 3, 4
and 6 against two framebuffer backgrounds. The renderer retains its white-factor,
opaque-texture restrictions; parser acceptance alone does not imply other material
combinations render. Preserve this distinction when selecting new effects.


Mesh MOVE billboard type 3 is currently renderable only for a singleton direct
position track, matching the original zero-displacement identity rotation. The
parser preserves the type for discovery, but moving tracks require further runtime
work. The native skill-mesh fixture exercises this distinction.


Selected MDE/MSE mesh geometry counts are bounded at 32, allowing original Dash's
24 elements without dropping geometry. The binary byte/vertex/frame/payload limits
remain enforced. Mixed conversion audits every element, but the current Godot
runtime still requires one geometry per mesh recipe; conversion acceptance is not
runtime acceptance for multi-element effects.


Mesh color factors now support finite RGB channels in [0,1], packed to original
byte precision before modulation. Alpha remains constrained to 1 in this renderer.
The `skill_mesh` native scenario covers white, both original Dash gray values and
an asymmetric colored factor across operations 3/4/6. Multi-element scene support
is still separate from this material capability.


The shared mesh renderer now supports up to 32 ordered surfaces in one scene,
with a shared frame clock and per-surface factors/textures. Mixed effects pass the
resource dictionary and assign priorities to every material. Source-color RGB
blends accept alpha-bearing textures because texture alpha does not participate
in their supported RGB equation; transparent viewports still reject. The native
mixed scenario derives layer counts from its catalog and verifies each surface's
material/factor, so it can exercise complete Dash as well as Bash.


The equipped candidate skill-effect fixture accepts arbitrary selected skill pairs:
each vnum must have unique installed motions for both appearances of one class.
Screenshots follow clip duration (25/50/75 percent), with the existing dedicated
Bash burst capture retained. The current fixture still equips sword 10; other
weapon-specific skills require the corresponding equipped fixture extension.
