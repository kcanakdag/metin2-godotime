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
authored dummy. Placement rows also currently accept only that ordinary vnum.

`.local/mobs/yongan-wildlife-r3` resolves five model paths and 69 original motion
registrations offline. Three parser regression tests and Python lint pass. Model
conversion, rendered deformation/attack checks, trusted registry compilation,
per-definition AI/damage/rewards and actual two-client gameplay remain required.
No new mob is live and no original spawn group is replaced by an invented layout.
