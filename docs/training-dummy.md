# Training dummy

The authored straw-and-wood dummy uses ordinary server combat and client targeting.
It stays anchored, never attacks, and grants no XP, gold or item drops. Defeating
it clears target/chain state and creates a new life after its configured respawn
delay. Stale target lives and skill revisions remain invalid. It has no privileged
client damage or reset interface.

`content/profiles/training-dummy.json` configures health, level, defense, supported
weapon resistances, combat sphere, appearance dimensions/colors and placements.
The default has 30,000 HP and a two-second respawn, near the Yongan entry point
at `(662, 580)`. Training Grounds has a separate placement. The Rust builder
validates numeric bounds and IDs, while map initialization validates traversability.
Practice targets share physical damage and area attacks, but bypass reward credit.

Build and install the runtime model with:

```sh
python3 tools/build_training_dummy.py --blender /path/to/blender --install
# Equivalent:
make dummy-build BLENDER=/path/to/blender
```

Validate a customized profile before launching Blender:

```sh
python3 tools/build_training_dummy.py --profile /path/to/dummy.json --check-profile
```

This command checks the profile without creating assets. Both the authoring tool
and server reject unknown fields, duplicate placement IDs within a map, invalid
stats and malformed appearance data. Height supports 0.5–3.5 metres, body radius
0.1–0.8 metres, and each wood/straw/rope/target color has four RGBA channels in
the 0–1 range. Use `--profile` without `--check-profile` to build that variant;
select the same profile for the server as described below. Traversability is
checked separately against the actual map during server initialization.

Blender runs in an isolated background process. The generator does not modify the
open editor. It produces an editable `.blend`, a GLB with wait/impact/defeat clips,
a presentation manifest, provenance receipt and audit. Only the GLB and manifest
are installed under ignored `client/assets/imported/authored/training-dummy/`.
The model is project-authored; it does not contain original Metin2 assets.

Protocol 17 publishes `WorldInfo.training_target_hash`. The client refuses a
different profile hash, and exports check the exact packaged authored manifest,
model loading and declared animations. Rebuild both server and client after a
profile edit. A custom offline profile can be selected using the generator's
`--profile` and the Rust build's `MT2_TRAINING_TARGET_PROFILE` absolute path; both
must select the same data. Profile changes are not client-authorized mutations.

For an isolated visual check:

```sh
python3 tools/test_actors.py --scenario training_dummy --native \
  --authored-package .local/training-dummy --godot /path/to/godot \
  --output .local/training-dummy-actors
```

The focused multiplayer scenario is `tools/test_progression_admin.py training_dummy`.
It uses two existing authenticated QA accounts and the existing authorized level-5
setup. Publish to a separate `mt2-p2-...` database with a 600-HP copy of the profile
for bounded kill/respawn timing. Never reset another database. The scenario uses
subscribed revisions and actual reducer acknowledgements, and checks both clients,
movement, skill/melee damage, no rewards, anchoring, respawn, stale lives and reconnect.
Failed reports are retained beside the sanitized log as `.result.json`.

Current evidence: `.local/p6-class-skills/dummy-actors-r4/report.json` passes 16
native presentation checks; `dummy-live-r4.json` passes 45 actual server checks.
The latter uses `mt2-p2-dummy-qa-r2-20260908` with a 600-HP test profile. The normal
profile is separately generated and audited. The dummy remains installed in the
current local build at `http://127.0.0.1:8186`, using
`mt2-p2-npc-areas-qa-r1-20260908`.
`dummy-browser-r4/report.json` passes 82 actual Chrome/Linux checks against the
final `exports/dummy-web-r3` and `exports/dummy-linux-r3` builds, including
pointer selection, held Space damage and mutual dummy presentation, with no
browser engine errors. Both real exported packs were audited for the matching
manifest and all three clips. Blender MCP was unreachable; Godot tests used isolated processes,
not the connected editor. No Windows or public deployment evidence is claimed.

A fresh native recheck in `.local/p6-class-skills/dummy-actors-current-r1` passes
all 16 checks with the same installed model hash. The rendered straw-and-wood
model, target marker and full-health label were visually inspected.

The profile-validation follow-up rebuilt the asset in background Blender under
`.local/p6-class-skills/dummy-profile-build-r1`, reproducing the installed GLB
hash exactly. `dummy-profile-actors-r1` passes 16 fresh native Godot checks;
the rendered straw target was inspected. Three Python tests and three Rust
tests cover valid custom profiles and malformed input. This follow-up changes
authoring validation only; it does not add playable class skills or constitute
a new multiplayer/export qualification.
