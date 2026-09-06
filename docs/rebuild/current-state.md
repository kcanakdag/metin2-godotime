# Implemented baseline and evidence limits

Inspected project revision: `d1b3bbdea24240e03e5e325549eb5c4bd01a377b`,
2026-09-06. This planning pass reads current source and existing reports; it
does not rerun or redeploy the game. The full feature catalog deliberately
marks broad systems as partial/planned rather than declaring them complete.

## What exists

| Area | Concrete implementation | Remaining full-game work |
| --- | --- | --- |
| Accounts/entry | Better Auth username/password registration/login, remembered sessions, five-minute JWTs with four-minute refresh, four character slots, selection/entry/leave/logout | Recovery/email/dashboard, all classes/sexes/empires/appearance options, deletion and full profile rules, established-read revocation verification |
| Current character | Male Warrior, Shinsoo, Yongan; stable character identity separate from account and socket | Other classic characters, original stats/progression/skills and appearance/motion catalog |
| Server authority | Finite/range movement, collision, presence, cooldowns, simple combat/death/respawn, gold and item ownership | General action/state/stat/AI/quest/social/economy rules, interest management, multiple maps/instances/channels |
| Items | Two-page 90-cell bag, starter sword and red potions, stacking/placement/equip/use/drop pickup, private account reads, local quickslots | Full prototype/instance model, all equipment slots/bonuses/sockets/time limits, visible equipped weapon, transfer/refine/storage/shop systems |
| Combat | Procedural Stone Sentinel, nearest valid target, basic damage, death/respawn, gold and potion drop | Original mobs and AI, targeting/combo/ranged/magic/skills/affects, XP/level/quests, original formulas and balance |
| World | Yongan's 20 terrain sections, 601 building/prop placements, shared collision bake, streaming packs, atlas/minimap | 368 trees and 6 effects unsupported, general map compiler, path routing/layered floors, spawns/NPCs/portals and remaining world catalog |
| Animation/assets | Pinned warrior: 3 meshes, 75 bones, wait/walk/run/attack clips; selected UI/art conversion | General race/rig/motion/gear/NPC/VFX/SFX pipeline and original-client comparison |
| UI | Original selected entry/taskbar/inventory/minimap/chat/system artwork and working connected slice | Full character/skill/NPC/quest/trade/storage/party/guild/wedding/extension screens and exact text/behavior parity |
| Browser/desktop | Godot standard GDScript, Web Compatibility single-threaded export, hashed core/nearby section loading, Linux export | Memory/cache/context-loss/tab-resume robustness, population profiling, actual current Windows execution and broader browser matrix |
| Operations/tools | Isolated export/probe audits, typed bindings, Python/Godot/Rust/TS checks, local MCP and previews, deployment/backups | General authoring/content compiler, performance lab, admin RBAC/audit console, restore/migration drills and production load targets |

The inspected owned source comprises 70 Python/GDScript/Rust/TypeScript/JS
files under the audited directories before the planning checker was added.
There are 18 SpacetimeDB table declarations and 21 reducer declarations,
including lifecycle/scheduled and legacy test-only entry paths. These counts
describe code structure, not feature completeness. Paths and hashes are recorded
in [project-inventory.json](evidence/project-inventory.json).

## Recorded integration evidence inspected

| Report | Observed contents | What it proves and does not prove |
| --- | --- | --- |
| `.local/accounts/integration-report.json` | `passed: true`, 58 checks, local `mt2-yongan-v2` | Two-account auth→SDK→server integration, ownership/read scope, slots, selected-character movement/lifecycle; headless native, not all original UI |
| `.local/browser-accounts/20260906-193823/report.json` | `passed: true`, 103 checks, loopback, no browser errors | Actual Chrome plus exported Linux account/UI/world lifecycle, including real timed renewal |
| `.local/browser-accounts/20260906-194508/report.json` | `passed: true`, 103 checks, public HTTPS `mt2-accounts-v3`, no browser errors | Public Chrome/Linux path for the implemented slice; not native Windows, a load benchmark or original-client fidelity proof |
| `.local/accounts/public-http-report.json` | Public health/auth/discovery/JWKS/database/manifest response records | Recorded deployment availability and served artifact evidence, not gameplay subscriptions on its own |

These ignored local evidence files contain development results; the tracked
inventory records their existence and hashes without copying account data or
credentials. Their checks were inspected for scope during planning. The current
development release is `20260906T173802450337Z` at the
[public game endpoint](https://kcanakdag.com:8443/). No live availability check
or update is implied by this planning-only document.

## Concrete gaps to prioritize

The `player` table is public and includes persistent/offline name, position and
gold fields. Account roster and inventory use own-account RLS, but that does not
make the whole character private. Gameplay/session expiry is validated; forced
revocation of existing reads at token expiry is not established. Fix and measure
these boundaries before broadening private quest/social/economic state.

`combat::simulate`, inventory enumeration and account/name checks include
whole-table scans. The single-actor prototype does not establish scale. Profile
and add query-appropriate indexes/region scopes as entity counts grow.
The map bake currently chooses the highest applicable walk surface: it does not
support independent bridge/underpass traversal at the same horizontal point.
Click movement slides against obstacles but does not plan a route around them.

Original image pixels are audited; original font metrics, full UI flow and
frame-for-frame animation fidelity are not established. Existing safe defaults
and prototype numbers are not the original game's balance specification.
