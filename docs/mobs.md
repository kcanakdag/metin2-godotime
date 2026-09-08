# Original mob pipeline

## Projectile mesh conversion

```sh
python3 tools/import_projectile_mesh.py --offline \
  --effect 'ymir work/pc/assassin/effect/arrow_01.mse' \
  --blender /path/to/blender --output /path/to/new-arrow-package
```

The selected arrow effect uses one five-frame MDE mesh and its original TGA.
The importer reuses background Blender conversion, converts the texture, retains
the MSE render recipe and audits every exported frame/UV against source geometry.
It currently accepts fixed-position, 50 FPS mesh effects with reviewed blend
metadata. Reading a blend pair does not add renderer support: the ordinary target
effect parser still defaults to its existing supported subset. The arrow's 3/8
blend pair remains an explicit runtime requirement.

The generalized GLB audit now supports sparse morph accessors, variable source
frame/geometry counts and explicit offsets. An initial arrow audit rejected
Blender's sparse zero-delta frames; the reader was corrected, not the exported
model. Both installed click-effect GLBs still pass the same full geometry audit.

`.local/mobs/arrow-mesh-r2` contains the converted arrow and source-bound receipt.
The isolated native Godot probe in `arrow-native-r1` verifies four morph targets,
all five frame-weight states and a 0.1-second loop; the textured arrow was visually
inspected. Sixteen Python tests and Python lint pass. This is geometry/animation
evidence, not original blending, in-flight attachment, particle effects or live
combat qualification. Seven of the eight referenced MSE files are particle systems
and still need the shared particle importer/renderer.

## Flight-definition discovery

```sh
python3 tools/discover_projectiles.py --offline \
  --catalog /path/to/gameplay.v1.json --output /path/to/new-projectile-inventory
```

Omit `--offline` only to fetch the flight scripts explicitly referenced by the
candidate catalog. The command validates the catalog hash and records pinned MSF
source hashes, source loader defaults, original flight parameters, attachments and
resolved MSE dependency paths. It does not fetch or convert those MSE dependencies
yet, and does not change the installed game. Original units remain centimetres,
seconds and degrees for the future coordinate adapter.

The 26 White Oath launches share four MSF definitions with five attachments and
eight effect dependencies. These include homing, acceleration, angular velocity
and two offset strands; they cannot all be replaced by a generic straight arrow.
`CollisionSphereRadius` is recorded as ignored because its original loader read
is commented out. Malformed/unknown fields and unsafe paths reject.

`bou_20_1_throw.msf` contains negative trail dimensions. The importer preserves
those numbers and flags them explicitly. `FlyTrace::UpdateNewPosition` immediately
expires history for a negative trail lifetime, so the recorded policy is
`expires-immediately`; no positive replacement dimensions are invented. Other
invalid trail dimensions still need explicit handling before runtime use.

`projectile-sources-r5/r6` are byte-identical offline inventories. An earlier repeatability check found
unstable JSON key ordering; the writer now sorts keys and retains those earlier
outputs for diagnosis. Three parser
tests and Python lint pass; evidence is
`.local/mobs/projectile-source-acceptance-r1.json`. MSE conversion, flight rendering,
coordinate/attachment validation in Godot and authoritative attack integration
remain unfinished.

## Full candidate attacks and projectile declarations

`build_mob_catalog.py` now compiles all 44 converted definitions into 78 ordinary
attack variants: 52 melee and 26 projectile variants. Each attack declares
`delivery` and `damage_kind`. Melee retains its existing hit windows; projectile
attacks retain an empty window list and explicit `projectile_launches` instead.
The source definition still preserves the original stats and battle dispatch.

`mob_projectiles.py` validates type-6 events against their exact actor/action/MSA
identity, timestamp, source fields, attachment flag/bone and safe MSF path. Source
positions remain explicitly in centimetres; they are not silently reinterpreted as
Godot local coordinates. Launch records preserve source and speed-adjusted timing.
Unknown events, duplicate declarations, mismatched MAGIC/RANGE dispatch and missing
launches reject. MSF effects and their dependencies are not imported by this linker.

These are visual launch declarations, not server damage authorization. The pinned
`CHARACTER::Attack` dispatches MAGIC/RANGE through `Shoot`; `CFuncShoot` applies
the appropriate damage type/resistance. `CalcMagicDamage` derives NPC base damage
through `CalcMeleeDamage`, but that does not make its final damage type melee or
justify ignoring magic resistance. The authoritative implementation remains
pending. Catalogs/receipts explicitly list unimplemented runtime requirements.

`.local/mobs/population-gameplay-r2` links all models and actions; the original
five-species melee records are unchanged after removing the new descriptive fields.
Twenty-eight focused Python tests and Python lint pass. Evidence:
`.local/mobs/projectile-linker-acceptance-r1.json`. The melee timing fixture rejects
projectile catalogs until its gameplay scenario supports them; the separate full
asset gallery remains valid conversion evidence. No runtime, export or deployment
claim is made from this candidate compilation.

## Original regeneration runtime contract

Population discovery now emits a `runtime_policy` for persistent overworld
regeneration and an `enabled` flag per entry. A zero interval disables initial
spawning too; disabled entries retain their source dependencies but contribute
zero to the initial population bound. Dungeon and stone summons are separate
source paths and are not covered by this contract.

Enabled entries fill immediately, then first tick after their interval plus a
uniform integer 0–16 seconds of jitter. Subsequent ticks use the entry interval
and attempt each missing unit once. A group counts as one unit owned by its
leader. The original `CHARACTER::Destroy` releases that unit; damage/death alone
does not release it. Surviving members retain independent lives and must not be
removed or respawned merely because the group leader was replaced.

The first member uses the entry rectangle. Each successful member establishes
the next rectangle around its own position, with four independently sampled
300–500 cm offsets. Each member gets up to 16 range-placement attempts. Leader
failure aborts the group; follower failure skips that follower and retains the
last successful rectangle. Range spawning uses section zero and random 0–360
degree headings; the file's direction/section apply to the separate point path.
The source's range-regeneration exception check is commented out. Modern collision
validation must still validate actual sampled positions through the map adapter.

`yongan-runtime-policy-r1` and `r2` preserve the full 945-entry, 54-group,
44-definition closure and 2,963 initial member bound. The new receipt includes
`char.cpp` in source hashes to bind the destruction contract. This metadata is
not yet connected to live regeneration; the existing authored dog homes still
use their current lifecycle.

The reusable Rust scheduler is `server/src/regeneration.rs`. It plans a new entry
state while a caller supplies successful spawn-owner tokens; the caller must
persist that state and spawned rows in one transaction. Tokens increase and cannot
be reused after destruction, preventing stale cleanup from freeing a replacement
life's capacity. Failed placements consume only the current tick's bounded attempt;
there is no catch-up burst after a delayed tick. This core is currently exercised
offline and has not yet been connected to SpacetimeDB tables or combat cleanup.

Run the offline lifecycle stress command with a freshly audited inventory:

```sh
cargo run --manifest-path server/Cargo.toml --offline --features yongan \
  --example regeneration_stress -- /path/to/population.v1.json
```

This hash-checked scenario chooses each selector's largest group, assumes all
placements succeed, destroys all initial owners and retains every follower before
one refill. Yongan produces 945 initial units/2,963 members, 2,018 surviving
followers and 4,981 members after refill. This deliberately exercises a population
growth case, not expected live density. It does not test placement, collision,
combat or subscriptions. The three `--test regeneration` Rust tests cover timing,
failed placement, exact owner destruction, stale tokens and atomic state planning.

The scheduler also exports/restores a storage-neutral snapshot containing its
deadline, startup flag, current owner tokens and highest issued token. Restoration
validates capacity, sorted unique nonzero owners, issued-token bounds and deadline
consistency. The storage caller must bind snapshots to their exact entry and
content identity; the offline tool checks both against its inventory.

Exercise a separate-process checkpoint/resume:

```sh
cargo run --manifest-path server/Cargo.toml --offline --features yongan \
  --example regeneration_stress -- /path/to/population.v1.json \
  --checkpoint /path/to/new-checkpoint.json
cargo run --manifest-path server/Cargo.toml --offline --features yongan \
  --example regeneration_stress -- /path/to/population.v1.json \
  --resume /path/to/new-checkpoint.json
```

Checkpoints use new files only and are local developer fixtures, not authenticated
server backups. The tool rejects another inventory, changed entry identities,
invalid deadlines, reused cross-entry owners and regressed allocation counters.
The checkpoint/resume acceptance run restores all 945 entries and matches the
uninterrupted 4,981-member result. Five Rust tests and eight process-level checks
pass in `.local/mobs/regeneration-restore-acceptance-r1.json`. This does not prove
a SpacetimeDB restart: persisted tables and transactional live integration are
still pending.

The shared `npc_placement::sample_group` planner now implements the original
leader-first chain using the existing sixteen-attempt range sampler. It aborts
after a failed leader, skips failed followers, and derives each next rectangle
from the most recent successful member. Derived rectangles may cross map edges;
individual samples still require terrain acceptance. Four independent 300–500 cm
offset draws follow each success. The module is a public pure Rust API, not a new
SpacetimeDB reducer; existing NPC behavior remains unchanged.

Inspect the complete group selection against the server's baked Yongan map:

```sh
cargo run --manifest-path server/Cargo.toml --offline --features yongan \
  --example population_placement -- /path/to/population.v1.json 42 \
  > /path/to/placements.json
```

The tool verifies the inventory hash, samples original selectors uniformly and
records source entry/unit/member identity, coordinates, height and heading. It
currently supports group families (`g`, `ga`, `r`) on Yongan. Positions use the
server's current movement footprint; species-specific footprints remain future
work. Seed 42 places 2,853 members across all 945 units and all 44 definitions;
seed 43 places 2,843, with no failed leaders or followers in either run. Repeating
seed 42 produces identical output. Evidence is in
`.local/mobs/population-placement-acceptance-r1.json`. These are real-map offline
placement checks, not live actor spawning, rendered map inspection or multiplayer
evidence.

`content/profiles/yongan-wildlife.json` explicitly selects Wild Dog 101, Wolf 102,
Wild Boar 108, Bear 110 and Tiger 114. This is a candidate source inventory, not
an installed runtime registry or a new spawn layout.

```sh
.local/venv-dev/bin/python tools/discover_mobs.py --output .local/mobs/wildlife
# Once the selected source metadata is cached:
.local/venv-dev/bin/python tools/discover_mobs.py --offline --output .local/mobs/wildlife-recheck
```

Use a new output directory each time. The command reads pinned server proto/name
tables and client registrations, resolves model and motion-list paths through the
archive's pack precedence, and records original collision metadata. Output stays
in ignored directories. It does not execute legacy code or install game content.
The receipt hashes the selected profile, compiler and inventory; changing inputs
during compilation fails. Source records retain file and row hashes.

The inventory preserves stats, damage multiplier, reward ranges, all source
resistance/enchantment columns, AI/race/immunity flags and special mechanics.
Empty original skill slots remain `null`, distinct from a recorded zero. Gameplay
integration must resolve these fields deliberately; their presence does not imply
that the live server implements every mechanic. Unknown monster identities,
duplicate rows, malformed columns, invalid bounds and nonfinite values reject.

The selected source HP values are 126, 162, 248, 381 and 585 respectively. The
current development dog has 100 HP; adopting the original registry must explicitly
update that fixture and its tests. Do not copy its values onto other mob types.
The existing gameplay still embeds one ordinary mob definition, with a separate
authored dummy. The shared population parser now accepts an explicit registry and
retains every placement's definition vnum. The current build supplies only the
implemented ordinary vnum; additional source definitions are not yet accepted as
playable monsters. The authored dummy's compiled placements retain its own vnum.
Combat verifies the persisted mob against its assigned spawn ID/type.

`.local/mobs/yongan-wildlife-r3` resolves five model paths and 69 original motion
registrations offline. Three parser regression tests and Python lint pass. The conversion follow-up below now covers the asset stage. Trusted registry
compilation, per-definition AI/damage/rewards, world attack checks and actual
two-client gameplay remain required.
No new mob is live and no original spawn group is replaced by an invented layout.

## Convert and inspect selected wildlife

```sh
.local/venv-dev/bin/python tools/import_mob_content.py --offline \
  --blender /path/to/blender --output .local/mobs/wildlife-converted
.local/venv-dev/bin/python tools/test_npc_content.py \
  --content .local/mobs/wildlife-converted --native --godot /path/to/godot \
  --output .local/mobs/wildlife-actors
```

Omit `--offline` on the first conversion to fetch the explicitly selected model,
texture and animation dependencies. The importer reuses the existing actor
converter and material resolver. The existing NPC-named gallery checks ordinary
skinned actors too; no NPC runtime behavior is assigned to these mobs. Conversion
runs in background Blender and leaves the open editor untouched. Output includes
normalized source motion metadata, GLBs and hash-bound conversion receipts.
Original GR2 is not a runtime dependency.

For the full map selection, pass
`--profile content/profiles/yongan-population.json` to the same importer. Identical
render inputs share one GLB, selected deterministically by the lowest definition
vnum; different textures, motions or attachment data prevent sharing. Each mob
retains its own definition and action IDs, mapped to the shared file's actual
clip names. `conversion-input.v1.json` is the unique-model subset of the full
normalized manifest. `blender-unique-report.json` records physical conversions;
`blender-report.json` expands that evidence to every definition with explicit
`shared_model_actor_id` links. Both reports are hashed in the conversion receipt.

Motion registration follows the pinned `RaceManager::__LoadRaceMotionList`:
exact registrations take precedence over its one/two-character suffix fallback.
Unregistered command/special-attack rows remain in
`ignored_motion_registrations`; they are not invented as playable actions.
Actor conversion selects the model's mesh bindings in their original order,
recording file-level meshes that the model never references. This excludes the
Archer's unused `Line01` geometry without guessing a bone attachment.

`.local/mobs/wildlife-converted-r1` contains five textured models and 68 reachable
motions. The original dog list's second back-damage registration follows a
100-weight entry and is unreachable; the importer retains the original selection
semantics. No unsupported motion events were reported. `wildlife-actors-r1`
passes 304 native Godot checks for exact clip sets/durations, changing finite bone
poses, skin bindings and textured surfaces. All four new models were inspected
from front/back/sides and face Godot -Z. This is component evidence, not proof
of combat hit timing, moving world actors or two-client gameplay.

The shared material resolver now permits an ambient map only when it references
the same texture as diffuse, as in the original dog. Separate ambient textures
still reject. A regression covers both cases. The first conversion failure is
retained; the successful retry uses that shared-material fix.

Next, compile per-definition attacks, collision, stats and rewards into a trusted
mob registry, replace dog-only runtime references, then qualify real movement,
combat, life/respawn and reward handling with independent clients. Do not install
these models as static scenery or label conversion as playable enemy support.

## Physical registry checkpoint

Ordinary physical attacks and defenses now resolve a trusted definition by vnum
and actor ID. The runtime registry still includes only the existing dog; the
training dummy retains its authored defense profile. Candidate wildlife stats can
be compiled without installing them:

```sh
cargo run --manifest-path server/Cargo.toml --offline --example compile_mob_physical -- \
  .local/mobs/wildlife-converted/normalized.v1.json .local/mobs/wildlife-physical.rs
```

The compiler validates actor links, duplicate identities, numeric ranges and
runtime float precision. Unsupported nonzero combat modifiers reject instead of
silently disappearing. Original POWER-family battle types use the same physical
handler as MELEE. The Boar's five-percent normal-hit critical chance is retained;
normal critical damage doubles with checked overflow. Skill critical probability
and critical visual effects are separate, unfinished mechanics.

The five-definition candidate compiles in `wildlife-physical-r2.rs`. The runtime
adapter checkpoint passes 161 Rust tests, strict Rust lint and 113 checks with two
authenticated clients in `physical-registry-live-r1.json`. Those live checks use
the existing dog population on `mt2-p2-mob-physical-qa-r1-20260908`; they do not
establish five-species gameplay or change the served client/server build.

## Gameplay registry consumers

`MobDefinition` now supplies ordinary spawning identity, presentation, health,
level, movement/acquisition/chase parameters, attack timing, XP/gold ranges,
respawn delay, defending sphere and knockdown/standup reactions. Runtime consumers
resolve the actor's trusted vnum; they no longer substitute dog constants. Invalid
persisted health, level, model or motion-set metadata rejects instead of being
silently repaired. The registry still wraps the existing dog fixture; the dummy
uses its own passive definition and cannot become an ordinary reward source.

The follow-up passes 162 Rust tests and strict Rust lint. Actual authenticated
two-client QA passes 113 checks on `mt2-p2-mob-runtime-qa-r1-20260908`, recorded in
`.local/mobs/runtime-registry-live-r1.json`. The published schema matches the
committed bindings; protocol 18 is unchanged. The acceptance receipt records
module, report and schema hashes. No exports or served endpoint changed.

Remaining integration includes compiling all five gameplay records from the
converted catalog, matching client content identities, original spawn groups and
passive/provoked AI. The existing potion drop remains a development fixture;
per-definition XP/gold does not establish original item-drop-table parity.

## Compile converted motion mechanics

```sh
.local/venv-dev/bin/python tools/build_mob_catalog.py \
  --content .local/mobs/wildlife-converted --output .local/mobs/wildlife-gameplay
```

This creates `gameplay.v1.json` and a receipt in a new directory. It requires the
conversion receipt, checks the exact normalized/report/model hashes and matches
every reported animation ID, name and duration. Changed conversion inputs reject
before output is written. Generated content remains ignored and is not installed
by this command.

The catalog preserves all nine weighted normal-attack variants across the five
species, original hit samples and parameters, per-species defending spheres and
front/back knockdown and front-standup durations. It derives run speed from the
converted run accumulation and duration. Full source records, including pending
AI/regen/drop mechanics, remain attached; the compiler does not replace them with
the dog fixture's values. Unsupported geometry, motion groups or deferred events
reject rather than choosing a default. The current geometry policy retains the
single original Bip01 sphere, as in the existing runtime; this is not new world
collision or animated hit-geometry qualification.

Timing records distinguish the pinned server's `CalculateDuration` cadence from
precise client animation playback. Boar attack speed 80 yields a 2.4-second source
server cooldown, while a 1.5-second clip plays for 1.875 seconds. Bear move speed
70 applies the original 130-percent duration factor, rather than multiplying its
run speed by 0.7. Faster server cadence retains the original integer-percent
rounding. Motion hit-window timestamps are separately scaled using ceiling
division for future authoritative animated hits; the original server's immediate
damage dispatch is not reproduced by that scheduling proposal.

Rules are recorded against server revision
`7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318`: `utils.cpp:CalculateDuration`,
`char.cpp:GetMoveMotionSpeed/GetMoveSpeed` and `char_state.cpp:StateBattle`.
This compiler requires that reviewed revision. Runtime integration still needs
weighted action selection, matching client playback/catalog gates, original
population/AI handling and deliberate reward-table support.

`.local/mobs/wildlife-gameplay-r3` and `r4` produce identical catalogs for five
mobs/nine attacks. Six compiler regressions and three mob-source tests pass, as
does Python lint. A real CLI check rejects altered converted metadata before
creating output. `gameplay-catalog-acceptance-r1.json` records this evidence.
No model, live module, exported client or served endpoint changed.

## Authoritative weighted action selection

The shared runtime now accepts up to 16 weighted ordinary attacks per definition,
with a required total of 100 and a shared validated range. Selection occurs once
when an attack starts. Its published action ID, duration and delayed hit window
come from that entry; hit resolution rejects an action absent from the species'
registry. Single-action definitions retain the existing RNG behavior.

The current compiled dog remains one 100-weight attack. Rust tests exhaust all
100 rolls for a two-variant fixture, including distinct original dog windows,
and reject missing weights, duplicate IDs and invalid windows. These variants
are not installed into live content by this checkpoint.

All 164 Rust tests and strict lint pass. `weighted-actions-live-r1.json` passes
113 authenticated two-client checks against `mt2-p2-mob-actions-qa-r1-20260908`.
That live run exercises the existing single-attack population, not a distributed
weighted-variant test. The module's schema matches committed protocol-18 bindings;
`weighted-actions-acceptance-r1.json` records hashes and limitations. Client code,
exports and served endpoints are unchanged. The candidate catalog still needs
build-time integration and matching client playback before additional actions
or species can be enabled.

## Godot wildlife presentation

The catalog builder also emits `presentation.v1.json`, containing public actor
models, animation metadata, converted artifact hashes and the gameplay hash.
Original `front_dead`/`back_dead` registrations map to the renderer's canonical
`front_death`/`back_death` actions while retaining original IDs and clip names.
The shared actor reader accepts only the dedicated `assets/imported/mobs/actors/`
GLB directory, alongside its existing roots; traversal remains rejected.

```sh
.local/venv-dev/bin/python tools/test_actors.py --scenario mobs \
  --mob-content .local/mobs/wildlife-converted --native --godot /path/to/godot \
  --output .local/mobs/gameplay-presentation
```

The runner verifies conversion receipts, generates candidate catalogs and merges
their actors into a disposable fixture. Real PvE nodes receive controlled state
rows. The installed manifest and live world content checks are untouched.
Mob attacks now use `source_duration / (ends_at - starts_at)` for playback,
supporting slow original attacks without relaxing player speed bounds. Late
subscriptions seek at the same rate; completed actions hold the final pose.
Idle and new lives release that pose and reset playback speed.

`gameplay-presentation-r3` passes 125 rendered Godot checks across all five species,
nine exact attack variants, slowed/late playback, source recovery clips, death,
respawn and targeting. The five textured model captures were visually inspected.
`playback-regression-r1` passes 116 existing actor checks in headless Godot,
including player/skill presentation and the installed dog. Ten Python tests and
GDScript/Python lint pass. `playback-acceptance-r1.json` records evidence hashes.

The first render caught the missing model-directory allowlist entry; the second
caught the original death-action naming difference. Both failed runs are retained,
and the successful third run includes the fixes. No Godot MCP was exposed; tests
used isolated processes rather than the open editor. This is native component
evidence, not new live species, actual subscriptions or browser/export proof.
The live installer/hash gate and compiled five-species server registry remain
unfinished; no served endpoint changed.

## Original population dependency discovery

```sh
.local/venv-dev/bin/python tools/discover_mob_population.py \
  --output .local/mobs/yongan-population
```

The command reads committed blobs from the pinned local server checkout; use
`--source-checkout` to specify its location. `--map` selects the source map folder
and `--profile` selects the definition coverage being audited. It does not fetch
or convert additional assets, install a population, or change a database.
Output includes source/code/profile hashes, numeric definition names/folders,
centimetre rectangles, source directions, intervals and transitive group members.

Yongan's `regen.txt` has **945 `r` entries**, referencing **10 group selectors,
54 groups and 44 monster definitions**. These definitions use 12 source model
folders, though sharing a folder alone does not prove identical client material
or animation bindings. The current five selected definitions cover **zero complete
entries**: every selector includes at least one additional variant. Choosing only
available variants would change the original population distribution.

The parser distinguishes direct mobs (`m`), groups (`g`/`ga`) and selectors (`r`).
Group leaders and ordered member slots remain explicit. It follows the source
loader's first-missing-slot termination and records ignored later slots. Missing
or ambiguous referenced groups reject; unrelated duplicate IDs in the legacy
files do not prevent auditing this map. Unsupported families and point-group
entries reject rather than being interpreted as ordinary area groups.

Pinned `LoadGroupGroup` reads the file's probability field but calls
`AddMember(vnum)` without passing that probability. Output therefore preserves
`source_weight` separately from `effective_weight: 1`. The regeneration reader
also skips its percentage field; the importer records that distinction explicitly.
Compound intervals such as `1m5s` remain supported, including zero for the source
nonrepeating case. These are source semantics, not newly invented spawn chances.

The initial member upper bound is **2,963**, assuming all initial slots succeed
and each selector picks its largest group. It is not a steady-state live mob cap:
the group master owns the original regeneration slot, while followers can remain
alive. Cadence, group lifecycle, placement attempts, collision and passive/provoked
AI still need runtime implementation before these entries can be installed.

`yongan-population-r3` and `r4` are byte-identical. Five population-parser tests
and the ten existing mob compiler/source tests pass, along with Python lint.
`population-discovery-acceptance-r1.json` records the counts, hash and scope.
Next, resolve the 39 additional definition dependencies through the bounded map
selection, reuse verified identical model inputs where possible, and compile the
server registry alongside a matching live client catalog and group population.

## Derive and resolve the full map selection

```sh
.local/venv-dev/bin/python tools/build_population_profile.py \
  --population .local/mobs/yongan-population/population.v1.json \
  --output .local/mobs/map-selection.json
.local/venv-dev/bin/python tools/discover_mobs.py --profile .local/mobs/map-selection.json \
  --offline --output .local/mobs/map-assets
```

The builder checks the population hash, source revision and exact definition
closure, retains existing IDs from `--base-profile`, and derives stable IDs and
source folders for additional definitions. It refuses to overwrite an existing
output. The checked-in `content/profiles/yongan-population.json` selects all 44
Yongan dependencies. Its source inventory resolves **12 GR2 model paths and 19
race scripts**; auditing population coverage with this profile covers all **945
entries**. This counts declared definition references, not converted/live actors.

Default monster ShapeData can replace a model and remap its source skin to a
variant DDS. Discovery now records that selected shape, and conversion applies
its substitutions to exact material-bound paths. Missing/duplicate substitutions,
incomplete source/target pairs and unsupported shape fields reject. Source motion
paths continue to resolve from the original motion-list directory. This preserves
blue/grey wolves, bear colors and red boars without replacing their meshes with
different geometry. Model sharing in the runtime remains a separate optimization;
12 base models do not imply 12 identical appearances.

The 44-definition discovery first needed selected variant metadata fetched from
the pinned archive. `population-assets-r3` and `r4` then reproduce identical
inventories offline. The three-variant `skin-converted-r1` probe uses background
Blender; `skin-actors-r2` passes **179 native Godot checks** for clips, deforming
bones, skin bindings and textured surfaces. Blue Wolf 104, Red Wild Boar 109 and
Black Bear 112 captures were inspected. The first gallery clipped the Bear's
side views; its camera now uses the full bounds diagonal, and the repeat captures
show complete models. Twenty Python tests and Python/GDScript lint pass.
`population-profile-acceptance-r1.json` records the evidence.

Fourteen White Oath definitions have original battle type `MAGIC`; the physical
handler must continue rejecting them until their mechanics are implemented.
The new selection is not a claim that all 44 appearances are converted, that
model reuse is implemented, or that the original population is playable. Group
spawning/AI, complete combat handlers, shared model packaging, matching live
catalog gates and exported multiplayer QA remain pending. Served builds are
unchanged.
## Particle effect conversion

The selected particle-only MSE subset has a reusable offline converter:

```sh
python3 tools/import_particle_effects.py --offline \
  --effect 'ymir work/effect/monster/chaos_ghost_20_1_throw.mse' \
  --output .local/mobs/particle-example
```

Repeat `--effect` for up to 32 distinct recipes. Omit `--offline` when the
explicitly selected source scripts or textures need fetching. Output must be a
new directory; a failed run leaves its partial output for inspection, without a
success receipt. Successful output contains `effects.v1.json`, PNG textures and
`receipt.json`. This tool does not install effects, alter a database or export a
client.

The strict parser retains original emission shapes, timing/loop counts, position
keys, scalar curves, blend/billboard settings, attachment/stretch flags, rotation
and ordered texture frames. Duplicate frames remain intentional animation frames.
Curves retain original units; emitter-time curves are not arbitrarily clamped to
normalized particle age. Color keys include the original union of RGBA event times
with interpolated channels packed to bytes. Unsupported groups/interpolation,
unknown fields, malformed curves, nonfinite numbers and unsafe texture paths
fail conversion. This bounded subset requires explicit source fields and does
not implement every legacy loader fallback or mixed mesh/particle effect.

The seven selected projectile effects pass conversion in
`.local/mobs/particle-effects-r2` and an identical offline repeat in `-r3`:
22 systems and 12 distinct texture paths. Each PNG reproduces the source image's
decoded RGBA pixels. `particle-acceptance-r1.json` records the catalog/receipt
hashes, repeat comparison and 20 focused parser/mesh regression tests; owned
Python lint passes. The first offline attempt lacked the selected texture cache.

These are converted recipes, not rendered or multiplayer-qualified effects.
Particle simulation, original blend/billboard rendering and flight attachment
remain explicit runtime requirements. No new mob or class skill is playable from
this conversion alone. The shared format is intended for both projectile and
ability presentation, with server-owned damage remaining separate.

### Godot emission lifecycle

`client/scripts/actors/particle_emission.gd` now implements the shared presentation
emission lifecycle. It consumes imported emitter curves and returns particle births
and deaths with per-instance monotonic IDs. It preserves delayed-start activation,
fractional emission residue, discarded capacity overflow, finite/infinite loops,
single-cycle advancement per update, inactive emission and strictly-negative
lifetime expiry. Configuration is copied and bounded; rejected configuration or
nonfinite/invalid timesteps do not mutate the running instance. The original uses
single-precision floats; this Godot component is not a bit-identical replay claim.

Run its isolated actual-engine checks with:

```sh
python3 tools/test_particle_emission.py --godot /path/to/godot \
  --catalog .local/mobs/particle-effects-r3/effects.v1.json \
  --output .local/mobs/particle-emission-new
```

The fixture exercises all 22 selected systems for 1,200 updates each, plus focused
lifecycle/rejection cases. `.local/mobs/particle-emission-r2/report.json` records
90 passing checks in Godot 4.7.2, with source hashes and no engine errors. The runner
uses a private project/user-data directory; it does not touch the open editor.
An earlier manual run passed the assertions but could not write Godot's default
user-data directory; its log is retained under `particle-emission-r1`.

This component tracks emission/lifetimes. The companion kinematic simulation is
described below; geometry, materials and texture animation still need rendering
and visual qualification. Neither component is connected to the served game.

### Particle motion and moving emitters

`particle_motion.gd` supplies original shape sampling, source centimetre/axis
conversion, inward/outward emission, velocity dispersion, gravity and drag.
`particle_simulation.gd` connects it to the emission lifecycle, removes expired
particles and exposes presentation states by stable per-instance ID. Attached
particles retain local coordinates; world particles capture the emitter transform
at birth and remain behind as it moves. Randomness uses an explicit seed for
repeatable diagnostics; it does not reproduce the original RNG stream.

The implementation samples the original normalized cube/rectangle directions,
not an invented uniform sphere distribution. Gravity runs before per-update air
resistance, followed by position integration. The original particle dimensions
are half extents, and previous position is initialized from birth velocity for
future stretched-quad rendering. Source recipes must pass the offline importer;
this is not an API for untrusted client data. Non-rigid/nonfinite transforms and
invalid timesteps reject before state advances. Nonzero emitter angular orbit is
explicitly unsupported and rejected; every currently selected system uses zero.

Use the same runner with `--scenario motion`. The accepted
`.local/mobs/particle-motion-r1/report.json` records 89 actual-engine checks:
exact trajectories, force order, emitter attachment, ellipse/sphere edge emission,
inward/outward speed, rejection, and two identical seeded runs across all 22
systems for 600 moving/rotating-emitter updates each. Godot reports no errors.
The shared runner's emission regression also passes 90 checks in
`particle-emission-r3`. Owned Python and GDScript lint pass.

The renderer below now adds appearance around these states. Simulation checks alone
establish neither visual fidelity nor projectile flight, combat, multiplayer or
deployment acceptance.

### Selected particle rendering

`particle_style.gd` preserves packed-byte color interpolation, normalized scale
curves, degree-based rotation and original texture-frame deadlines/wrapping.
Random spin direction is selected once per emission batch, matching the source
decorator cloning rule. `particle_effect.gd` batches world-space triangles by
system/texture frame and renders the selected camera-facing or stretched quads.
It supports the selected 5/2 additive and 5/6 alpha blend pairs with color operation
4 and billboard types 0/1. Other render modes reject configuration rather than
silently receiving a default. Recipes and texture resources are trusted imported
content; a configured effect needs to be in a scene with an active camera.

Run the gallery using the same runner:

```sh
python3 tools/test_particle_emission.py --scenario render --godot /path/to/godot \
  --catalog .local/mobs/particle-effects-r3/effects.v1.json \
  --output .local/mobs/particle-render-new
```

On Linux this uses `xvfb-run` and Godot's Compatibility renderer in an isolated
project/user-data directory. Referenced PNGs are hash-checked before and after
copying; the report binds code, catalog, log and captures. No editor or served
package is modified. The accepted `.local/mobs/particle-render-r2/report.json`
passes 62 checks and records 35 captures at frames 3, 6, 12, 24 and 36 for all
seven effects. Early captures preserve the very brief impact flashes that had
already faded at frame 12 in the initial `particle-render-r1` gallery. All seven
early captures were visually inspected: flame projectiles, orange/pink/purple
impact rings and sparks render without opaque texture rectangles. Later captures
show their fading smoke/trails. `particle-render-review-r1.json` binds that review.

The actual driver was Mesa llvmpipe; X11 input-method and unsupported VSync warnings
were present, with no engine errors. The 89-check motion regression still passes
in `particle-motion-r2`, and owned Python/GDScript lint passes.

This is local component rendering evidence, not original-client pixel parity.
The shader uses Godot's color-space/blend pipeline; gamma/blending must still be
compared against original-client reference captures. No hardware/browser/export,
depth-occlusion fixture, large-population performance, flight trajectory, server
combat or multiplayer acceptance is claimed. Next connect the effects to the
original flight definitions and live mob actions, then qualify those paths.
