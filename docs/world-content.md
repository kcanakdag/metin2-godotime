# World population and development preview

The full goal includes quests; current priority is filling the world, then
completing classes, abilities, maps and the remaining systems through reusable
definitions. Quest implementation follows the world work. This slice adds
authored Wild Dog populations and an offline inspector. General mob-stat/AI
registries and live editing remain upcoming work. Static NPC dialogue now uses
a shared server-validated interaction handler.

## Author mob homes

`content/worlds/*.population.json` contains a map ID, profile ID, revision and
placements with persistent numeric spawn IDs, definition vnums and map-local X/Z
in meters. Yongan selects six Wild Dogs; training retains one. These are authored
development layouts, not original regen-file density.

The build and offline tool share `server/build_population.rs`. The Rust
`world_content` example also runs the actual server terrain/collision code.
Validation rejects unavailable definitions, duplicate/overlapping homes, unknown
fields, invalid numbers, map mismatch and blocked/out-of-bounds positions. Server
initialization validates homes again before inserting the population.

```sh
python3 tools/world_content.py validate \
  --profile content/worlds/yongan.population.json \
  --output .local/world-content/my-validation

python3 tools/world_content.py move \
  --profile content/worlds/yongan.population.json \
  --id 6 --x 706 --z 600 --output .local/world-content/my-draft
```

`add` needs an unused `--id`, `--vnum`, `--x` and `--z`; `remove` needs `--id`.
Edits increment the revision and validate the entire draft. New output directories
contain `population.json` and `report.json`; inputs are never overwritten. Review
the draft before moving it into source control. Builds use the corresponding
default map profile or an absolute `MT2_POPULATION_PROFILE` path. Overrides cannot
accompany fixed combat fixtures.

**Use a new development database for population changes.** This version seeds the
spawn set during initialization and does not migrate existing populations.
Republishing an existing database is not a supported population deployment
workflow. Do not reuse IDs for unrelated spawns, remove persisted IDs or reset a
database to make tests pass. Migration/reconciliation is an upcoming operator
feature. The population layout itself adds no protocol fields. Current NPC interactions
use application protocol 13.

## Convert original stationary NPCs

`content/profiles/yongan-town-npcs.json` selects 23 additional original definitions
at 32 source point placements: merchants, teachers, blacksmith, fishermen and
other stationary townspeople. It is a candidate batch, not an installed population
or working shop system. Use it with the same importer and batch gallery commands
below. The gallery checks every actor and saves `npc-preview-<vnum>.png` for each.
The corrected batch `.local/npcs/yongan-town-r7` contains 190 reachable clips.
Native gallery `.local/npcs/yongan-town-qa-r3/report.json` passes 936 checks,
including all 23 screenshots. The combined candidate catalog at
`.local/npcs/yongan-town-catalog-r2/runtime` adds the existing guard for 24
definitions / 33 placements; it has not replaced the live catalog.
The candidate's `yongan-town-world-r4/report.json` passes 39 real Main/map checks
for activation, chunk reload, guard picking and lifecycle cleanup. Its connection
is simulated; actual exported multiplayer verification is still required.

To exercise a candidate in an isolated copy of the real map scene:

```sh
python3 tools/test_world_npcs.py --npc-package /path/to/candidate/runtime \
  --native --godot /path/to/godot --output .local/npcs/candidate-map-check
```

NPC positions require finite, in-map coordinates and a terrain height, but are
allowed on blocked terrain, matching original `CHARACTER_MANAGER::SpawnMob` for
stationary NPCs. Mob homes and player movement still require walkable positions.
The offline inspector exposes this distinction as `point_policy: "static_npc"`;
its default remains `walkable`. The source fisherman at `(251, 874)` exercises
the distinction. This is an offline authoring policy, not a player permission.

Visual animation duration comes from the original GR2, matching
`CActorInstance::GetMotionDuration`. If an event-free MSA disagrees, the importer
retains `source_msa_duration_us` and uses GR2 timing; Soon's idle is 1.5 seconds
despite its two-second MSA declaration. Event-bearing mismatches still fail.

The shared converter preserves GR2 triangle-group material bindings when replacing
Blender material slots. It supports an optional opacity map when it references
the same texture as the diffuse map; separate opacity images remain unsupported.
Original actor opacity rendering accepts alpha byte values above zero, represented
as a glTF MASK cutoff of half an alpha byte. Materials with and without opacity
remain separate even when sharing an image.

NPC motion registration follows the source's ordered random selection over 0–99:
trailing registrations after the first 100 weight points are unreachable. This
matters for Octavio's duplicate WAIT1 and the guardians' reaction variants. The
source files remain hash-bound; reachable clips keep their original probabilities.
The town profile explicitly records the Battle Bailiff's deferred attack projectile
event. It does not grant combat behavior to the static NPC layer. Unlisted events
still reject compilation; shop transactions and NPC combat remain upcoming work.

```sh
python3 tools/import_npc_content.py \
  --profile content/profiles/yongan-city-guard.json \
  --blender /path/to/blender --output .local/npcs/my-guard
# Add --offline after the selected files have been fetched.
python3 tools/test_npc_content.py --content .local/npcs/my-guard \
  --godot /path/to/godot --native --output .local/npcs/my-guard-check
```

City Guard 20354 uses client revision
`bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7` and server revision
`7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318`. The importer cross-checks NPC type,
names, model/race/motion metadata and map placement. It discovers diffuse textures
and retains both weighted idle variants among all five clips. Originals and
derivatives remain ignored; source references do not change asset rights.

The guard's rigid weapon has no weight stream. Shared `gr2_bindings.py` turns its
single bone binding into unit skin weights, preserving model-space vertices and
the pose/inverse-bind operation in original `EterGrnLib/ModelInstanceUpdate.cpp`.
Ambiguous/partial bindings fail; weighted meshes retain their existing data.
This requires neither per-NPC hand offsets nor a Granny runtime. Forward
orientation is normalized to -Z. Conversion receipts record frozen inputs,
selected source hashes, artifact hashes and completion. Blender checks deformation
and scale preservation; the Godot gallery checks clips, poses, skin and materials.
Review the render too. Background conversion preserves the open Blender scene;
local graphics/audio access may be needed for clean shutdown.

## Install NPCs in the playable map

```sh
python3 tools/build_npc_catalog.py --content .local/npcs/my-guard \
  --population content/worlds/yongan.population.json \
  --output .local/npcs/my-runtime --install
python3 tools/test_world_npcs.py --godot /path/to/godot --native \
  --output .local/npcs/my-runtime-check
```

The build output must be new. Only its `runtime/` directory is installed under
ignored `client/assets/imported/npcs`; conversion receipts and source metadata
stay outside the client. An existing installation is preserved in the new build's
`previous-installed/` directory. Repeat `--content` and `--population` for more
selected definitions/maps. Duplicate actor, vnum, spawn or output IDs fail.

The public catalog contains names, model references, idle weights and stable
placements with server-derived height and map content hash. Source direction zero
means a random octant; the static presentation seeds that octant from the spawn
ID so clients/reconnects agree. Fixed source octants preserve the original
`GetDeltaByDegree` X/Y direction in map X/Z. The label uses original
`colorinfo.py` NPC color `(122, 231, 93)`. The guard has no invented fixed heading.

The compiler reuses the actor texture extractor and lossless/mipmap import policy.
Validation checks model bytes and compares any Godot-extracted texture pixels with
the embedded GLB images, allowing PNG re-encoding but rejecting changed pixels or
undeclared sidecar files. Export staging restores the texture import policy, and
the actual PCK audit checks the catalog identity, textured skins and idle clips.

The Main scene prepares this layer after terrain verification and activates it
when entry succeeds. Missing or outdated Yongan content rejects entry. Actors
exist only over loaded chunks and are removed on chunk unload, character change,
disconnect or map reconfiguration. The layer selects both source-weighted idle
variants and adds a picking-only proxy with no movement collision. Training has
no original NPCs.

Interactions are authored in `content/worlds/yongan.interactions.json`, keyed by
stable spawn ID. The server joins these records to the installed catalog at
build time; `kind: "dialogue"` selects the shared handler. Use plain `body` text;
unknown fields/handlers, duplicate IDs, unresolved spawns and map mismatch fail
compilation. Only linked NPCs can open a server conversation.
The current guard greeting is authored development text; quests and shops remain
deferred. See the [interaction contract](architecture.md#authored-population-boundary)
and [network checks](development.md#npc-interaction-authoring-and-qa).

For actual Web/Linux NPC qualification, build both targets with `--test-probe`
and matching endpoint/database configuration, serve the Web export with the
existing local proxy, then run:

```sh
.local/venv-dev/bin/python tools/test_browser_accounts.py \
  --url http://127.0.0.1:8186 --database <protocol-13-npc-database> \
  --native <linux-test-export>/MT2Spacetime.x86_64 \
  --world-npcs tests/fixtures/yongan-city-guard-route.json \
  --hardware --headless --output .local/npcs/browser-check
```

The read-only test probe exposes NPC position, idle and camera visibility without
new gameplay permissions. The fixture is bound to the current terrain hash; its
149-meter route was checked through the Rust terrain/collision inspector on a
one-meter grid. Both clients traverse it through normal move intents. The scenario
checks rendered NPCs, click-to-approach, private dialogue, Close/Escape, WASD,
removal/reentry/reconnect and the existing account/movement/rejection lifecycle.
It passed 103 checks on the local NPC interaction database. Screenshots establish browser/native appearance; this is not public
internet qualification. Do not add `--session-refresh` for this focused slice.

## Offline development mode

```sh
python3 tools/world_content.py preview \
  --profile content/worlds/yongan.population.json \
  --npc .local/npcs/my-guard --godot /path/to/godot \
  --output .local/world-content/my-preview
# --npc is optional; --smoke runs isolated Xvfb input/render QA.
```

The separate staged Godot project preserves the open editor. Select a spawn to
focus its original animated model and inspect server-derived coordinates.
WASD/Q/E fly, right drag turns, Shift boosts and the wheel changes speed. `U`
shows missing scenery markers; `C` shows terrain attributes. The guard uses
original map-local `(605, 663)`, height `198.515` in the current bake. Its heading
is an inspection pose; original random-octant policy remains in source metadata.

This mode has no server connection, credentials or privileged actions. Scripts
under `tools/` and the staged `.local` project stay outside player exports.
Preview actors idle but do not simulate combat. Installing the main-scene NPC
catalog is a separate step above. Live spawn/teleport controls need separate authorized,
audited reducers; progression permissions do not grant those capabilities.

Yongan still has 368 unsupported SpeedTree placements and six effects. Source
markers are available; an SPT converter and foliage/streaming QA remain needed.
`tools/prepare_foliage.py` now freezes the 14 original SPT definitions and all
368 placements with verified source hashes. See [foliage conversion](foliage.md)
for the original size/rotation policy and the pending offline runtime probe.
Terrain adapters currently support training and Yongan. Additional playable maps
need terrain, streaming metadata and transitions as well as another profile.

## Focused qualification

```sh
python3 tools/test_physical_combat.py --scenario population \
  --server http://127.0.0.1:8186 --game-server http://127.0.0.1:13223 \
  --database <fresh-mt2-p2-database> --godot /path/to/godot \
  --population-profile content/worlds/yongan.population.json \
  --report .local/world-content/two-client.json
```

Two ordinary accounts verify subscribed homes, mutual movement, invalid target
rejection, combat/reward, independent lives, respawn and reconnect without reward
duplication. Scripts parse before accounts are created. The safe return route
currently targets Yongan. Adding a home does not require repeating unrelated
token-refresh or inventory UI scenarios.
