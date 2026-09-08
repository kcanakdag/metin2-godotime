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
