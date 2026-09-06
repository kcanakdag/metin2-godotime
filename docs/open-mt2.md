# Is open-mt2 useful?

**Yes, as a gameplay, data, and test reference.**
[open-mt2](https://github.com/willianmarquess/open-mt2) is a Node.js/TypeScript
Metin2 server emulator. It does not provide a Godot client or a SpacetimeDB module.
The inspected commit is `8d8800d470f0b69221886723eb5877a2ed9d9d8d`.

The 2026-09-06 [expanded implementation audit](rebuild/reference-audit.md)
rechecked this pin against repository HEAD and inspected its handlers, rules,
registries and tests alongside Quantum Core X. It distinguishes concrete code
from unfinished or absent systems: open-mt2 is useful for selected rules and
tests, but does not supply the full party/trade/guild/marriage/dungeon game.
The [full rebuild catalog](rebuild/feature-catalog.md) uses original C++ source
and content inventories to cover those gaps.

| Area | Value to this project |
| --- | --- |
| Gameplay rules | Reference implementations for movement, stats, inventory, mob behavior, damage, and effects |
| Configuration data | Examples of item, mob, map, and animation metadata structures |
| Unit tests | Examples and edge cases to validate equivalent reducer behavior |
| Legacy networking | Useful if original-client compatibility becomes a goal; less relevant to our custom Godot client |
| Animation tool | Combines animation JSON metadata; it does not import GR2 meshes or skeletal clips |

The inspected [battle strategy](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/core/domain/entities/game/player/delegate/battle/PlayerBattleAgainstMobStrategy.ts)
contains damage, resistance, critical-hit, and timed-effect logic. Its direct
dependencies on player/mob objects, event timers, and networking mean this code
cannot simply be dropped into a reducer.
The [animation utility](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/core/domain/util/AnimationUtil.ts)
calculates movement timing from animation duration and displacement.
The [animation generator](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/tools/animation/index.js)
reads JSON files and assembles metadata for server startup.

The README lists many implemented systems and marks combat, quests, and skills
as in progress. These are upstream's status claims, not an end-to-end test by us.
The README also explicitly allows differences from original gameplay.

Recommended use: select a small behavior, understand its inputs and edge cases,
then implement and validate the equivalent SpacetimeDB table/reducer design.
MySQL/Redis persistence, in-memory entity state, connection lifecycle, and Node
timers would need redesigning. A TypeScript SpacetimeDB module would not remove
that architectural work; the current starter uses Rust.

The repository LICENSE is GPL-3.0; `package.json` says ISC. That metadata conflicts,
so do not treat it as an unambiguously ISC library when deciding to copy code.
No open-mt2 code has been copied into this monorepo. The license of an emulator
also does not grant rights to original game assets.
