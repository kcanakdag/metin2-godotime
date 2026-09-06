# Coverage findings and decisions before implementation

This ledger distinguishes gaps in our implementation from gaps in the reference
evidence. An open entry is planned investigation with a concrete exit condition;
it is not silently removed from the full-game scope.

## Server/client map crosswalk

[map-crosswalk.json](evidence/map-crosswalk.json) joins the audited server
directory names to client `setting.txt` parent names using case-folded literal
matching. It records 112 server directories, 92 client setting paths and 81
distinct client names. The union has 124 names: **69 on both sides, 43 server-only
and 12 client-only** under this exact filter.

These are not counts of complete or missing playable maps. Server directories
include support/test/event records; client settings include patch copies. Some
names are probable aliases, such as monkey-dungeon spelling variants and
`metin2_map_devilcatacomb` versus `metin2_map_devilscatacomb`. A probable alias
must be verified against map index/atlas paths, settings and actual resources
before merging it. A name on both sides still needs coordinate, collision,
spawn, portal and dependency verification.

The crosswalk prevents “we have all maps” from following merely from possession
of two archives. Each row becomes a content work item: identify canonical ID and
profile, resolve source paths/aliases, compile visual and authoritative outputs,
verify landmarks and routes, validate NPC/mob/quest/portal references, then test
entry/return and streaming in exported clients. Only Yongan has a partial
implemented fixture in this repository.

## Decisions and evidence gates

| ID | Question or missing evidence | Required action and exit condition | Systems / phase |
| --- | --- | --- | --- |
| DEC-01 | Exact classic era/region/balance profile | Pin a coherent client/server/data manifest, enabled features, class/empire set, level/skill/item tables and active quest list. Preserve later official/variant rows even when excluded from first delivery. | SYS-SCOPE / P0 |
| DEC-02 | Cross-source compatibility and missing data tables | Compare shared IDs/enums and definition schemas; identify original SQL-loaded catalogs absent from checked-in data. Obtain a provenance-backed reference or author an explicit replacement, with formula/content deviation recorded. | SYS-DATA / P0–P3 |
| DEC-03 | Map aliases, server-only/client-only records | Resolve all selected crosswalk rows against index/atlas/settings; classify support/test/unused records explicitly. Do not bulk import 112 directories as 112 playable maps. | SYS-WORLD / P0–P4 |
| DEC-04 | Original-client visual/input/animation reference | Build a lawful capture corpus with version, resolution, locale, camera/action timing and selected equipment/skills/screens. Source reading and exact UI image hashes do not prove indistinguishable output. | SYS-QA, SYS-UI, SYS-MOTION / P1 onward |
| DEC-05 | Full GR2/race/motion compatibility | Add representative skeletal/rigid/variant fixtures and motion event readers; report unsupported compression/rig variants. Verify bind pose/deformation, timing and attachments before batch conversion. | SYS-IMPORT, SYS-ACTOR, SYS-MOTION / P1 |
| DEC-06 | SpeedTree and effect/environment formats | Research concrete supported conversion paths; otherwise author explicit substitutes with provenance and visual targets. Cover current 368 unsupported Yongan trees and 6 effects first. | SYS-IMPORT / P1–P4 |
| DEC-07 | Font and original rendering metrics | Select a distributable font/input with documented rights; compare advances/baselines/wrapping/antialiasing against reference. No font bytes were found in the audited archive. | SYS-UI / P1 onward |
| DEC-08 | Quest execution model and API coverage | Inventory all selected scripts/API calls; prototype a bounded persisted event/state/action representation and converter. Evaluate any necessary sandbox separately; all unsupported syntax/APIs stay in a review queue. | SYS-QUEST / P0–P3 |
| DEC-09 | Full public/private reads and revocation | Split persistent private character state from public presence; test malicious subscriptions and established reads after expiry/logout on the pinned runtime. Document measured semantics and mitigation. | SYS-NET, SYS-AUTH / P0 |
| DEC-10 | Population/platform/performance targets | Choose hardware/browser/resolution/network and concurrent player/entity mixes; measure the prototype and representative dense scenes. Set budgets and justify indexes/regions/partitioning from evidence. | SYS-QA, SYS-NET, SYS-WEB / P0 onward |
| DEC-11 | Multilevel movement and legacy sync semantics | Decide layered navigation representation, climb/slope/clearance rules and latency compensation using fixtures. Preserve classic feel while rejecting client-granted positions/hits. | SYS-MOVE / P1–P4 |
| DEC-12 | Channels and cross-database authority | Begin with logical map/channel membership; measure need for multiple databases. If needed, specify a durable handoff and global identity/economy/social authority before implementing transfers. | SYS-WORLD, SYS-NET / P4 onward |
| DEC-13 | Account security and operator model | Define recovery/email/session policy, admin roles, protected fields, audit retention and emergency access. Implement explicit backend checks for every privileged action. | SYS-AUTH, SYS-ADMIN / P0–P3 |
| DEC-14 | Economy/premium/monetization behavior | Pin currency caps, taxes, prices, premium timers/awards and optional billing scope. Keep payment integration separate from classic rules, with idempotent audited grants if enabled. | SYS-ECONOMY, SYS-OPS / P3–P5 |
| DEC-15 | Conditional classic/regional systems | Adjudicate monarch/elections, war betting/castle variants and seasonal quests against the selected profile. Disabled auction and incomplete Speed Server are experiments, not default parity claims. | SYS-EMPIRE, SYS-EVENT, SYS-EXT / P7–P9 |
| DEC-16 | Later official versus custom automation | Keep Lycan, alchemy, pets, sash/aura, mail/offline market, Champion/Yohara and other indexed systems as individual expansion tasks. Auto-Hunt is a rules decision; Switchbot lacks established official evidence in this audit. | SYS-EXT / P9 |
| DEC-17 | Missing modern-reference pages | Merc and Heart of Greed have index evidence but missing dedicated destinations in the inspected wiki. Find publisher announcement/client/data evidence before specifying their full rules; do not fabricate behavior. | SYS-EXT, SYS-INSTANCE / P9 |
| DEC-18 | Backup/migration/recovery targets | Define RPO/RTO and game/auth/key/content coordination; rehearse actual restore/migration with clients on an isolated snapshot. Current backups and command fixtures are not a completed recovery drill. | SYS-OPS / P0–P10 |
| DEC-19 | Final asset distribution profile | Record distribution evidence, authored replacement or exclusion per selected asset/dependency; resolve unknown entries before qualifying production packaging. Source hashes establish provenance, not permission. | SYS-IMPORT, SYS-RELEASE / P1–P10 |

These decisions should become versioned project records as their phases begin.
Routine implementation choices can be resolved within the chosen profile;
player-visible rule changes or missing original inputs need an explicit recorded
decision. Do not block unrelated compiler/fixture work on a later expansion's
unknown rules.
