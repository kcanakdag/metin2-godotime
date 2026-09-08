# Original mob pipeline

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
