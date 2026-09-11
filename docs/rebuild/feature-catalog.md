# Full-game feature and dependency catalog

Generated from [plan.json](plan.json) by `python3 tools/check_rebuild_plan.py --write`.
Edit the JSON source, then regenerate. Validate with `python3 tools/check_rebuild_plan.py`.

This catalog contains **194 records across 41 systems**.
Server requirements, client requirements, reference comparisons and modernization tasks
can describe different parts of the same gameplay system; this is not a count of unique
game mechanics or a percentage-complete estimate.

Project status: decision 9, partial 47, planned 117, reference-only 21.
`partial` means only the documented current slice exists. `complete` requires
scoped acceptance evidence; the checker cannot establish its semantic sufficiency.
`reference-only` records evidence or legacy infrastructure to replace.
`decision` keeps an optional/uncertain source capability visible pending rules-profile
selection. `planned` requires implementation. Upstream implementation status is separate.

The **implementation prerequisites** form an acyclic graph. A feature depends on its
system foundation and any additional listed system/feature. **Behavioral coupling**
preserves the source audit's interactions; it can contain cycles and is not a build order.
System gates apply to every feature in that system together with the feature's detailed
behavior and [work-package checklist](architecture-and-delivery.md#work-packages-and-realistic-planning).
Phase labels identify first delivery/integration; completing a whole family can span
several phases. See [delivery phases](architecture-and-delivery.md#delivery-phases-and-gates).

## System dependencies and acceptance gates

| System | First phase | Implementation prerequisites | Acceptance |
| --- | --- | --- | --- |
| [SYS-SCOPE](#sys-scope): Rules profile and source coverage | P0 | None | Pinned feature/content profile, deliberate deviations and unresolved-source ledger reviewed; every inventoried family accounted for. |
| [SYS-DATA](#sys-data): Versioned definitions and content graph | P0 | [SYS-SCOPE](#sys-scope) | Stable IDs, cross-reference/range validation and client/server compatibility manifest; rejected unknown required records. |
| [SYS-PERSIST](#sys-persist): Persistence, time and migrations | P0 | [SYS-SCOPE](#sys-scope) | Transactional state, clock semantics, checked values and an isolated old-save migration/restore exercise. |
| [SYS-AUTH](#sys-auth): Account and session lifecycle | P0 | [SYS-PERSIST](#sys-persist) | Two real accounts, private reads, denied foreign actions, refresh/logout/reconnect/duplicate-session behavior; revocation limits measured. |
| [SYS-CHAR](#sys-char): Characters, empires and entry | P0 | [SYS-AUTH](#sys-auth), [SYS-DATA](#sys-data) | All selected class/sex/empire/slot/name/delete/appearance paths persist with ownership enforcement and real entry UI. |
| [SYS-NET](#sys-net): Replication and interest management | P0 | [SYS-AUTH](#sys-auth), [SYS-CHAR](#sys-char) | Two independent clients see mutual movement and presence removal; private/hidden state denied; transfer/reconnect readiness measured. |
| [SYS-IMPORT](#sys-import): Asset and metadata compiler | P1 | [SYS-DATA](#sys-data) | Representative format/race fixtures convert reproducibly; source hashes, unresolved records, deformation, rendering and exported dependencies verified. |
| [SYS-ACTOR](#sys-actor): Character, mob and equipment presentation | P1 | [SYS-IMPORT](#sys-import), [SYS-DATA](#sys-data) | Selected rigs/skins/gear/attachments render and deform correctly in Godot, Web and native; definition IDs match authoritative appearance. |
| [SYS-MOTION](#sys-motion): Motion modes, actions and animation events | P1 | [SYS-ACTOR](#sys-actor), [SYS-DATA](#sys-data) | Motion durations, combo/hit windows, root movement, interruptions and VFX/SFX events agree with trusted action definitions. |
| [SYS-UI](#sys-ui): Classic UI, input and localization | P1 | [SYS-IMPORT](#sys-import), [SYS-NET](#sys-net) | Each selected screen renders at reference sizes and handles keyboard/mouse/IME/focus/tooltips; actual input and source comparisons recorded. |
| [SYS-WORLD](#sys-world): Maps, instances membership and transfers | P1 | [SYS-DATA](#sys-data), [SYS-NET](#sys-net) | Two clients traverse matching collision and round-trip between maps; missing assets/interrupted transfer cannot create duplicate presence. |
| [SYS-MOVE](#sys-move): Movement, navigation and camera | P1 | [SYS-WORLD](#sys-world) | Walk/run/rotation/click paths/camera feel; finite/range rejection, seams, blockers, layered paths and latency correction verified. |
| [SYS-ITEM](#sys-item): Item instances, ownership and equipment | P2 | [SYS-CHAR](#sys-char), [SYS-DATA](#sys-data), [SYS-PERSIST](#sys-persist) | All item locations/flags/attributes/lifetimes enforced atomically; no item duplication across full bags, retries, death or reconnect. |
| [SYS-STATS](#sys-stats): Stats, formulas and resources | P2 | [SYS-CHAR](#sys-char), [SYS-ITEM](#sys-item) | Typed formulas with exact order/rounding/caps; base/equipment/affect rebuild agrees after equip, death and reconnect. |
| [SYS-COMBAT](#sys-combat): Targeting, damage and life cycle | P2 | [SYS-MOVE](#sys-move), [SYS-STATS](#sys-stats), [SYS-MOTION](#sys-motion) | Selected melee/ranged/magic/combo/death rules verified by two clients, trusted damage traces and rejected out-of-range or impossible actions. |
| [SYS-AI](#sys-ai): NPC/monster AI and spawn ecology | P2 | [SYS-COMBAT](#sys-combat), [SYS-WORLD](#sys-world) | Archetypes, aggro/group/leash/boss/metin spawning and regeneration produce valid behavior and measured population cost. |
| [SYS-LOOT](#sys-loot): Drops and reward allocation | P2 | [SYS-COMBAT](#sys-combat), [SYS-ITEM](#sys-item) | Drop tables, ownership, party attribution, pickup, expiry and full-bag/concurrent pickup tested; rewards conserved exactly once. |
| [SYS-PROGRESS](#sys-progress): Experience, leveling and training | P2 | [SYS-COMBAT](#sys-combat), [SYS-STATS](#sys-stats) | XP/stat points/level caps/death penalties and progression tables match chosen profile across rewards and reconnect. |
| [SYS-SKILL](#sys-skill): Skills, statuses and auxiliary training | P2 | [SYS-COMBAT](#sys-combat), [SYS-PROGRESS](#sys-progress) | Selected skill schools/ranks/books/reset/affect stacks/immunities/resources/cooldowns and timing verified in PvE/PvP fixtures. |
| [SYS-NPC](#sys-npc): NPC interaction and dialogue | P3 | [SYS-WORLD](#sys-world), [SYS-ACTOR](#sys-actor), [SYS-UI](#sys-ui) | Distance/access/reentrancy validated; dialogue/shops/quest markers use stable targets and recover from walking away or reconnect. |
| [SYS-QUEST](#sys-quest): Quest events, flags, timers and content | P3 | [SYS-NPC](#sys-npc), [SYS-PROGRESS](#sys-progress), [SYS-ITEM](#sys-item) | Supported API/grammar inventory, complete branch/reward scenarios, persisted waits, duplicate-event denial and content-upgrade recovery. |
| [SYS-ECONOMY](#sys-economy): Shops, storage, refining and currencies | P3 | [SYS-ITEM](#sys-item), [SYS-NPC](#sys-npc), [SYS-PERSIST](#sys-persist) | Prices/materials/sockets/attributes/storage ownership and restrictions validated; atomic mutations, overflow/full-bag tests and audit provenance. |
| [SYS-CHAT](#sys-chat): Chat, whispers and moderation | P3 | [SYS-NET](#sys-net), [SYS-UI](#sys-ui) | Audience privacy, blocking/language/filters/rate limits and movement after input verified with real clients. |
| [SYS-SOCIAL](#sys-social): Friends, invitations and consent | P5 | [SYS-CHAT](#sys-chat), [SYS-CHAR](#sys-char) | Invitation/accept/reject/block/logout rules, online/offline lists and unauthorized requests verified. |
| [SYS-TRADE](#sys-trade): Direct exchange and player shops | P5 | [SYS-ECONOMY](#sys-economy), [SYS-SOCIAL](#sys-social) | Offer revisions and reservations; last-item races/full bags/death/logout/retries conserve gold/items and release locks. |
| [SYS-PARTY](#sys-party): Parties and shared rewards | P5 | [SYS-SOCIAL](#sys-social), [SYS-COMBAT](#sys-combat), [SYS-PROGRESS](#sys-progress) | Leader/roles/invites/leave/kick/bonuses/XP/loot distances and disconnecting leader tested with multiple actual members. |
| [SYS-PVP](#sys-pvp): PK, alignment, duels and arenas | P5 | [SYS-COMBAT](#sys-combat), [SYS-SOCIAL](#sys-social) | Safe zones/empire/duel consent/karma/revenge/arena rules and death/drop penalties follow selected profile. |
| [SYS-INSTANCE](#sys-instance): Dungeon and encounter lifecycle | P6 | [SYS-WORLD](#sys-world), [SYS-QUEST](#sys-quest), [SYS-PARTY](#sys-party) | Admission, keys/timers/phases/rejoin/wipe/results/cleanup work through disconnect and restart; no repeated rewards. |
| [SYS-MOUNT](#sys-mount): Horse, mount and companion actors | P6 | [SYS-MOVE](#sys-move), [SYS-MOTION](#sys-motion), [SYS-PROGRESS](#sys-progress) | Ownership/training/feed/stamina/ride restrictions and mounted actions; summon/unsummon/reconnect and rider visuals verified. |
| [SYS-LIFE](#sys-life): Fishing, mining, crafting and polymorph | P6 | [SYS-QUEST](#sys-quest), [SYS-ITEM](#sys-item), [SYS-WORLD](#sys-world) | Tools/bait/ore/recipes/timers/transforms/skill books and rare outcomes use server rules with matching motion/UI. |
| [SYS-GUILD](#sys-guild): Guild organization, land and war | P7 | [SYS-PARTY](#sys-party), [SYS-ECONOMY](#sys-economy), [SYS-PVP](#sys-pvp) | Role matrix, resources/skills/marks/land/buildings/war results and scheduled recovery; multiple groups and adversarial permissions exercised. |
| [SYS-EMPIRE](#sys-empire): Empire politics and conflicts | P7 | [SYS-GUILD](#sys-guild), [SYS-PVP](#sys-pvp), [SYS-QUEST](#sys-quest) | Selected language/privilege/monarch/election/treasury/three-way-war policies, scheduled events and audits verified. |
| [SYS-MARRIAGE](#sys-marriage): Marriage, wedding and divorce | P8 | [SYS-SOCIAL](#sys-social), [SYS-QUEST](#sys-quest), [SYS-ITEM](#sys-item), [SYS-INSTANCE](#sys-instance) | Eligibility, consent, fees/items, guest ceremony, rings/love/bonuses/teleport and all divorce/recovery paths verified with partners and guest. |
| [SYS-EVENT](#sys-event): Seasonal and live events | P6 | [SYS-QUEST](#sys-quest), [SYS-WORLD](#sys-world) | Selected event scripts/rates/rewards/schedules and expiry/restart/duplicate claims validated; operator controls audited. |
| [SYS-EXT](#sys-ext): Later official and fork-specific systems | P9 | [SYS-DATA](#sys-data), [SYS-CHAR](#sys-char), [SYS-ITEM](#sys-item), [SYS-QUEST](#sys-quest) | Every enabled extension has a verified rules profile and its own client/server/content/tests; unresolved or fork-only features stay visible. |
| [SYS-OPS](#sys-ops): Operations and recovery | P0 | [SYS-PERSIST](#sys-persist), [SYS-AUTH](#sys-auth) | Structured metrics, sensitive-data handling, compatibility/deployment gates, backup ownership and coordinated auth/game restore evidence. |
| [SYS-ADMIN](#sys-admin): Admin and support surface | P3 | [SYS-OPS](#sys-ops), [SYS-CHAR](#sys-char) | Backend roles and audited, bounded actions; no unrestricted player command path; sanctions/repair/event retries and permission denial exercised. |
| [SYS-DEV](#sys-dev): Development and authoring tools | P1 | [SYS-DATA](#sys-data), [SYS-IMPORT](#sys-import), [SYS-NET](#sys-net) | CLI and editor views share contracts; reproducible builds/fixtures, visual inspection and actionable missing-data reports without runtime MCP. |
| [SYS-QA](#sys-qa): Scenario, fidelity and performance laboratory | P0 | [SYS-NET](#sys-net) | Two independent accounts plus rendered exports, negative/concurrent/reconnect cases and declared population/platform benchmarks; evidence tied to revisions. |
| [SYS-WEB](#sys-web): Browser delivery and portability | P1 | [SYS-WORLD](#sys-world), [SYS-UI](#sys-ui), [SYS-ACTOR](#sys-actor) | Initial/streamed asset latency, memory/cache limits, input/audio/tab lifecycle, WebGL context loss and intended browser exports exercised. |
| [SYS-RELEASE](#sys-release): Release and compatibility qualification | P10 | [SYS-OPS](#sys-ops), [SYS-QA](#sys-qa), [SYS-WEB](#sys-web) | All profile features/content accepted, performance targets met, restore drill and real supported-platform/internet evidence; clean player packages. |

## SYS-SCOPE

Rules profile and source coverage

### MOD-001

**Rules profiles, parity ledger and intentional differences** — planned; P0.

Scope: modernization.

Classic experience is preserved; era-specific rules and modern conveniences are explicit. Later official and private-server features remain distinguishable.

Implementation prerequisites: [SYS-SCOPE](#sys-scope).

Evidence: [Rules profiles, parity ledger and intentional differences](architecture-and-delivery.md).

### MOD-002

**Feature and content coverage registry** — planned; P0.

Scope: modernization.

Every source subsystem, command, quest namespace, UI module and content category maps to a feature, replaced infrastructure or an unresolved evidence entry.

Implementation prerequisites: [SYS-SCOPE](#sys-scope).

Evidence: [Feature and content coverage registry](architecture-and-delivery.md).


## SYS-DATA

Versioned definitions and content graph

### SRV-053

**Server content import, compilation and validation** — partial; P0.

Scope: required development tooling.

Automate repeatable imports for item/mob proto, names, skills, refine, shops, attributes, drops, groups, fishing, cube, Dragon Soul, map regen/NPC/stone/boss, dungeon files and quests. Emit canonical IDs, hashes, diagnostics, cross-reference checks and diffable manifests; never hand-edit generated outputs.

Implementation prerequisites: [SYS-DATA](#sys-data).

Behavioral coupling: all content feature IDs, shared client/server manifest.

Current project: Map/UI/warrior-specific manifests and baked data only; no universal definition/quest/item compiler.

Evidence: [Set_Proto_Mob_Table / Set_Proto_Item_Table](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/db/src/ProtoReader.cpp); [InitializeMobTable / InitializeItemTable / InitializeShopTable / InitializeSkillTable / InitializeRefineTable](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/db/src/ClientManagerBoot.cpp); [regen_load](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/regen.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### MOD-003

**Stable content IDs, schemas and compatibility versions** — planned; P0.

Scope: modernization.

Separate account/character/entity/item/definition/map/instance/channel IDs; version normalized records, rounding and generated client/server manifests.

Implementation prerequisites: [SYS-DATA](#sys-data).

Evidence: [Stable content IDs, schemas and compatibility versions](architecture-and-delivery.md).

### MOD-015

**Item, shop, drop and recipe data compiler** — planned; P0.

Scope: modernization.

Compile prototypes, flags/limits/sockets/attributes, drop probabilities, item sizes, shop prices, refine/cube recipes and references; report unknown types.

Implementation prerequisites: [SYS-DATA](#sys-data).

Evidence: [Item, shop, drop and recipe data compiler](development-and-admin.md).

### MOD-016

**Skill/formula/status definition compiler** — planned; P0.

Scope: modernization.

Typed bounded formula AST and defined arithmetic order, stat dependencies, stacking/expiry rules, training tables and tooltip/motion links.

Implementation prerequisites: [SYS-DATA](#sys-data).

Evidence: [Skill/formula/status definition compiler](development-and-admin.md).


## SYS-PERSIST

Persistence, time and migrations

### SRV-052

**Persistence, caches, database domains and audit logs** — reference-only; P0.

Scope: historical infrastructure to replace.

Legacy SQL spans account/player/common/log databases, write-behind caches and generated IDs. Model explicit tables, ownership/RLS, transactions, migrations, retention and structured telemetry in SpacetimeDB/services.

Implementation prerequisites: [SYS-PERSIST](#sys-persist).

Behavioral coupling: typed persistent schema, transactions, observability.

Evidence: [CClientManager::InitializeTables](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/db/src/ClientManagerBoot.cpp); [CPlayerTableCache / CItemCache](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/db/src/Cache.cpp); [LogManager](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/log.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### MOD-027

**Bounded durable timers and transactional state machines** — planned; P0.

Scope: modernization.

Persist deadline/generation and validate current state; stale schedules cannot repeat rewards, trades, wedding reservations or instance cleanup.

Implementation prerequisites: [SYS-PERSIST](#sys-persist).

Evidence: [Bounded durable timers and transactional state machines](architecture-and-delivery.md).


## SYS-AUTH

Account and session lifecycle

### SRV-002

**Account authentication and login keys** — partial; P0.

Scope: classic core.

Covers password/login-key paths, duplicate login checks, account/player roster load, and auth-to-game handoff. Rebuild against the existing Better Auth/JWT boundary; do not port Argon2/database query code verbatim.

Implementation prerequisites: [SYS-AUTH](#sys-auth).

Behavioral coupling: account service, [SRV-001](#srv-001).

Current project: [accounts.rs](../../server/src/accounts.rs) and [account_auth.gd](../../client/scripts/net/account_auth.gd); constrained account slice and recorded 58/103 checks in [current state](current-state.md).

Evidence: [CInputAuth::Login](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/input_auth.cpp); [CInputLogin::Login / LoginByKey](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/input_login.cpp); [CClientManager::RESULT_LOGIN](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/db/src/ClientManagerLogin.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### MOD-029

**Sensitive read revocation and account security completion** — planned; P0.

Scope: modernization.

Verify established-read revocation on JWT expiry/logout; recovery/email/device/session controls and sanctions, replacing current documented uncertainty.

Implementation prerequisites: [SYS-AUTH](#sys-auth).

Evidence: [Sensitive read revocation and account security completion](architecture-and-delivery.md).


## SYS-CHAR

Characters, empires and entry

### SRV-003

**Character roster, creation, selection, deletion and save** — partial; P0.

Scope: classic core.

Four-slot roster, empire/job/name validation, appearance, stats, playtime and location. Current project already implements a constrained vertical slice.

Implementation prerequisites: [SYS-CHAR](#sys-char).

Behavioral coupling: [SRV-002](#srv-002), persistent character identity.

Current project: Four slots, male Warrior/Shinsoo only; original entry art and recorded account checks. All-class/delete/full intro parity remains work; see [current state](current-state.md).

Named subfeatures and required behavior:

- **Character name change:** Selected [`change_name.quest`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/change_name.quest) checks marriage, polymorph, guild, party, level, cooldown and name availability, consumes item 71055 and requires relog. Its internal quest name is misspelled `chagne_name`, so runtime parity is unverified; redesign references around stable character IDs.
- **Character sex change:** Selected `item_change_sex.quest` checks level, engagement/marriage, polymorph and cooldown, consumes item 71048 and calls `pc.change_sex`. Decide what happens to equipped items, appearance assets and class restrictions transactionally.
- **Empire change:** Selected [`change_empire.quest`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/change_empire.quest) blocks engagement/marriage, polymorph and guild membership, checks gold/item/cooldown, then calls `pc.change_empire`. Reconcile all empire-keyed character, spawn, language, guild, friend and quest state atomically.

Evidence: [CInputLogin::CharacterCreate / CharacterSelect / CharacterDelete / Entergame](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/input_login.cpp); [QUERY_PLAYER_CREATE / DELETE / SAVE](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/db/src/ClientManagerPlayer.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### CLI-001

**Account, empire, character, loading, and world-entry screens** — partial; P0.

Scope: Client lifecycle from server selection and login through empire choice, four character slots, creation, selection, loading, enter, change character, logout, and disconnect errors.

Preserve classic stage art, anchors, preview poses, sounds, focus, failure retention, and confirmed selection. Automate fixed-resolution screen captures and input traversal; accept only with real create/select/reconnect/logout flows on two isolated accounts.

Implementation prerequisites: [SYS-CHAR](#sys-char).

Behavioral coupling: account authentication, private character roster, session lifecycle, [CLI-028](#cli-028).

Current project: Four slots, male Warrior/Shinsoo only; original entry art and recorded account checks. All-class/delete/full intro parity remains work; see [current state](current-state.md).

Evidence: [MainStream](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/bin/pack/root/networkmodule.py); [CPythonNetworkStream::SetSelectPhase](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/PythonNetworkStreamPhaseSelect.cpp).


## SYS-NET

Replication and interest management

### SRV-001

**Process topology and binary protocol** — reference-only; P0.

Scope: historical infrastructure.

Auth/game processes and a DB daemon exchange packed C++ packets. Preserve behaviors and ordering contracts, but replace this unsafe ABI-coupled topology with typed SpacetimeDB tables/reducers and explicit application versions.

Implementation prerequisites: [SYS-NET](#sys-net).

Behavioral coupling: network transport, schema/version negotiation.

Evidence: [start / idle / heartbeat](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/main.cpp); [HEADER_CG/GC/GG registries](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/packet.h); [HEADER_GD/DG registries](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/common/tables.h); [Detailed source checklist and coverage limits](server-audit.md).

### SRV-004

**Presence, channels, P2P discovery and disconnect** — partial; P0.

Scope: classic core.

Rebuild as explicit connection/session ownership, online presence, map membership, reconnect and deterministic disconnect cleanup; avoid legacy peer-global state.

Implementation prerequisites: [SYS-NET](#sys-net).

Behavioral coupling: [SRV-001](#srv-001), [SRV-002](#srv-002), map membership.

Current project: Single-map account-aware subscriptions and controlling socket, with documented public-player/read-expiry limits; see [current state](current-state.md).

Evidence: [P2P_MANAGER](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/p2p.cpp); [DESC_MANAGER](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/desc_manager.cpp); [CInputP2P::Login / Logout / Relay](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/input_p2p.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### CLI-029

**Typed networking, phases, subscriptions, rejection, and reconnect** — partial; P0.

Scope: Legacy behavior surface spans handshake/login/select/loading/game phases, 82 CG and 128 GC header names, actors/items/social/quest events, ping/time sync, errors and disconnects; rebuild uses SpacetimeDB typed state and reducers.

Use the packet list as a behavior checklist, never a wire-compatibility target. Each slice accepts reducer rejection, confirmed state, permission-filtered subscriptions, remote disconnect removal and lifecycle-appropriate reconnect with two identities.

Implementation prerequisites: [SYS-NET](#sys-net).

Behavioral coupling: versioned SpacetimeDB schema, authenticated sessions, server-owned gameplay state.

Current project: Single-map account-aware subscriptions and controlling socket, with documented public-player/read-expiry limits; see [current state](current-state.md).

Evidence: [typedef BYTE TPacketHeader](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/Packet.h); [CPythonNetworkStream::OnProcess](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/PythonNetworkStream.cpp).

### REF-002

**Interest-managed world and presence** — reference-only; P0.

Scope: both emulators implemented reference.

Both maintain symmetric nearby sets around a spatial index. In SpacetimeDB, bound rows/subscriptions and test unsubscribe/disconnect explicitly.

Implementation prerequisites: [SYS-NET](#sys-net).

Behavioral coupling: [REF-001](#ref-001), entity lifecycle, map partitioning, subscriptions.

Evidence: [Area](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/core/domain/Area.ts); [Map.Update](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/World/Map.cs).

### MOD-023

**Public presence and private character-state separation** — planned; P0.

Scope: modernization.

Replace broad persistent player rows with authorized public presence/appearance and scoped private state; test offline/hidden data exposure.

Implementation prerequisites: [SYS-NET](#sys-net).

Evidence: [Public presence and private character-state separation](architecture-and-delivery.md).

### MOD-024

**Indexed interest management and active-region simulation** — planned; P0.

Scope: modernization.

Measure current full scans, row size/update cost and decoder budget; map/region indexes and subscription readiness; avoid idle-world tick work.

Implementation prerequisites: [SYS-NET](#sys-net).

Evidence: [Indexed interest management and active-region simulation](architecture-and-delivery.md).


## SYS-IMPORT

Asset and metadata compiler

### CLI-022

**Terrain, placement, collision, environment, foliage, and map metadata formats** — partial; P1.

Scope: setting/atlas info, height/tile/splat/attributes/water/shadows, area placements, property CRCs, model attributes, dungeon/portal metadata, environments and SpeedTree foliage.

The project supports a Yongan subset; SPT and broad indoor/portal/environment semantics remain unparsed. Acceptance validates finite/range-safe parsing, dependency closure, transforms, collision/nav agreement, underpasses and isolated map-pack loading.

Implementation prerequisites: [SYS-IMPORT](#sys-import).

Behavioral coupling: pinned source catalog, authoritative collision bake, [CLI-031](#cli-031).

Current project: Existing pinned selected warrior/map/UI conversion and export audits; general category coverage remains work.

Evidence: [CArea::Load](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/GameLib/Area.cpp); [GetMainTree](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/SpeedTreeLib/SpeedTreeForest.h).

### CLI-026

**Effects, particles, mesh animation, lights, trails, and fly objects** — planned; P1.

Scope: MSE particle/mesh/light graphs, MDE frames, animated textures, billboard/blend/color/alpha/depth behavior, screen effects, weapon traces, MSF projectile paths and target effects.

The project has no general MSE/MDE/MSF importer. Compile explicit Godot material/particle resources with bounded emitters and priorities; acceptance uses frame-locked alpha/depth/blend comparisons, lifecycle/leak checks and dense-combat budgets.

Implementation prerequisites: [SYS-IMPORT](#sys-import).

Behavioral coupling: [CLI-023](#cli-023), [CLI-024](#cli-024), [CLI-025](#cli-025), [CLI-031](#cli-031).

Evidence: [CEffectData::LoadScript](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/EffectLib/EffectData.cpp); [CFlyingData::LoadScriptFile](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/GameLib/FlyingData.cpp).

### CLI-027

**Sound events, positional audio, ambient sound, and music** — planned; P1.

Scope: MSS motion sound timing, WAV effects, 2D/3D attenuation, listener updates, duplicate suppression, ambient zones, streamed MP3/BGM, fades and volume controls.

Replace Miles with Godot audio while retaining authored timestamps, falloff, overlap and crossfade. Acceptance records event deltas/mix levels, map transitions, setting persistence and browser autoplay/background recovery.

Implementation prerequisites: [SYS-IMPORT](#sys-import).

Behavioral coupling: [CLI-024](#cli-024), [CLI-021](#cli-021), audio asset compiler, [CLI-031](#cli-031).

Evidence: [CSoundManager::PlaySound3D](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/MilesLib/SoundManager.cpp); [CRaceMotionData::LoadSoundScriptData](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/GameLib/RaceMotionData.cpp).

### CLI-031

**Deterministic asset compiler, cache, validation, preview, and visual comparison** — partial; P1.

Scope: Pinned inventory and pack precedence; dependency graph; safe format readers; content-addressed conversion/cache; map, character, motion, equipment, VFX/SFX and UI builds; previews, reports and release manifests.

Generalize existing fixture importers early. Every output records source blob/SHA-256, reader/tool versions, units/axes, dependencies, unsupported fields and capability status. Acceptance requires offline reproduction, deterministic hashes, missing-reference failure, incremental cache correctness, preview/contact-sheet generation, fixed-camera comparisons and isolated package loading.

Implementation prerequisites: [SYS-IMPORT](#sys-import).

Behavioral coupling: pinned archive access, Blender and Godot version pins, content schemas, release audit.

Current project: Existing pinned selected warrior/map/UI conversion and export audits; general category coverage remains work.

Evidence: [CEterPackManager::RegisterPack](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/EterPack/EterPackManager.cpp); [patch1](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/bin/pack/Index).

### MOD-004

**Safe source readers and dependency resolution** — partial; P1.

Scope: modernization.

Pinned blobs and hashes, archive precedence, safe paths, finite/range/size checks, unknown-field reports; do not execute imported Python/Lua.

Implementation prerequisites: [SYS-IMPORT](#sys-import).

Evidence: [Safe source readers and dependency resolution](development-and-admin.md).

### MOD-005

**Incremental reproducible content builds** — partial; P1.

Scope: modernization.

Content-addressed cache keys include dependency hashes, converter versions, settings and target; deterministic manifests, offline operation, explicit override layers.

Implementation prerequisites: [SYS-IMPORT](#sys-import).

Evidence: [Incremental reproducible content builds](development-and-admin.md).

### MOD-013

**Trees, foliage, effects and environmental conversion** — planned; P1.

Scope: modernization.

Research currently unsupported SpeedTree/effect categories; preserve atmosphere with explicit conversion/substitution provenance and density budgets.

Implementation prerequisites: [SYS-IMPORT](#sys-import).

Evidence: [Trees, foliage, effects and environmental conversion](development-and-admin.md).

### MOD-020

**Effects, trails, projectiles and audio-event compiler** — planned; P1.

Scope: modernization.

Dependency graph and event timing, particle/mesh/billboard layers, blend/depth semantics, bone attachments, ambient/BGM zones and audio mix metadata.

Implementation prerequisites: [SYS-IMPORT](#sys-import).

Evidence: [Effects, trails, projectiles and audio-event compiler](development-and-admin.md).


## SYS-ACTOR

Character, mob and equipment presentation

### CLI-003

**Network actors, presence, names, and interpolation** — partial; P1.

Scope: Create/update/remove players, NPCs, monsters, shops, mounts and observers; appearance, guild/alignment labels, text tails and remote motion presentation.

Automate two-client join/move/appearance/disconnect/reconnect scenarios and dense-town label captures. A local avatar or queried row is insufficient; verify both clients' subscriptions and rendered removal.

Implementation prerequisites: [SYS-ACTOR](#sys-actor).

Behavioral coupling: presence subscriptions, interest management, [CLI-023](#cli-023), [CLI-029](#cli-029).

Current project: One warrior rig/four clips and procedural enemy; no visible weapon attachment, full races or original mob catalog.

Evidence: [CNetworkActorManager](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/NetworkActorManager.cpp); [CPythonNetworkStream::RecvCharacterAppendPacket](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/PythonNetworkStreamPhaseGameActor.cpp).

### CLI-023

**GR2 geometry, rigs, skinning, materials, and race variants** — partial; P1.

Scope: Rigid/deformable GR2 models and animations, bind/rest transforms, skeletons, skin weights, shapes/skins/hair, materials, opacity/specular/two-sided behavior, LOD and runtime instances.

Build skeleton signatures before sharing libraries; enumerate every MSM model/skin/hair dependency and GR2 revision. Acceptance uses male/female/class/monster/NPC fixtures, deformation probes, silhouette/material captures and native/Web exported playback.

Implementation prerequisites: [SYS-ACTOR](#sys-actor).

Behavioral coupling: Carbon/Blender converter, content compiler, [CLI-031](#cli-031).

Current project: One warrior rig/four clips and procedural enemy; no visible weapon attachment, full races or original mob catalog.

Evidence: [CGraphicThing::OnLoad](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/EterGrnLib/Thing.cpp); [CRaceData::LoadRaceData](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/GameLib/RaceDataFile.cpp).

### CLI-025

**Equipment, weapon, hair, effect, and collision attachments** — partial; P1.

Scope: Main/weapon/head/left-weapon/hair parts, bone attachment names, linked skeleton models, weapon traces, item/race collision pieces, smoke and attached effects.

Generate attachment resources per skeleton signature and equipment appearance rule. Acceptance overlays bones/grips/traces/collision for one- and two-hand swords, dual daggers, bow, fan, bell, hair, armour, costume, rider and mount.

Implementation prerequisites: [SYS-ACTOR](#sys-actor).

Behavioral coupling: [CLI-005](#cli-005), [CLI-023](#cli-023), [CLI-024](#cli-024), [CLI-026](#cli-026), [CLI-031](#cli-031).

Current project: One warrior rig/four clips and procedural enemy; no visible weapon attachment, full races or original mob catalog.

Evidence: [CActorInstance::AttachWeapon](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/GameLib/ActorInstanceAttach.cpp); [CActorInstance::AttachEffectByID](https://github.com/NakiuS/Metin2Client/blob/40e2d9fef3bed9fa56a113001ae678efb72e06d3/source/GameLib/ActorInstanceAttach.cpp).

### MOD-007

**General race, skeleton and skin compiler** — partial; P1.

Scope: modernization.

Parse model/race/shape/hair/attachment metadata, normalize binds and weights, use skeleton signatures and representative male/female/class/monster rigs.

Implementation prerequisites: [SYS-ACTOR](#sys-actor).

Evidence: [General race, skeleton and skin compiler](development-and-admin.md).

### MOD-010

**Equipment attachment and appearance resolver** — planned; P1.

Scope: modernization.

Resolve weapon/armour/hair/shape by item and race, generate bone attachment transforms, prevent duplicate root movement, preview grip/clipping.

Implementation prerequisites: [SYS-ACTOR](#sys-actor).

Evidence: [Equipment attachment and appearance resolver](development-and-admin.md).

### MOD-034

**Client scene batching, LOD and animation scheduling** — planned; P1.

Scope: modernization.

Profile instancing/culling/material sharing/skeleton updates, pool effects and prioritize nearby feedback; fidelity error bounds and Web/native comparison.

Implementation prerequisites: [SYS-ACTOR](#sys-actor).

Evidence: [Client scene batching, LOD and animation scheduling](development-and-admin.md).


## SYS-MOTION

Motion modes, actions and animation events

### SRV-058

**Server motion timing and mob skill hit metadata** — planned; P1.

Scope: classic combat-content contract.

Server reads duration/accumulation and event spheres from motion metadata. The automated animation pipeline must produce client clips and server timing/hit contracts from one pinned source, with validation for missing modes/events.

Implementation prerequisites: [SYS-MOTION](#sys-motion).

Behavioral coupling: [SRV-009](#srv-009), [SRV-011](#srv-011), animation import pipeline.

Named subfeatures and required behavior:

- **Combo mastery and attack-chain timing:** Items 50304-50306 train `SKILL_COMBO` with level gates; `CHARACTER::SetSkill` selects the combo index. [`ani.cpp`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/ani.cpp) loads weapon and mounted combo timings. Compile combo order, cancel/link windows and server hit timing with the corresponding animation profile.

Evidence: [CMotionManager / CMotion::LoadMobSkillFromFile](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/motion.cpp); [293 motion metadata directories](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/monster); [character motion metadata](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/pc); [Detailed source checklist and coverage limits](server-audit.md).

### CLI-024

**Motion manifests, timing, combos, root displacement, and events** — partial; P1.

Scope: MSM motion lists and modes, MSA-to-GR2 references, duration/weight, loops, combo input windows, attack data/hit traces, accumulation and effect/sound/projectile/show/hide/warp events.

The tree has 6,393 MSA files. Generate versioned AnimationLibrary/state-machine resources and a server action manifest from one normalized record; never infer timing from filenames. Acceptance diffs duration, loops, event frames, combo windows, displacement and interruptions within declared tolerances.

Implementation prerequisites: [SYS-MOTION](#sys-motion).

Behavioral coupling: [CLI-023](#cli-023), [CLI-026](#cli-026), [CLI-027](#cli-027), server action definitions, [CLI-031](#cli-031).

Current project: Four selected warrior clips; no general motion-mode/event/action compiler.

Evidence: [CRaceMotionData::LoadMotionData](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/GameLib/RaceMotionData.cpp); [CActorInstance::MotionEventProcess](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/GameLib/ActorInstanceMotionEvent.cpp).

### MOD-008

**Batch animation and motion-mode importer** — partial; P1.

Scope: modernization.

Generalize four-clip fixture into enumerated motion sets with duration, loops, source displacement, interpolation/compression tolerances and provenance.

Implementation prerequisites: [SYS-MOTION](#sys-motion).

Evidence: [Batch animation and motion-mode importer](development-and-admin.md).

### MOD-009

**Shared authoritative action and animation-event definitions** — planned; P1.

Scope: modernization.

Normalize combo windows, hit volumes/times, interruptions, movement locks, projectiles, trails/effects/sounds; server validates actions by stable ID.

Implementation prerequisites: [SYS-MOTION](#sys-motion).

Evidence: [Shared authoritative action and animation-event definitions](development-and-admin.md).


## SYS-UI

Classic UI, input and localization

### SRV-050

**Localization, translated names, locale strings and profanity data** — partial; P1.

Scope: content/platform.

15 localized name catalogs plus locale strings/translation Lua. Build normalized localization bundles with key/placeholder validation and UTF-8 policy; do not retain locale-dependent SQL/string assumptions.

Implementation prerequisites: [SYS-UI](#sys-ui).

Behavioral coupling: content build, [SRV-011](#srv-011), [SRV-013](#srv-013), [SRV-022](#srv-022).

Current project: Selected original images and connected intro/HUD/inventory/chat/map/system subset, including a system-menu sign-out whose cleared web session is durable before the login screen returns (browser repro on the served export); no full fonts/screens/state parity.

Named subfeatures and required behavior:

- **Item informer/delete utilities, localized dialogue, quest letters/targets/counters/clocks and test-server notices:** These are supporting player-facing workflows, not generic quest-engine completion. Their UI, localization and authorization must be covered or explicitly excluded.

Evidence: [LocaleService](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/locale_service.cpp); [localized item names](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/conf/item_names_en.txt); [localized server strings](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/locale_string_de.txt); [Detailed source checklist and coverage limits](server-audit.md).

### CLI-006

**Taskbar, gauges, quickslots, mouse modes, and notifications** — partial; P1.

Scope: HP/SP/stamina/EXP gauges, eight visible quickslots and pages, skill cooldown finish, mouse mode, system/community/inventory/character buttons, gift and energy indicators.

Preserve native-pixel composition and classic key bindings with scalable viewport policy. Screenshot-diff gauge frames and button states; automate quickslot binding/activation/page persistence and server-confirmed effects.

Implementation prerequisites: [SYS-UI](#sys-ui), [SYS-SKILL](#sys-skill), [SYS-PROGRESS](#sys-progress).

Behavioral coupling: character points, skills, authoritative inventory, [CLI-028](#cli-028).

Current project: Selected original images and connected intro/HUD/inventory/chat/map/system subset; no full fonts/screens/state parity.

Evidence: [TaskBar](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/bin/pack/root/uitaskbar.py); [window](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/bin/pack/locale_en/locale/en/ui/taskbar.py).

### CLI-007

**Inventory, equipment, drag/drop, and tooltips** — partial; P1.

Scope: Two bag pages, equipment, item carry/drag/drop, right-click actions, money pickup/drop prompts, sockets, attributes, restrictions and rich item/skill tooltips.

Generate slot geometry and tooltip inputs from definitions while retaining classic order, colors and delays. Acceptance exhausts pointer/focus states and waits for authoritative confirmation before changing items or counts.

Implementation prerequisites: [SYS-UI](#sys-ui), [SYS-ITEM](#sys-item).

Behavioral coupling: [CLI-005](#cli-005), [CLI-006](#cli-006), [CLI-014](#cli-014), [CLI-019](#cli-019), [CLI-028](#cli-028).

Current project: Selected original images and connected intro/HUD/inventory/chat/map/system subset; no full fonts/screens/state parity.

Evidence: [InventoryWindow](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/bin/pack/root/uiinventory.py); [ItemToolTip](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/bin/pack/root/uitooltip.py).

### CLI-010

**Character status, skills, emotions, affects, and quest list** — planned; P1.

Scope: Status/attribute points, skill groups and grades, skill slots, emotion actions, active affects, alignment, character detail and timed quest list.

Treat source enums and layouts as available capability, not live completeness. Acceptance checks formula-driven values, upgrade rejection, cooldown/affect transitions and classic tabs at fixed resolutions.

Implementation prerequisites: [SYS-UI](#sys-ui), [SYS-SKILL](#sys-skill), [SYS-QUEST](#sys-quest), [SYS-PVP](#sys-pvp).

Behavioral coupling: progression definitions, skills/affects, quests, [CLI-006](#cli-006), [CLI-024](#cli-024), [CLI-028](#cli-028).

Evidence: [CharacterWindow](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/bin/pack/root/uicharacter.py); [CPythonPlayer](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/PythonPlayerSkill.cpp).

### CLI-020

**Options, help, music selection, system menu, and web surface** — partial; P1.

Scope: Display/audio/input and gameplay options, block/PvP controls, help, restart/change/logout/quit, music selection and legacy embedded web/mall window.

Use Godot-native settings and a deliberate safe browser policy. Acceptance checks persistence per profile, live option effects, focus restoration, restart states, and excludes legacy COM/browser code from exports.

Implementation prerequisites: [SYS-UI](#sys-ui).

Behavioral coupling: settings persistence, audio, account lifecycle, safe external navigation, [CLI-028](#cli-028).

Current project: Selected original images and connected intro/HUD/inventory/chat/map/system subset; no full fonts/screens/state parity.

Evidence: [OptionDialog](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/bin/pack/root/uisystemoption.py); [WebBrowser_Show](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/CWebBrowser/CWebBrowser.c).

### CLI-028

**Classic UI runtime, layouts, atlases, localization, fonts, and IME** — partial; P1.

Scope: Python window/widget semantics, stacking/focus/picking, layout dictionaries, SUB crops, DDS/TGA/JPG artwork, animation/button states, 15 locale packs, text tags, wrapping and IME.

Inventory enumerates 74 root, 79 UIScript and 18 English Python modules; these overlap controllers, layouts and phase glue. Do not execute legacy Python. Generate Godot scenes/resources and a reference gallery; accept pixel/geometry/focus/IME checks at fixed classic and modern resolutions. The archive names Tahoma but contains no redistributable font bytes.

Implementation prerequisites: [SYS-UI](#sys-ui).

Behavioral coupling: UI asset compiler, localization definitions, licensed font input, [CLI-031](#cli-031).

Current project: Selected original images and connected intro/HUD/inventory/chat/map/system subset; no full fonts/screens/state parity.

Evidence: [PythonScriptLoader](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/bin/pack/root/ui.py); [CGraphicSubImage::OnLoad](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/EterLib/GrpSubImage.cpp).

### MOD-021

**UI atlas, localization and font-metric tooling** — partial; P1.

Scope: modernization.

Keep source pixels while validating locale keys/placeholders/wrapping; layout references, font rights/metrics and missing translations.

Implementation prerequisites: [SYS-UI](#sys-ui).

Evidence: [UI atlas, localization and font-metric tooling](development-and-admin.md).


## SYS-WORLD

Maps, instances membership and transfers

### SRV-005

**Maps, sectrees, attributes, portals and warp locations** — partial; P1.

Scope: classic core + content.

112 map directories are present, but directory presence is not proof of complete visual/server content. Compile map coordinates, server_attr, towns, portals and allowed-map policy into versioned authoritative data.

Implementation prerequisites: [SYS-WORLD](#sys-world).

Behavioral coupling: content compiler, authoritative collision.

Current project: Yongan/20 sections, shared bake, map panels and browser section packs; other maps, portals, foliage/effects and layered traversal remain work.

Evidence: [SECTREE_MANAGER::Build / LoadSettingFile / LoadMapRegion](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/sectree_manager.cpp); [CMapLocation](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/map_location.cpp); [map index catalog](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/map/index); [Detailed source checklist and coverage limits](server-audit.md).

### CLI-009

**Minimap, atlas, map names, and target markers** — partial; P1.

Scope: Zoomable local minimap, native-size atlas, player/NPC/warp/quest/target markers, tooltips, coordinates and map-name transitions.

Compile minimap/atlas transforms and marker catalogs per map. Acceptance overlays known coordinates and edges at every zoom, validates axes/bounds, and never invents unsubscribed markers.

Implementation prerequisites: [SYS-WORLD](#sys-world).

Behavioral coupling: world/map definitions, presence and quest subscriptions, [CLI-021](#cli-021), [CLI-028](#cli-028).

Current project: Yongan/20 sections, shared bake, map panels and browser section packs; other maps, portals, foliage/effects and layered traversal remain work.

Evidence: [CPythonMiniMap](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/PythonMiniMap.cpp); [MiniMap](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/bin/pack/root/uiminimap.py).

### CLI-021

**Outdoor, indoor, dungeon, portal, and streamed map rendering** — partial; P1.

Scope: Map selection/loading, terrain patches/quadtree, area objects, indoor dungeon blocks, portals, water, shadows, sky, lens flare, weather and streamed visibility.

Inventory finds 92 setting.txt paths, including patch/duplicate variants. Batch import by explicit map profile and pack precedence; acceptance checks seams, landmarks, visibility, portals, water and classic atmosphere in deterministic camera captures.

Implementation prerequisites: [SYS-WORLD](#sys-world).

Behavioral coupling: content compiler, map definitions, [CLI-022](#cli-022), [CLI-026](#cli-026).

Current project: Yongan/20 sections, shared bake, map panels and browser section packs; other maps, portals, foliage/effects and layered traversal remain work.

Evidence: [CMapManager](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/GameLib/MapManager.cpp); [CMapOutdoor::Load](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/GameLib/MapOutdoorLoad.cpp).

### MOD-012

**General map, collision and layered-navigation compiler** — partial; P1.

Scope: modernization.

Extend Yongan shared bake to all selected maps, independent stacked walk levels, portals/towns/spawns and reachability; check seams/units/pivots.

Implementation prerequisites: [SYS-WORLD](#sys-world).

Evidence: [General map, collision and layered-navigation compiler](development-and-admin.md).

### MOD-026

**Map/channel transfer and handoff recovery** — planned; P1.

Scope: modernization.

Exactly one authoritative character location; validated load/entry handshake and cancellation; measured cross-database need before distributed transfer.

Implementation prerequisites: [SYS-WORLD](#sys-world).

Evidence: [Map/channel transfer and handoff recovery](architecture-and-delivery.md).


## SYS-MOVE

Movement, navigation and camera

### SRV-006

**Movement, synchronization and validated warps** — partial; P1.

Scope: classic core.

Preserve walk/run pace, rotation and warp semantics while keeping server authority. Replace client-supplied position trust and ad-hoc sync checks with bounded intent validation, sequences and correction.

Implementation prerequisites: [SYS-MOVE](#sys-move).

Behavioral coupling: [SRV-004](#srv-004), [SRV-005](#srv-005).

Current project: [movement.rs](../../server/src/movement.rs), [orbit_camera.gd](../../client/scripts/camera/orbit_camera.gd): authoritative straight-line/slide movement; no routed navigation or prediction.

Named subfeatures and required behavior:

- **Return, memory and destination warp items:** `USE_TALISMAN` handles return-to-town and saved-location items with dungeon/health/cooldown restrictions. Selected [`ring_warp.quest`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/ring_warp.quest) adds an item with destination menu, charge count and cooldown. Warp validation and charge consumption must be one recoverable transition.
- **NPC/map warp services:** Selected `map_warp.quest`, `neutral_warp.quest` and `goto_empire_castle.quest` provide destination/empire transport separately from warp items. Compile destinations against the map profile, bounds, access rules and fees.

Evidence: [CInputMain::Move / SyncPosition / Warp](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/input_main.cpp); [CHARACTER state machine](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_state.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### CLI-002

**Classic movement, smart mouse control, picking, and camera** — partial; P1.

Scope: WASD/arrows, click-to-move, smart click interaction/attack, auto attack, target and item picking, orbit/zoom/pitch, cursor modes, and input ownership.

Keep acceleration, turn response, camera constraints and click priority observationally faithful while using validated intents. Acceptance includes obstacle sliding, UI/chat focus isolation, item/actor/ground click precedence and latency/correction scenarios.

Implementation prerequisites: [SYS-MOVE](#sys-move).

Behavioral coupling: authoritative movement, world collision, [CLI-021](#cli-021), [CLI-029](#cli-029).

Current project: [movement.rs](../../server/src/movement.rs), [orbit_camera.gd](../../client/scripts/camera/orbit_camera.gd): authoritative straight-line/slide movement; no routed navigation or prediction.

Evidence: [CPythonPlayer::NEW_SetMouseSmartState](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/PythonPlayerInputMouse.cpp); [__BuildKeyDict](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/bin/pack/root/game.py).

### REF-001

**Authoritative movement and correction** — reference-only; P1.

Scope: open-mt2 implemented reference.

Port the intent validation and reject/resync contract to reducers; do not port TCP packet timing literally.

Implementation prerequisites: [SYS-MOVE](#sys-move).

Behavioral coupling: authoritative identity, map collision/attributes, movement speed, client correction event.

Evidence: [CharacterMoveService.execute](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/game/app/service/CharacterMoveService.ts); [Player.isMoveAllowed](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/core/domain/entities/game/player/Player.ts); [Player anti-teleport rate check](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/test/unit/core/domain/entities/game/player/PlayerMoveRate.test.ts).

### MOD-025

**Sequenced input, prediction and reconciliation** — planned; P1.

Scope: modernization.

Optional bounded local prediction with acknowledgements/correction, authoritative path/rate validation, delay/jitter tests and classic pacing.

Implementation prerequisites: [SYS-MOVE](#sys-move).

Evidence: [Sequenced input, prediction and reconciliation](architecture-and-delivery.md).


## SYS-ITEM

Item instances, ownership and equipment

### SRV-013

**Item instances, inventory and item-use dispatch** — partial; P2.

Scope: classic core.

Instance IDs, stacks, sockets, attributes, ownership, inventory windows/cells and item subtype behavior. Every mutation should be one authoritative transaction.

Implementation prerequisites: [SYS-ITEM](#sys-item).

Behavioral coupling: [SRV-003](#srv-003), item definitions, transaction boundary.

Current project: [inventory.rs](../../server/src/inventory.rs): sword/potions and simple bag/equip/use/drop; no complete item attribute/type/slot model.

Named subfeatures and required behavior:

- **Equip/unequip families:** `CHARACTER::UseItemEx` dispatches weapon, armour, costume, rod, pick, ring, belt, unique and special Dragon Soul equipment, while normal Dragon Soul placement uses item movement. Validate job/sex/level/anti-flags, wear-slot conflicts, polymorph, exchange locks, expiry and derived affects.
- **Recovery, ability, cleansing and invisibility consumables:** Live `ITEM_USE` branches cover delayed, immediate and continuous HP/SP recovery, ability buffs, direct affects, bad-affect clearing and invisibility. Arena/dungeon/war limits and use/consumption ordering are part of the rules.
- **Refinement scrolls, Metin stones, sockets and attributes:** Live branches cover tuning/detachment, socket cleaning, normal/rare attribute add/change, accessory socket creation/insertion, belt sockets and Metin insertion. Keep target validation, probability, failure result, item consumption and logs transactional; source enum coverage alone does not select every scroll variant.
- **Return, memory and destination warp items:** `USE_TALISMAN` handles return-to-town and saved-location items with dungeon/health/cooldown restrictions. Selected [`ring_warp.quest`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/ring_warp.quest) adds an item with destination menu, charge count and cooldown. Warp validation and charge consumption must be one recoverable transition.
- **Gift boxes, keyed treasure boxes and special-item groups:** `ITEM_GIFTBOX` and `ITEM_TREASURE_KEY` resolve `CSpecialItemGroup` results including item, gold, EXP, mob/group and negative effects. Reward roll, capacity, consumption and spawned outcomes must commit exactly once; direct use of `ITEM_TREASURE_BOX` returns false.
- **Quest and signal-use items:** `ITEM_QUEST` routes through `CQuestManager::UseItem` or `SIGUse` according to flags/group IDs; many selected quests also bind exact item-vnum `use`. Content compilation must reconcile both dispatch routes and reject duplicate reward/consumption paths.
- **Defined but non-executing item categories:** `ITEM_AUTOUSE`, `ITEM_MATERIAL`, `ITEM_SPECIAL`, `ITEM_TOOL` and `ITEM_LOTTERY` reach an empty `UseItemEx` branch at this pin; `USE_MOVE`, `USE_TREASURE_BOX` and `USE_MONEYBAG` also do no direct work there. Keep them in compatibility/import reports, but do not claim live standalone features without another handler or selected quest.
- **Item informer/delete utilities, localized dialogue, quest letters/targets/counters/clocks and test-server notices:** These are supporting player-facing workflows, not generic quest-engine completion. Their UI, localization and authorization must be covered or explicitly excluded.

Evidence: [CItem](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/item.cpp); [ITEM_MANAGER](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/item_manager.cpp); [CHARACTER::UseItem / MoveItem / DropItem](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_item.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### SRV-014

**Equipment, wear slots and quickslots** — partial; P2.

Scope: classic core.

Equipment validation and visual parts, two-handed conflicts, quickslot add/delete/swap and persistence.

Implementation prerequisites: [SYS-ITEM](#sys-item), [SYS-STATS](#sys-stats), [SYS-ACTOR](#sys-actor), [SYS-UI](#sys-ui).

Behavioral coupling: [SRV-013](#srv-013), [SRV-007](#srv-007).

Current project: [inventory.rs](../../server/src/inventory.rs): sword/potions and simple bag/equip/use/drop; no complete item attribute/type/slot model.

Named subfeatures and required behavior:

- **Equip/unequip families:** `CHARACTER::UseItemEx` dispatches weapon, armour, costume, rod, pick, ring, belt, unique and special Dragon Soul equipment, while normal Dragon Soul placement uses item movement. Validate job/sex/level/anti-flags, wear-slot conflicts, polymorph, exchange locks, expiry and derived affects.

Evidence: [CHARACTER::EquipItem / UnequipItem](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_item.cpp); [CHARACTER quickslot operations](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_quickslot.cpp); [EWearPositions / EWindows](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/common/length.h); [Detailed source checklist and coverage limits](server-audit.md).

### CLI-005

**Items, equipment, drops, and appearance resolution** — partial; P2.

Scope: Item definitions, bag placement, stack/count/socket/attribute display, ground drops and ownership, use/drop/move, equipment slots and visible appearance.

Compile item prototypes and visual/icon dependencies into versioned records. Acceptance covers every slot/race/sex restriction, multi-cell placement, stack bounds, confirmed mutations, drop ownership/expiry and equipment silhouette.

Implementation prerequisites: [SYS-ITEM](#sys-item), [SYS-ACTOR](#sys-actor).

Behavioral coupling: authoritative inventory, item definitions, [CLI-007](#cli-007), [CLI-025](#cli-025), [CLI-029](#cli-029).

Current project: [inventory.rs](../../server/src/inventory.rs): sword/potions and simple bag/equip/use/drop; no complete item attribute/type/slot model.

Evidence: [CPythonNetworkStream::RecvItemSetPacket2](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/PythonNetworkStreamPhaseGameItem.cpp); [CItemData](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/GameLib/ItemData.h).

### REF-006

**Inventory, equipment and item use** — reference-only; P2.

Scope: classic core implemented; modern windows partial.

Use stable item instance IDs and atomic moves. Costume slots are supported; Dragon Soul and belt constants in open-mt2 are not full workflows.

Implementation prerequisites: [SYS-ITEM](#sys-item).

Behavioral coupling: item instances, item proto, slot/window schema, persistence, derived stats.

Evidence: [Inventory](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/core/domain/entities/game/inventory/Inventory.ts); [UseItemService.execute](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/game/app/service/UseItemService.ts); [Inventory](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/PlayerUtils/Inventory.cs); [Equipment.IsSuitable](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/PlayerUtils/Equipment.cs).

### MOD-028

**Atomic item/currency reservations and provenance** — planned; P2.

Scope: modernization.

Common ownership/location/version/lock operations shared by trade/shop/storage/refine/quests/admin; conservation and retry safety, checked integers.

Implementation prerequisites: [SYS-ITEM](#sys-item).

Evidence: [Atomic item/currency reservations and provenance](architecture-and-delivery.md).


## SYS-STATS

Stats, formulas and resources


## SYS-COMBAT

Targeting, damage and life cycle

### SRV-009

**Combat, targeting, damage, death and respawn** — partial; P2.

Scope: classic core.

Authoritative hit/range/timing, physical and magical formulas, defense/resists, critical/piercing, death, penalties, respawn and rewards. Do not infer truth from animation timing.

Implementation prerequisites: [SYS-COMBAT](#sys-combat).

Behavioral coupling: [SRV-006](#srv-006), [SRV-007](#srv-007), [SRV-008](#srv-008), [SRV-010](#srv-010), [SRV-011](#srv-011).

Current project: [combat.rs](../../server/src/combat.rs): one procedural enemy and simplified attacks/death/respawn; original combat formulas and content absent.

Named subfeatures and required behavior:

- **Combo mastery and attack-chain timing:** Items 50304-50306 train `SKILL_COMBO` with level gates; `CHARACTER::SetSkill` selects the combo index. [`ani.cpp`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/ani.cpp) loads weapon and mounted combo timings. Compile combo order, cancel/link windows and server hit timing with the corresponding animation profile.
- **Dead state, delayed restart and forced town return:** `dead_event`, `CHARACTER::Dead` and [`do_restart`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/cmd_general.cpp) implement a timed dead phase plus `restart_here` and `restart_town`. Model these as server states; validate late/duplicate requests and reconnect while dead.
- **Context-specific revive:** `do_restart` has separate ordinary-map, guild-war, dungeon, Three-Way War and Sungzi/token paths, with different positions and HP/SP restoration. `ReviveInvisible(5)` supplies temporary post-revive protection on applicable paths. Preserve the selected rules instead of using a universal respawn.
- **EXP death penalty and protections:** `CHARACTER::DeathPenalty` exempts levels below 10, has a luck branch, consumes `AFFECT_NO_DEATH_PENALTY` on applicable here-revives, caps loss, halves it for a unique item and makes the shown town-revive loss zero. Pin the regional table and exact eligibility before implementing.
- **Alignment-based inventory/equipment drops:** [`CHARACTER::ItemDropPenalty`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_battle.cpp) selects inventory/equipment probabilities and quantities by alignment band, respects anti-drop flags/protection item, and excludes low levels, shops and battle arena. It is invoked for eligible non-duel/non-war/non-event player deaths. Item removal, ownership and ground-drop placement must be atomic.

Evidence: [CHARACTER::Damage / Dead / DistributeExp](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_battle.cpp); [battle_melee_attack](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/battle.cpp); [CInputMain::Attack / UseSkill](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/input_main.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### CLI-004

**Combat, PvP, skills, affects, and projectiles** — partial; P2.

Scope: Targeting, normal/combo attacks, hit reactions, damage numbers, death/stand-up, skills and cooldowns, affects, duels/PvP, fly targets and projectile creation.

Client events schedule presentation only; the server validates target, range, state, resource cost, cooldown and damage. Acceptance replays authoritative action IDs against motion hit windows, interruptions, correction, PvE/PvP and exported-client timing.

Implementation prerequisites: [SYS-COMBAT](#sys-combat), [SYS-SKILL](#sys-skill), [SYS-PVP](#sys-pvp).

Behavioral coupling: server combat rules, skill and affect definitions, [CLI-024](#cli-024), [CLI-026](#cli-026), [CLI-029](#cli-029).

Current project: [combat.rs](../../server/src/combat.rs): one procedural enemy and simplified attacks/death/respawn; original combat formulas and content absent.

Evidence: [CPythonNetworkStream::SendAttackPacket](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/PythonNetworkStreamPhaseGame.cpp); [CActorInstance](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/GameLib/ActorInstanceBattle.cpp).

### REF-004

**Combat and damage pipeline** — reference-only; P2.

Scope: partial reference in both emulators.

open-mt2 is the stronger rules/test reference. QCX explicitly lacks magic attack, range validation and several bonus/resist stages.

Implementation prerequisites: [SYS-COMBAT](#sys-combat).

Behavioral coupling: [REF-001](#ref-001), [REF-003](#ref-003), stats, equipment, skills, effects, RNG.

Evidence: [PlayerBattleAgainstMobStrategy](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/core/domain/entities/game/player/delegate/battle/PlayerBattleAgainstMobStrategy.ts); [PlayerBattleAgainstMobStrategy tests](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/test/unit/core/domain/entities/game/player/delegate/battle/PlayerBattleAgainstMobStrategy.test.ts); [Entity.Attack/Damage](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/World/Entities/Entity.cs).


## SYS-AI

NPC/monster AI and spawn ecology

### SRV-011

**Mob definitions, AI, groups and spawn regeneration** — partial; P2.

Scope: classic core + content.

Includes NPC/monster/metin types, aggression, rank, AI flags, movement/combat states, group/group-group spawning and timed regen. Validate every vnum, map, radius, count and interval.

Implementation prerequisites: [SYS-AI](#sys-ai).

Behavioral coupling: [SRV-005](#srv-005), mob definitions, spawn compiler.

Current project: One procedural Stone Sentinel pursuit/attack fixture; no original mob/group/spawn catalog.

Evidence: [CMobManager::Initialize / LoadGroup / LoadGroupGroup](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/mob_manager.cpp); [monster state machine](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_state.cpp); [regen_load / regen_do](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/regen.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### REF-003

**Monster and Metin spawn/behavior** — reference-only; P2.

Scope: both emulators implemented with incomplete edge behavior.

Use durable spawn identity and scheduled respawn; keep classic idle/chase/attack cadence data-driven.

Implementation prerequisites: [SYS-AI](#sys-ai).

Behavioral coupling: [REF-002](#ref-002), mob proto, spawn groups, animation timing, authoritative scheduler.

Evidence: [SpawnManager](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/core/domain/manager/SpawnManager.ts); [SimpleBehaviour](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/World/AI/SimpleBehaviour.cs); [StoneBehaviour](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/World/AI/StoneBehaviour.cs).

### MOD-019

**Mob, group and spawn catalog compiler** — planned; P2.

Scope: modernization.

Compile prototype/rank/AI/resist data, groups/group-groups/regen, collision-compatible positions and bounded population schedules.

Implementation prerequisites: [SYS-AI](#sys-ai).

Evidence: [Mob, group and spawn catalog compiler](development-and-admin.md).


## SYS-LOOT

Drops and reward allocation

### SRV-012

**Drop tables, ground items and loot ownership** — partial; P2.

Scope: classic core + content.

Common, mob, etc, group and special-item drops; ownership reservation, pickup range, expiration and anti-duplication. Source catalogs require referential/probability validation.

Implementation prerequisites: [SYS-LOOT](#sys-loot).

Behavioral coupling: [SRV-009](#srv-009), [SRV-011](#srv-011), [SRV-013](#srv-013), economy policy.

Current project: Compiled pinned drop catalog (revision 7ee9c84: 1220 common rows, 10 groups, 10 selected mobs) rolled server-side on kill with the original level-delta tables and rare-bonus draw order; excluded rows recorded per reason. 329-vnum/33-model ground catalog including mandatory Yang, and a 52-check two-export field run (equip, kill, death on both clients, original ground models) with 132 focused Python and 9 Rust tests. Alignment drops, party allocation, the item-drop death penalty and gift/treasure boxes remain open.

Named subfeatures and required behavior:

- **Alignment-based inventory/equipment drops:** [`CHARACTER::ItemDropPenalty`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_battle.cpp) selects inventory/equipment probabilities and quantities by alignment band, respects anti-drop flags/protection item, and excludes low levels, shops and battle arena. It is invoked for eligible non-duel/non-war/non-event player deaths. Item removal, ownership and ground-drop placement must be atomic.
- **Gift boxes, keyed treasure boxes and special-item groups:** `ITEM_GIFTBOX` and `ITEM_TREASURE_KEY` resolve `CSpecialItemGroup` results including item, gold, EXP, mob/group and negative effects. Reward roll, capacity, consumption and spawned outcomes must commit exactly once; direct use of `ITEM_TREASURE_BOX` returns false.

Evidence: [ITEM_MANAGER::CreateDropItem](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/item_manager.cpp); [CHARACTER::PickupItem](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_item.cpp); [mob drop catalog](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/mob_drop_item.txt); [Detailed source checklist and coverage limits](server-audit.md).

### REF-007

**Drops, ownership and pickup** — reference-only; P2.

Scope: partial reference in both emulators.

Premium, party, guild and marriage modifiers remain incomplete.

Implementation prerequisites: [SYS-LOOT](#sys-loot).

Behavioral coupling: [REF-003](#ref-003), [REF-004](#ref-004), [REF-006](#ref-006), loot tables, ownership expiry, RNG.

Evidence: [DropManager](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/core/domain/manager/DropManager.ts); [DroppedItem ownership expiry](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/test/unit/core/domain/entities/game/item/DroppedItem.test.ts); [DropProvider](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/Services/DropProvider.cs).


## SYS-PROGRESS

Experience, leveling and training

### SRV-007

**Stats, experience, levels, alignment and progression** — planned; P2.

Scope: classic core.

Includes stat points, experience distribution, level-up, alignment/karma, playtime and level rewards. Balance must be pinned to a chosen release/content profile.

Implementation prerequisites: [SYS-PROGRESS](#sys-progress).

Behavioral coupling: [SRV-003](#srv-003), [SRV-009](#srv-009).

Named subfeatures and required behavior:

- **Class skill-tree choice and skill-point advancement:** Selected [`skill_group.quest`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/skill_group.quest) chooses one of two groups for each of the four jobs; `CHARACTER::SetSkillGroup`, `SkillLevelUp` and the player `skillup` command apply it. Preserve teacher/level gates, point costs, active/passive distinctions and skill-group state.
- **Stat, skill-group and single-skill reset:** Selected `reset_status.quest` and `skill_reset2.quest` call `pc.reset_status`, `pc.clear_skill` and `pc.set_skill_group`; `ITEM_SKILLFORGET` lowers one skill. `reset_scroll.quest` is present but not selected. Treat NPC, item, level/cost/cooldown variants as distinct flows rather than one generic respec.
- **EXP death penalty and protections:** `CHARACTER::DeathPenalty` exempts levels below 10, has a luck branch, consumes `AFFECT_NO_DEATH_PENALTY` on applicable here-revives, caps loss, halves it for a unique item and makes the shown town-revive loss zero. Pin the regional table and exact eligibility before implementing.
- **Starter equipment, `levelup`, main route level 1-98 and flame route 99-105:** Baseline and high-level routes must be split by profile; validate every level/kill/item/NPC gate and reward branch.

Evidence: [CHARACTER::PointChange / ComputePoints](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char.cpp); [CHARACTER::DistributeExp](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_battle.cpp); [exp and stat tables](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/constants.cpp); [Detailed source checklist and coverage limits](server-audit.md).


## SYS-SKILL

Skills, statuses and auxiliary training

### SRV-008

**Skills, skill groups, books and guild skills** — planned; P2.

Scope: classic core.

Includes active/passive skills, cooldowns, levels, master/grand-master training, skill resets, skill books, horse and guild skills.

Implementation prerequisites: [SYS-SKILL](#sys-skill).

Behavioral coupling: [SRV-007](#srv-007), combat formulas, skill definitions.

Named subfeatures and required behavior:

- **Class skill-tree choice and skill-point advancement:** Selected [`skill_group.quest`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/skill_group.quest) chooses one of two groups for each of the four jobs; `CHARACTER::SetSkillGroup`, `SkillLevelUp` and the player `skillup` command apply it. Preserve teacher/level gates, point costs, active/passive distinctions and skill-group state.
- **Normal, Master, Grand Master and Perfect Master ranks:** [`char_skill.cpp`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_skill.cpp) uses `SKILL_MASTER`, `SKILL_GRAND_MASTER`, `SKILL_PERFECT_MASTER`, `LearnSkillByBook` and `LearnGrandMasterSkill`. Model rank transitions, forced promotion rules, failed/successful reads, EXP consumption, read counters and server deadlines explicitly.
- **Skill books, read-delay bypass and concentrated-reading bonus:** `CHARACTER::UseItemEx` dispatches `ITEM_SKILLBOOK`; `LearnSkillByBook` checks learnability, rank, EXP and next-read time and consumes `AFFECT_SKILL_NO_BOOK_DELAY`/`AFFECT_SKILL_BOOK_BONUS`. These consumable effects, success RNG and failure consumption are separate test branches.
- **Soul Stone Grand Master training:** Selected [`training_grandmaster_skill.quest`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/training_grandmaster_skill.quest) handles item 50513, whose English catalog name is `Soul Stone`; it selects eligible G skills, applies cooldown and alignment cost, calls `pc.learn_grand_master_skill`, and reaches level 40/P. Do not merge this with ordinary books.
- **Leadership, party roles, summon and heal:** `SKILL_LEADERSHIP` has three training-book tiers in `char_item.cpp`. [`party.cpp`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/party.cpp) gates attacker, haste, tanker, buffer, skill-master and defender roles, party heal and leader summon by leadership. Each role bonus, assignment permission and proximity/disconnect rule needs coverage.
- **Empire languages and Language Ring:** `SKILL_LANGUAGE1..3` are trained by items 50311-50313; `CInputMain::Chat`/`Whisper` use language skill power when converting other-empires' text, while the Language Ring unique group bypasses it. Keep language comprehension separate from localization and chat moderation.
- **Combo mastery and attack-chain timing:** Items 50304-50306 train `SKILL_COMBO` with level gates; `CHARACTER::SetSkill` selects the combo index. [`ani.cpp`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/ani.cpp) loads weapon and mounted combo timings. Compile combo order, cancel/link windows and server hit timing with the corresponding animation profile.
- **Horse summon and mounted-combat skills:** `skill.h` and `char_skill.cpp` implement horse summon plus Wild Attack, Charge, Escape and ranged Wild Attack; the Horse Riding Manual awards bounded riding points. Preserve job restrictions, SP/cooldown/riding requirements and point allocation.
- **Auxiliary trained skills:** Live item branches train polymorph, maximum-HP, penetration-resistance, creation, mining and horse skills. Profile each because their books and values can exist independently of a classic content selection.
- **Stat, skill-group and single-skill reset:** Selected `reset_status.quest` and `skill_reset2.quest` call `pc.reset_status`, `pc.clear_skill` and `pc.set_skill_group`; `ITEM_SKILLFORGET` lowers one skill. `reset_scroll.quest` is present but not selected. Treat NPC, item, level/cost/cooldown variants as distinct flows rather than one generic respec.

Evidence: [CHARACTER::UseSkill / LearnSkillByBook](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_skill.cpp); [CSkillManager::Initialize](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/skill.cpp); [TSkillTable](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/common/tables.h); [Detailed source checklist and coverage limits](server-audit.md).

### SRV-010

**Affects, buffs, debuffs, immunities and resistances** — planned; P2.

Scope: classic core.

Persistent and timed effects, poison/fire/stun/slow, equipment buffs and apply-point recalculation need typed definitions and expiry scheduling.

Implementation prerequisites: [SYS-SKILL](#sys-skill).

Behavioral coupling: [SRV-007](#srv-007), [SRV-008](#srv-008), time/scheduler.

Named subfeatures and required behavior:

- **Recovery, ability, cleansing and invisibility consumables:** Live `ITEM_USE` branches cover delayed, immediate and continuous HP/SP recovery, ability buffs, direct affects, bad-affect clearing and invisibility. Arena/dungeon/war limits and use/consumption ordering are part of the rules.

Evidence: [affect lifecycle](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/affect.cpp); [CHARACTER::AddAffect / RemoveAffect](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_affect.cpp); [EApplyTypes / EImmuneFlags / EMobResists](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/common/length.h); [Detailed source checklist and coverage limits](server-audit.md).

### REF-005

**Classic class and horse skills** — reference-only; P2.

Scope: open-mt2 broad but partial implementation; QCX progression partial.

open-mt2 SkillManager.load explicitly registers 55 entries: 48 active and 7 passive. Two additional horse passive classes are wired outside that registry. Material TODOs remain, and registry coverage does not include Lycan.

Implementation prerequisites: [SYS-SKILL](#sys-skill).

Behavioral coupling: [REF-004](#ref-004), skill proto/formulas, affects, cooldowns, skill progression.

Evidence: [SkillManager.load](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/core/domain/manager/SkillManager.ts); [PlayerSkill.useSkill/useSkillAttack](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/core/domain/entities/game/player/delegate/PlayerSkill.ts); [PlayerSkills.SkillUp/LearnSkillByBook](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/Skills/PlayerSkills.cs).


## SYS-NPC

NPC interaction and dialogue

### SRV-029

**NPC interaction, dialogue, target markers and quest UI** — planned; P3.

Scope: classic core.

Click/talk/use/take triggers, scripted say/select/input/confirm flows, quest letters and target creation/deletion.

Implementation prerequisites: [SYS-NPC](#sys-npc).

Behavioral coupling: [SRV-005](#srv-005), [SRV-028](#srv-028).

Named subfeatures and required behavior:

- **NPC/map warp services:** Selected `map_warp.quest`, `neutral_warp.quest` and `goto_empire_castle.quest` provide destination/empire transport separately from warp items. Compile destinations against the map profile, bounds, access rules and fees.
- **Side quests, quest-scroll bands and collection/biologist lines level 4-94:** Collection timers, repeated turn-ins, random acceptance and final permanent bonuses require durable per-character state and deterministic fixtures.

Evidence: [quest::NPC](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/questnpc.cpp); [TargetManager](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/target.cpp); [RegisterNPCFunctionTable](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/questlua_npc.cpp); [Detailed source checklist and coverage limits](server-audit.md).


## SYS-QUEST

Quest events, flags, timers and content

### SRV-028

**Quest VM, compiler, state, timers and event flags** — planned; P3.

Scope: classic core + content platform.

284 quest sources, 238 selected by locale_list, 27 native namespaces and 532 parsed native bindings. Replace unrestricted legacy scripting with a sandboxed, versioned, validated content runtime or typed workflows; preserve trigger semantics deliberately.

Implementation prerequisites: [SYS-QUEST](#sys-quest).

Behavioral coupling: [SRV-003](#srv-003), [SRV-029](#srv-029), scheduler, content publishing.

Named subfeatures and required behavior:

- **Quest and signal-use items:** `ITEM_QUEST` routes through `CQuestManager::UseItem` or `SIGUse` according to flags/group IDs; many selected quests also bind exact item-vnum `use`. Content compilation must reconcile both dispatch routes and reject duplicate reward/consumption paths.
- **Starter equipment, `levelup`, main route level 1-98 and flame route 99-105:** Baseline and high-level routes must be split by profile; validate every level/kill/item/NPC gate and reward branch.
- **Side quests, quest-scroll bands and collection/biologist lines level 4-94:** Collection timers, repeated turn-ins, random acceptance and final permanent bonuses require durable per-character state and deterministic fixtures.
- **Item informer/delete utilities, localized dialogue, quest letters/targets/counters/clocks and test-server notices:** These are supporting player-facing workflows, not generic quest-engine completion. Their UI, localization and authorization must be covered or explicitly excluded.

Evidence: [quest compiler](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/quest/src/qc.cc); [quest::CQuestManager](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/questmanager.cpp); [CQuestManager::RegisterQuestLuaFunctionTable](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/questlua.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### CLI-011

**Quest dialogue, choices, item selection, timers, and targets** — planned; P3.

Scope: Server-driven quest/event text, image/skin presentation, buttons, confirm/input/item choice, clocks, NPC positions and target markers.

Do not execute legacy Python or unrestricted quest scripts. Normalize supported dialogue actions and reject/queue unknown commands; accept with branch/reconnect/persisted-wait playthroughs and localization snapshots.

Implementation prerequisites: [SYS-QUEST](#sys-quest).

Behavioral coupling: authoritative quest state machine, localization, [CLI-009](#cli-009), [CLI-028](#cli-028), [CLI-029](#cli-029).

Evidence: [CPythonEventManager](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/PythonEventManager.cpp); [QuestDialog](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/bin/pack/root/uiquest.py).

### REF-010

**Quest event/state framework** — reference-only; P3.

Scope: open-mt2 partial; QCX scaffold.

open-mt2 has 11 concrete quest files but unfinished save/reward paths. QCX explicitly does not load quest state.

Implementation prerequisites: [SYS-QUEST](#sys-quest).

Behavioral coupling: persistent per-character state, event registry, NPC/mob/item IDs, rewards, dialogs.

Evidence: [QuestManager.load/registerTask/onAnswer/onKill/onLogout](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/core/domain/quests/QuestManager.ts); [QuestManager interaction/lifecycle tests](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/test/unit/core/domain/quests/QuestManager.test.ts); [QuestManager.InitializePlayer](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/Quest/QuestManager.cs).

### MOD-017

**Quest inventory, converter and authoring representation** — planned; P3.

Scope: modernization.

Inventory active scripts/includes and API usage, translate supported event/state/action subset, emit unsupported constructs; no arbitrary script execution.

Implementation prerequisites: [SYS-QUEST](#sys-quest).

Evidence: [Quest inventory, converter and authoring representation](development-and-admin.md).


## SYS-ECONOMY

Shops, storage, refining and currencies

### SRV-015

**Refining, sockets, item attributes and upgrade chains** — planned; P3.

Scope: classic core + content.

Normal/blessed/magic/metin/rod/pick/ore refining, failure outcomes, material/gold costs, refine-set chains, sockets and normal/rare attribute rolls.

Implementation prerequisites: [SYS-ECONOMY](#sys-economy).

Behavioral coupling: [SRV-013](#srv-013), [SRV-020](#srv-020), recipe compiler.

Named subfeatures and required behavior:

- **Refinement scrolls, Metin stones, sockets and attributes:** Live branches cover tuning/detachment, socket cleaning, normal/rare attribute add/change, accessory socket creation/insertion, belt sockets and Metin insertion. Keep target validation, probability, failure result, item consumption and logs transactional; source enum coverage alone does not select every scroll variant.

Evidence: [CRefineManager](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/refine.cpp); [item attribute generation](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/item_attribute.cpp); [InitializeRefineTable / InitializeItemAttrTable / InitializeItemRareTable](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/db/src/ClientManagerBoot.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### SRV-016

**NPC shops and extended shops** — planned; P3.

Scope: classic core + content.

NPC buying/selling, multi-tab/secondary-currency shops and distance/window constraints. Compile shop definitions and validate vnums, prices and currencies.

Implementation prerequisites: [SYS-ECONOMY](#sys-economy).

Behavioral coupling: [SRV-013](#srv-013), [SRV-020](#srv-020), [SRV-029](#srv-029).

Named subfeatures and required behavior:

- **Blacksmith/fishrod shops, mall/warehouse, gold bars, premium/voucher cash and shop-box quests:** Each currency/storage/external-award boundary needs separate authorization, cap, provenance and failure recovery.

Evidence: [CShopManager::Initialize / StartShopping / ReadShopTableEx](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/shop_manager.cpp); [CShop::Buy / Sell](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/shop.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### SRV-019

**Safebox, warehouse and item-mall storage** — planned; P5.

Scope: classic core.

Account/password-gated storage, capacity, item moves and mall checkout. Use account RLS/private subscriptions and atomic transfers.

Implementation prerequisites: [SYS-ECONOMY](#sys-economy).

Behavioral coupling: [SRV-002](#srv-002), [SRV-013](#srv-013), persistent private storage.

Named subfeatures and required behavior:

- **Blacksmith/fishrod shops, mall/warehouse, gold bars, premium/voucher cash and shop-box quests:** Each currency/storage/external-award boundary needs separate authorization, cap, provenance and failure recovery.

Evidence: [CSafebox](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/safebox.cpp); [SafeboxCheckin / SafeboxCheckout / SafeboxItemMove](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/input_main.cpp); [QUERY_SAFEBOX_*](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/db/src/ClientManagerPlayer.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### SRV-020

**Gold, premium time, cash, awards and economy logs** — planned; P5.

Scope: classic core + service integration.

Yang/gold, guild/monarch funds, premium timers, cash voucher/item-award paths and money logs. Define sources/sinks, caps, overflow behavior and auditable grants.

Implementation prerequisites: [SYS-ECONOMY](#sys-economy), [SYS-OPS](#sys-ops), [SYS-ADMIN](#sys-admin).

Behavioral coupling: [SRV-002](#srv-002), [SRV-013](#srv-013), audit ledger.

Named subfeatures and required behavior:

- **Blacksmith/fishrod shops, mall/warehouse, gold bars, premium/voucher cash and shop-box quests:** Each currency/storage/external-award boundary needs separate authorization, cap, provenance and failure recovery.

Evidence: [CMoneyLog](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/db/src/MoneyLog.cpp); [pc_change_money / pc_charge_cash / pc_give_award](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/questlua_pc.cpp); [EMoneyLogType / EPremiumTypes](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/common/length.h); [Detailed source checklist and coverage limits](server-audit.md).

### CLI-012

**NPC shops, private shops, mall, and auction surfaces** — planned; P5.

Scope: Buy/sell tabs and currencies, player shop creation/signs, mall checkout, auction list/register/unique-auction views and price confirmation.

The archive proves screen/protocol availability, not a fully enabled auction. Acceptance uses atomic balance/item transitions, stale-price rejection, seller disconnect recovery and exact read-only previews before purchase.

Implementation prerequisites: [SYS-ECONOMY](#sys-economy), [SYS-TRADE](#sys-trade).

Behavioral coupling: shops/economy, item ownership, auction service if selected, [CLI-005](#cli-005), [CLI-028](#cli-028), [CLI-029](#cli-029).

Evidence: [ShopDialog](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/bin/pack/root/uishop.py); [AuctionWindow](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/bin/pack/root/uiauction.py).

### CLI-014

**Refining, sockets, metin attachment, cube crafting, and item selection** — planned; P3.

Scope: Upgrade preview/chance/cost/result, stone attachment, socket/attribute presentation, cube recipes/results and bounded selection dialogs.

Client previews must derive from versioned authoritative definitions. Acceptance uses seeded/statistical recipe tests plus atomic failure/success, disconnect and duplicate-request cases.

Implementation prerequisites: [SYS-ECONOMY](#sys-economy), [SYS-ITEM](#sys-item).

Behavioral coupling: recipes and economy, transactional inventory, [CLI-005](#cli-005), [CLI-007](#cli-007), [CLI-028](#cli-028), [CLI-029](#cli-029).

Evidence: [RefineDialog](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/bin/pack/root/uirefine.py); [CubeWindow](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/bin/pack/root/uicube.py).

### REF-008

**NPC shops** — reference-only; P3.

Scope: implemented reference in both emulators.

Generate and validate catalogs; transactions remain server owned.

Implementation prerequisites: [SYS-ECONOMY](#sys-economy).

Behavioral coupling: [REF-006](#ref-006), NPC interaction, currency, shop catalog.

Evidence: [ShopService.openShop/buy/sell](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/game/app/service/ShopService.ts); [World.LoadShops](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/World/World.cs); [TsvShopProvider](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/Shops/TsvShopProvider.cs).


## SYS-CHAT

Chat, whispers and moderation

### SRV-022

**Chat, whispers, messenger friends and blocking** — partial; P3.

Scope: classic core.

Local/global/guild/party chat, whispers, friend requests, ignore/block modes, language conversion and moderation. Add rate limits, reporting and privacy policy.

Implementation prerequisites: [SYS-CHAT](#sys-chat).

Behavioral coupling: [SRV-002](#srv-002), [SRV-004](#srv-004), [SRV-050](#srv-050).

Current project: Centered chat/history with original art and focus tests; only current shared normal-message rule, no full channel/whisper/social behavior.

Named subfeatures and required behavior:

- **Empire languages and Language Ring:** `SKILL_LANGUAGE1..3` are trained by items 50311-50313; `CInputMain::Chat`/`Whisper` use language skill power when converting other-empires' text, while the Language Ring unique group bypasses it. Keep language comprehension separate from localization and chat moderation.
- **Player block preferences:** `CHARACTER::SetBlockMode` persists separate flags for exchange, party invite, guild invite, whisper, messenger invite and party request; target handlers enforce them. Preserve all six toggles and distinguish them from sanctions.
- **Chat block/mute and vote-block moderation:** `AFFECT_BLOCK_CHAT`, `block_chat`, `block_chat_list` and `vote_block_chat` implement timed moderation across cores. Rebuild this as permissioned sanctions with actor/reason/expiry/appeal evidence rather than conflating it with a player's whisper block.
- **Emotes and mutual emote permission:** `cmd_info` exposes kiss, slap, French kiss, clap, cheers, dances and expressive emotes; `emotion_allow` and `do_emotion` handle paired consent. Motion/effect availability and restrictions need generated action IDs and two-client tests.

Evidence: [CInputMain::Chat / Whisper / Messenger](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/input_main.cpp); [MessengerManager](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/messenger_manager.cpp); [CBanwordManager](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/banword.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### CLI-008

**Chat, whisper, channels, links, and moderation feedback** — partial; P3.

Scope: Passive chat, edit/history, normal/party/guild/shout channels, whisper windows/buttons, item hyperlinks, emoticons, insult-filter feedback and system notices.

Reproduce fade/order/layout and keyboard ownership while sanitizing user content. Acceptance covers rate/length rejection, channel permissions, reconnect history policy, IME, hyperlink safety and two-client delivery.

Implementation prerequisites: [SYS-CHAT](#sys-chat).

Behavioral coupling: server chat channels, social membership, moderation, [CLI-028](#cli-028), [CLI-029](#cli-029).

Current project: Centered chat/history with original art and focus tests; only current shared normal-message rule, no full channel/whisper/social behavior.

Evidence: [ChatLogWindow](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/bin/pack/root/uichat.py); [CPythonChat](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/PythonChat.cpp).

### REF-012

**Chat, shout and whisper** — reference-only; P3.

Scope: open-mt2 nearby/empire chat partial; QCX adds cross-core shout and whisper.

QCX hard-codes empire in cross-core shout paths; modern moderation and block/report flows are outside both implementations.

Implementation prerequisites: [SYS-CHAT](#sys-chat).

Behavioral coupling: presence, identity/name lookup, rate limits, block/moderation policy, cross-shard routing.

Evidence: [ChatService.talk/shout](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/game/app/service/ChatService.ts); [ChatManager.Talk/ShoutAsync/NoticeAsync](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/ChatManager.cs); [WhisperHandler.ExecuteAsync](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/PacketHandlers/Game/WhisperHandler.cs).


## SYS-SOCIAL

Friends, invitations and consent

### CLI-015

**Party and messenger/friend systems** — planned; P5.

Scope: Invites, membership/link state, roles, HP/affects, distribution, party skills, friend add/remove, online state and whisper entry.

Acceptance requires three-client role/leave/reconnect/offline cases, blocked interaction behavior and server-controlled permissions.

Implementation prerequisites: [SYS-SOCIAL](#sys-social), [SYS-PARTY](#sys-party).

Behavioral coupling: social graph, presence privacy, party authority, [CLI-008](#cli-008), [CLI-029](#cli-029).

Evidence: [PartyWindow](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/bin/pack/root/uiparty.py); [CPythonMessenger](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/PythonMessenger.cpp).


## SYS-TRADE

Direct exchange and player shops

### SRV-017

**Player private shops and price lists** — planned; P5.

Scope: classic core.

Private shop creation, signs, persisted price lists and purchase transfer. Requires transactional sales, ownership locking and abuse controls.

Implementation prerequisites: [SYS-TRADE](#sys-trade).

Behavioral coupling: [SRV-013](#srv-013), [SRV-020](#srv-020), [SRV-022](#srv-022).

Named subfeatures and required behavior:

- **Private-shop bundle:** Item 50200 invokes `__OpenPrivateShop`/`UseSilkBotary`; normal command rows close shops. Reserve stock and settle purchases through the authoritative shop transaction rather than treating the bundle as a cosmetic opener.

Evidence: [CInputMain::MyShop](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/input_main.cpp); [CShop::Create / AddGuest](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/shop.cpp); [CItemPriceListTableCache](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/db/src/Cache.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### SRV-018

**Direct player exchange** — planned; P5.

Scope: classic core.

Two-party item/gold trade with distance, capacity and acceptance invalidation. Implement as one atomic commit with idempotent requests.

Implementation prerequisites: [SYS-TRADE](#sys-trade).

Behavioral coupling: [SRV-013](#srv-013), [SRV-020](#srv-020), [SRV-004](#srv-004).

Evidence: [CExchange::AddItem / AddGold / Accept / Cancel](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/exchange.cpp); [CInputMain::Exchange](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/input_main.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### CLI-013

**Player exchange, safebox, and account mall storage** — planned; P5.

Scope: Two-party offers/acceptance, gold and item changes, cancellation; safebox password/size/money/items; mall storage and checkout.

Acceptance covers simultaneous edits, capacity and ownership bounds, cancel/disconnect/timeouts, replay/idempotency and privacy between two accounts.

Implementation prerequisites: [SYS-TRADE](#sys-trade), [SYS-ECONOMY](#sys-economy).

Behavioral coupling: atomic trade, private storage, [CLI-005](#cli-005), [CLI-028](#cli-028), [CLI-029](#cli-029).

Evidence: [ExchangeDialog](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/bin/pack/root/uiexchange.py); [CPythonSafeBox](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/PythonSafeBox.cpp).

### REF-009

**Online player private shops** — reference-only; P5.

Scope: open-mt2 implemented; QCX absent.

The open-mt2 exact-instance check, overflow guard and capacity rollback are strong invariant references. This is not an offline shop.

Implementation prerequisites: [SYS-TRADE](#sys-trade).

Behavioral coupling: [REF-006](#ref-006), currency, presence, atomic transaction, item locks.

Evidence: [PrivateShopService.openPrivateShop/buy/closePrivateShop](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/game/app/service/PrivateShopService.ts); [PrivateShopService buy rollback and validation tests](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/test/unit/game/app/service/PrivateShopService.test.ts); [TODO implement player shop](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/World/Shop.cs).


## SYS-PARTY

Parties and shared rewards

### SRV-021

**Parties and party bonuses** — planned; P5.

Scope: classic core.

Invites, leader/member roles, online links, map/distance state, EXP distribution, party skills/bonuses, removal and disconnect behavior.

Implementation prerequisites: [SYS-PARTY](#sys-party).

Behavioral coupling: [SRV-004](#srv-004), [SRV-007](#srv-007), [SRV-009](#srv-009).

Named subfeatures and required behavior:

- **Leadership, party roles, summon and heal:** `SKILL_LEADERSHIP` has three training-book tiers in `char_item.cpp`. [`party.cpp`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/party.cpp) gates attacker, haste, tanker, buffer, skill-master and defender roles, party heal and leader summon by leadership. Each role bonus, assignment permission and proximity/disconnect rule needs coverage.

Evidence: [CParty](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/party.cpp); [party persistence/broadcast](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/db/src/ClientManagerParty.cpp); [RegisterPartyFunctionTable](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/questlua_party.cpp); [Detailed source checklist and coverage limits](server-audit.md).


## SYS-PVP

PK, alignment, duels and arenas

### SRV-026

**Open-world PvP, PK modes, alignment and duels** — planned; P5.

Scope: classic core.

Mutual duel state, PK modes, empire/guild exemptions, killer status and penalties must be release-profiled and server-authoritative.

Implementation prerequisites: [SYS-PVP](#sys-pvp).

Behavioral coupling: [SRV-009](#srv-009), [SRV-047](#srv-047).

Named subfeatures and required behavior:

- **Soul Stone Grand Master training:** Selected [`training_grandmaster_skill.quest`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/training_grandmaster_skill.quest) handles item 50513, whose English catalog name is `Soul Stone`; it selects eligible G skills, applies cooldown and alignment cost, calls `pc.learn_grand_master_skill`, and reaches level 40/P. Do not merge this with ordinary books.
- **Alignment-based inventory/equipment drops:** [`CHARACTER::ItemDropPenalty`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_battle.cpp) selects inventory/equipment probabilities and quantities by alignment band, respects anti-drop flags/protection item, and excludes low levels, shops and battle arena. It is invoked for eligible non-duel/non-war/non-event player deaths. Item removal, ownership and ground-drop placement must be atomic.
- **Peace, revenge, free, protect and guild PK modes:** `CHARACTER::SetPKMode` and [`CPVPManager`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/pvp.cpp) apply empire, guild, map and alignment rules for `PK_MODE_*`. Revenge mode is real behavior, not just a UI label. Define safe-map and level/protection boundaries per profile.
- **Duel request/agreement/fight/revenge lifecycle:** `CPVP::Agree`, `Win` and packet `PVP_MODE_NONE/AGREE/FIGHT/REVENGE` track reciprocal consent and outcomes. Test crossed requests, distance/map changes, logout, death and stale pair cleanup.

Evidence: [CPVP / CPVPManager](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/pvp.cpp); [CHARACTER::CanBeginFight / battle](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_battle.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### SRV-027

**Arena and scheduled battle arena** — planned; P5.

Scope: classic core + content.

Duels, observers, potion limits, arena maps and scheduled battle-arena events.

Implementation prerequisites: [SYS-PVP](#sys-pvp).

Behavioral coupling: [SRV-005](#srv-005), [SRV-009](#srv-009), [SRV-049](#srv-049).

Named subfeatures and required behavior:

- **Arena and guild-war observers:** `CArenaManager`, `CWarMap` and the player `observer_exit` command maintain spectator membership/counts and exclude observers from party/trade/item/combat paths. Spectator visibility and exit/restore location need explicit authority and privacy rules.

Evidence: [CArena / CArenaManager](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/arena.cpp); [CBattleArena](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/BattleArena.cpp); [RegisterArenaFunctionTable](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/questlua_arena.cpp); [Detailed source checklist and coverage limits](server-audit.md).


## SYS-INSTANCE

Dungeon and encounter lifecycle

### SRV-030

**Dungeon instances and private-map orchestration** — planned; P6.

Scope: classic core + content.

Private maps, party membership, unique mobs/items, regen, timers, flags, warps, elimination and exit/rejoin state. Reconnect must resolve exactly one valid instance membership.

Implementation prerequisites: [SYS-INSTANCE](#sys-instance).

Behavioral coupling: [SRV-005](#srv-005), [SRV-011](#srv-011), [SRV-028](#srv-028).

Named subfeatures and required behavior:

- **Context-specific revive:** `do_restart` has separate ordinary-map, guild-war, dungeon, Three-Way War and Sungzi/token paths, with different positions and HP/SP restoration. `ReviveInvisible(5)` supplies temporary post-revive protection on applicable paths. Preserve the selected rules instead of using a universal respawn.
- **Devil Tower, catacomb, spider floors, Heaven's Cave/Blue Dragon/Dragon Lair and Flame Dungeon:** These are separate access, instance, encounter, timer and reward graphs; source presence does not prove a complete selected pack.

Evidence: [CDungeon / CDungeonManager](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/dungeon.cpp); [RegisterDungeonFunctionTable](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/questlua_dungeon.cpp); [dungeon content catalog](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/dungeon); [Detailed source checklist and coverage limits](server-audit.md).

### SRV-031

**Devil Tower, catacomb and spider dungeon content** — planned; P6.

Scope: content profile.

Quest-driven floors, keys, stones, bosses and rewards. Catalog presence does not establish correctness or target-release inclusion.

Implementation prerequisites: [SYS-INSTANCE](#sys-instance).

Behavioral coupling: [SRV-030](#srv-030), [SRV-012](#srv-012), content assets.

Named subfeatures and required behavior:

- **Devil Tower, catacomb, spider floors, Heaven's Cave/Blue Dragon/Dragon Lair and Flame Dungeon:** These are separate access, instance, encounter, timer and reward graphs; source presence does not prove a complete selected pack.

Evidence: [quest deviltower_zone](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/deviltower_zone.quest); [quest devilcatacomb_zone](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/devilcatacomb_zone.quest); [quest spider_dungeon_3floor_boss](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/spider_dungeon_3floor_boss.quest); [Detailed source checklist and coverage limits](server-audit.md).

### SRV-032

**Blue Dragon and Dragon Lair** — planned; P6.

Scope: content profile + specialized rules.

Specialized boss skills, lair access/weeklies and Lua binder/data. Treat as later-era content unless the selected baseline includes it.

Implementation prerequisites: [SYS-INSTANCE](#sys-instance).

Behavioral coupling: [SRV-030](#srv-030), [SRV-009](#srv-009), [SRV-028](#srv-028).

Named subfeatures and required behavior:

- **Devil Tower, catacomb, spider floors, Heaven's Cave/Blue Dragon/Dragon Lair and Flame Dungeon:** These are separate access, instance, encounter, timer and reward graphs; source presence does not prove a complete selected pack.

Evidence: [BlueDragon state/skills](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/BlueDragon.cpp); [DragonLair](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/DragonLair.cpp); [quest dragon_lair](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/dragon_lair.quest); [Detailed source checklist and coverage limits](server-audit.md).


## SYS-MOUNT

Horse, mount and companion actors

### SRV-037

**Horse ownership, leveling, stamina and combat** — planned; P6.

Scope: classic core.

Horse summon/revive/feed/ride, health/stamina, levels, names, training missions and horse skills.

Implementation prerequisites: [SYS-MOUNT](#sys-mount).

Behavioral coupling: [SRV-003](#srv-003), [SRV-008](#srv-008), [SRV-028](#srv-028).

Named subfeatures and required behavior:

- **Horse summon and mounted-combat skills:** `skill.h` and `char_skill.cpp` implement horse summon plus Wild Attack, Charge, Escape and ranged Wild Attack; the Horse Riding Manual awards bounded riding points. Preserve job restrictions, SP/cooldown/riding requirements and point allocation.
- **Horse acquisition, leveling, grades, health/stamina and naming:** Selected `horse_levelup`, `horse_upgrade`, `horse_upgrade2`, `horse_guard`, `horse_menu`, `horse_summon`, `horse_revive`, `horse_ride` and ticket-exchange quests cover mounted trials, grade items, summon items, feed, death/revive, ride/unsummon, status and naming. However, `pony_buy.quest` and `pony_levelup.quest` are present but absent from `locale_list`, so this snapshot does not prove a complete initial acquisition path.

Evidence: [CHorseRider](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/horse_rider.cpp); [CHARACTER horse operations](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_horse.cpp); [RegisterHorseFunctionTable](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/questlua_horse.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### SRV-038

**Special mounts and ride items** — decision; P9.

Scope: content variant.

Timed ride items, mount bonuses, upgrades and event mounts. Keep definitions data-driven and separate from the classic horse contract.

Implementation prerequisites: [SYS-MOUNT](#sys-mount).

Behavioral coupling: [SRV-037](#srv-037), [SRV-013](#srv-013), [SRV-010](#srv-010).

Named subfeatures and required behavior:

- **Timed/event mounts versus persistent horse:** Selected `ride`, `ride_upgradable`, `ride_ticket_change`, `training_mount` and seasonal ride quests use timed mount affects/items; these are a separately profile-gated system from `CHorseRider` progression and horse skills.

Evidence: [MountVnum / mount state](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char.cpp); [quest ride](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/ride.quest); [quest upgrade_mount](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/upgrade_mount.quest); [Detailed source checklist and coverage limits](server-audit.md).

### SRV-039

**Pet summoning, following and buffs** — decision; P9.

Scope: optional enabled variant.

Enabled at the pinned master, but not universal early-classic behavior. Summon/despawn, follow AI, buffs and item binding need explicit profile choice.

Implementation prerequisites: [SYS-MOUNT](#sys-mount), [SYS-ITEM](#sys-item), [SYS-SKILL](#sys-skill).

Behavioral coupling: [SRV-013](#srv-013), [SRV-010](#srv-010), [SRV-028](#srv-028).

Named subfeatures and required behavior:

- **Fish, bait, rod, pick, campfire, polymorph and cube interactions:** `UseItemEx` has concrete fish/bait/rod, pick, campfire and polymorph branches; `fishing`, `mining` and cube handlers own their action/RNG/cost flows. Each needs map/tool/state checks and durable item outcomes.

Evidence: [__PET_SYSTEM__](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/common/service.h); [CPetActor / CPetSystem](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/PetSystem.cpp); [RegisterPetFunctionTable](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/questlua_pet.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### REF-011

**Horse progression and riding** — reference-only; P6.

Scope: open-mt2 implemented vertical slice; QCX absent.

Separate horse gameplay identity/stats from visual mount presentation.

Implementation prerequisites: [SYS-MOUNT](#sys-mount).

Behavioral coupling: [REF-001](#ref-001), [REF-003](#ref-003), [REF-005](#ref-005), quests, mounted appearance, persistent horse state.

Evidence: [PlayerHorse](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/core/domain/entities/game/player/delegate/PlayerHorse.ts); [PlayerHorse tests](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/test/unit/core/domain/entities/game/player/PlayerHorse.test.ts); [HorseUpgradeQuest](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/core/domain/quests/quests/HorseUpgradeQuest.ts).


## SYS-LIFE

Fishing, mining, crafting and polymorph

### SRV-040

**Fishing, rods, bait and fish outcomes** — planned; P6.

Scope: classic core + content.

Fishing timing, rod refinement, bait, fish tables, catches/failures and fish-use outcomes. __FISHING_MAIN__ is only a disabled standalone test harness; the game path is active when undefined.

Implementation prerequisites: [SYS-LIFE](#sys-life).

Behavioral coupling: [SRV-013](#srv-013), [SRV-028](#srv-028), randomness service.

Named subfeatures and required behavior:

- **Fish, bait, rod, pick, campfire, polymorph and cube interactions:** `UseItemEx` has concrete fish/bait/rod, pick, campfire and polymorph branches; `fishing`, `mining` and cube handlers own their action/RNG/cost flows. Each needs map/tool/state checks and durable item outcomes.

Evidence: [fishing::Initialize / Take / Use](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/fishing.cpp); [CInputMain::Fishing](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/input_main.cpp); [fishing definition table](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/fishing.txt); [Detailed source checklist and coverage limits](server-audit.md).

### SRV-041

**Mining, pickaxes and ore refining** — planned; P6.

Scope: classic core + content.

Ore nodes, dig timing, pick refinement, ore/diamond refining, guild alchemist/building dependency and rewards.

Implementation prerequisites: [SYS-LIFE](#sys-life).

Behavioral coupling: [SRV-013](#srv-013), [SRV-015](#srv-015), [SRV-005](#srv-005).

Named subfeatures and required behavior:

- **Auxiliary trained skills:** Live item branches train polymorph, maximum-HP, penetration-resistance, creation, mining and horse skills. Profile each because their books and values can exist independently of a classic content selection.
- **Fish, bait, rod, pick, campfire, polymorph and cube interactions:** `UseItemEx` has concrete fish/bait/rod, pick, campfire and polymorph branches; `fishing`, `mining` and cube handlers own their action/RNG/cost flows. Each needs map/tool/state checks and durable item outcomes.

Evidence: [mining namespace](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/mining.cpp); [pc_mining / pc_ore_refine / pc_diamond_refine](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/questlua_pc.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### SRV-042

**Polymorph forms, marbles and books** — planned; P6.

Scope: classic core.

Form/race changes, duration, skill/book progression, bonuses and cleanup.

Implementation prerequisites: [SYS-LIFE](#sys-life).

Behavioral coupling: [SRV-011](#srv-011), [SRV-013](#srv-013), [SRV-009](#srv-009).

Named subfeatures and required behavior:

- **Auxiliary trained skills:** Live item branches train polymorph, maximum-HP, penetration-resistance, creation, mining and horse skills. Profile each because their books and values can exist independently of a classic content selection.
- **Polymorph balls, books and removal:** [`CHARACTER::ItemProcess_Polymorph`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_item.cpp) validates target mob/level, duration/bonus and item subtype; `CPolymorphUtils` updates book practice, while quest APIs expose apply/remove. Define equipment, skill/stat, mount, item-read and death interactions while transformed.
- **Fish, bait, rod, pick, campfire, polymorph and cube interactions:** `UseItemEx` has concrete fish/bait/rod, pick, campfire and polymorph branches; `fishing`, `mining` and cube handlers own their action/RNG/cost flows. Each needs map/tool/state checks and durable item outcomes.

Evidence: [CPolymorphUtils](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/polymorph.cpp); [CHARACTER::SetPolymorph](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char.cpp); [pc_polymorph / pc_give_poly_marble](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/questlua_pc.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### SRV-043

**Cube crafting and recipe content** — planned; P6.

Scope: classic/later content.

NPC-gated material recipes, gold costs, success probability, output and recipe UI. Compile and validate all recipe references and duplicate/overlapping inputs.

Implementation prerequisites: [SYS-LIFE](#sys-life).

Behavioral coupling: [SRV-013](#srv-013), [SRV-020](#srv-020), [SRV-029](#srv-029).

Named subfeatures and required behavior:

- **Fish, bait, rod, pick, campfire, polymorph and cube interactions:** `UseItemEx` has concrete fish/bait/rod, pick, campfire and polymorph branches; `fishing`, `mining` and cube handlers own their action/RNG/cost flows. Each needs map/tool/state checks and durable item outcomes.

Evidence: [Cube_InformationInitialize / Cube_make](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/cube.cpp); [cube recipes](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/cube.txt); [quest cube](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/cube.quest); [Detailed source checklist and coverage limits](server-audit.md).

### CLI-018

**Fishing, mining/digging, mounts, and contextual actions** — planned; P6.

Scope: Fishing cast/wait/react/catch/fail/cancel states and UI, digging motion, horse/mount modes, mounted weapon modes and contextual NPC/item actions.

Acceptance exercises location/tool/state validation, timing and cancellation, loot confirmation, rider/mount rig alignment and each supported weapon mode.

Implementation prerequisites: [SYS-LIFE](#sys-life), [SYS-MOUNT](#sys-mount).

Behavioral coupling: fishing/mining/horse rules, [CLI-002](#cli-002), [CLI-024](#cli-024), [CLI-025](#cli-025), [CLI-027](#cli-027).

Evidence: [CPythonNetworkStream::RecvFishing](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/PythonNetworkStreamPhaseGame.cpp); [enum EMode](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/GameLib/RaceMotionData.h).


## SYS-GUILD

Guild organization, land and war

### SRV-023

**Guild membership, ranks, funds, skills and ladder** — planned; P7.

Scope: classic core.

Creation/disband, invite/remove, grade permissions, member data, XP/level, money, skills, comments and ladder ranking.

Implementation prerequisites: [SYS-GUILD](#sys-guild).

Behavioral coupling: [SRV-003](#srv-003), [SRV-020](#srv-020), [SRV-022](#srv-022).

Named subfeatures and required behavior:

- **Empire change:** Selected [`change_empire.quest`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/change_empire.quest) blocks engagement/marriage, polymorph and guild membership, checks gold/item/cooldown, then calls `pc.change_empire`. Reconcile all empire-keyed character, spawn, language, guild, friend and quest state atomically.
- **Guild create/manage/master transfer/ranking, building/altar/melt/NPC and war join/bet/observer:** Creation fees/cooldowns, 15 grades and four permission bits, member contribution, treasury, skills, land and each war/bet state are individually testable.

Evidence: [CGuild](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/guild.cpp); [CGuildManager](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/guild_manager.cpp); [guild database operations](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/db/src/ClientManagerGuild.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### SRV-024

**Guild wars, reservations, scores and betting** — planned; P7.

Scope: classic core.

Field/arena/flag war modes, declarations, starts/ends, scores, observer maps, reservation, betting and results. Needs deterministic state transitions and settlement.

Implementation prerequisites: [SYS-GUILD](#sys-guild).

Behavioral coupling: [SRV-023](#srv-023), [SRV-005](#srv-005), [SRV-009](#srv-009).

Named subfeatures and required behavior:

- **Arena and guild-war observers:** `CArenaManager`, `CWarMap` and the player `observer_exit` command maintain spectator membership/counts and exclude observers from party/trade/item/combat paths. Spectator visibility and exit/restore location need explicit authority and privacy rules.
- **Guild create/manage/master transfer/ranking, building/altar/melt/NPC and war join/bet/observer:** Creation fees/cooldowns, 15 grades and four permission bits, member contribution, treasury, skills, land and each war/bet state are individually testable.

Evidence: [CGuild war operations](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/guild_war.cpp); [CWarMap / CWarMapManager](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/war_map.cpp); [CGuildManager war/reserve/bet](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/db/src/GuildManager.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### SRV-025

**Guild land, buildings, castle and siege** — planned; P7.

Scope: classic core + content.

Land ownership, object construction/upgrades/destruction, guild NPCs, power/refine buildings, castle frogs/towers/siege and cross-channel replication.

Implementation prerequisites: [SYS-GUILD](#sys-guild).

Behavioral coupling: [SRV-023](#srv-023), [SRV-005](#srv-005), [SRV-020](#srv-020).

Named subfeatures and required behavior:

- **Guild create/manage/master transfer/ranking, building/altar/melt/NPC and war join/bet/observer:** Creation fees/cooldowns, 15 grades and four permission bits, member contribution, treasury, skills, land and each war/bet state are individually testable.

Evidence: [building::CManager](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/building.cpp); [TLand / TObjectProto / TObject](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/common/building.h); [castle_* / siege](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/castle.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### SRV-057

**Guild marks and symbols** — planned; P7.

Scope: classic guild presentation contract.

Upload/download, CRC/index allocation and cross-channel synchronization. Replace filesystem image mutation with bounded validated storage, moderation and content delivery.

Implementation prerequisites: [SYS-GUILD](#sys-guild), [SYS-ADMIN](#sys-admin), [SYS-IMPORT](#sys-import).

Behavioral coupling: [SRV-023](#srv-023), asset storage, content moderation.

Evidence: [CGuildMarkManager](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/MarkManager.cpp); [GuildSymbolUpload / GuildMarkUpload / CRC lists](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/input_login.cpp); [HEADER_CG/GC_MARK and SYMBOL packets](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/packet.h); [Detailed source checklist and coverage limits](server-audit.md).

### CLI-016

**Guild membership, ranks, board, skills, war, marks, land, and buildings** — planned; P7.

Scope: Guild creation/invites, grade authority, members, comments, money/GSP, skills, wars/observer counts, emblems/symbol transfer, land and construction.

Split basic guild, war and land/building delivery while preserving the six classic pages. Acceptance checks every grade permission server-side, concurrent treasury changes, war lifecycle and sanitized bounded mark uploads.

Implementation prerequisites: [SYS-GUILD](#sys-guild).

Behavioral coupling: guild authority/economy, war/land/building systems, image moderation, [CLI-015](#cli-015), [CLI-029](#cli-029).

Evidence: [GuildWindow](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/bin/pack/root/uiguild.py); [CPythonNetworkStream::RecvGuild](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/PythonNetworkStreamPhaseGame.cpp).

### REF-013

**Guild management** — reference-only; P7.

Scope: QCX partial implementation; open-mt2 absent.

Create/member/rank/news/EXP paths exist, but invitation tracking, rejection and fan-out have explicit TODOs. Guild war/land is not complete.

Implementation prerequisites: [SYS-GUILD](#sys-guild).

Behavioral coupling: identity, persistent membership, roles/permissions, currency/EXP, presence, invitation lifecycle.

Evidence: [GuildManager](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/GuildManager.cs); [GuildInviteHandler.ExecuteAsync](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/PacketHandlers/Game/Guild/GuildInviteHandler.cs); [GuildRankPermissions](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/CorePluginAPI/Game/Types/Guild/GuildRankPermissions.cs).


## SYS-EMPIRE

Empire politics and conflicts

### SRV-046

**Monarch candidacy, election, treasury, tax and powers** — decision; P7.

Scope: classic regional system.

Candidates, votes, ruler assignment/removal, empire treasury/tax, notices, warp/transfer, mob summon and healing. Product decision needed because many later distributions removed or changed it.

Implementation prerequisites: [SYS-EMPIRE](#sys-empire).

Behavioral coupling: [SRV-003](#srv-003), [SRV-020](#srv-020), [SRV-047](#srv-047), [SRV-051](#srv-051).

Named subfeatures and required behavior:

- **Empire privileges, Three-Way War, arena/OX, Christmas, Easter, Ramadan, Halloween, Valentine, harvest and mystery-box events:** Every event has independent schedule/flag/content/reward/recovery needs. Some seasonal ride/costume items also depend on later-system profiles.

Evidence: [CMonarch](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/monarch.cpp); [CMonarch / election queries](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/db/src/Monarch.cpp); [RegisterMonarchFunctionTable](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/questlua_monarch.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### SRV-047

**Empires, language conversion and empire privileges** — planned; P7.

Scope: classic core.

Three empires, spawn/ownership rules, cross-empire chat transformation, character/guild/empire EXP/drop/gold privileges and empire-change constraints.

Implementation prerequisites: [SYS-EMPIRE](#sys-empire).

Behavioral coupling: [SRV-003](#srv-003), [SRV-022](#srv-022), [SRV-020](#srv-020).

Named subfeatures and required behavior:

- **Empire change:** Selected [`change_empire.quest`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/change_empire.quest) blocks engagement/marriage, polymorph and guild membership, checks gold/item/cooldown, then calls `pc.change_empire`. Reconcile all empire-keyed character, spawn, language, guild, friend and quest state atomically.
- **Empire privileges, Three-Way War, arena/OX, Christmas, Easter, Ramadan, Halloween, Valentine, harvest and mystery-box events:** Every event has independent schedule/flag/content/reward/recovery needs. Some seasonal ride/costume items also depend on later-system profiles.

Evidence: [CHARACTER::ChangeEmpire](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_change_empire.cpp); [CPrivManager](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/priv_manager.cpp); [ConvertEmpireText](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/empire_text_convert.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### SRV-048

**Three-way war, empire war maps and siege variants** — decision; P7.

Scope: classic event/content variant.

Empire selection, pass/sungzi maps, scores, bosses, warps, rewards and castle siege controls. Keep event state machine isolated and recoverable.

Implementation prerequisites: [SYS-EMPIRE](#sys-empire).

Behavioral coupling: [SRV-047](#srv-047), [SRV-005](#srv-005), [SRV-009](#srv-009), [SRV-049](#srv-049).

Named subfeatures and required behavior:

- **Context-specific revive:** `do_restart` has separate ordinary-map, guild-war, dungeon, Three-Way War and Sungzi/token paths, with different positions and HP/SP restoration. `ReviveInvisible(5)` supplies temporary post-revive protection on applicable paths. Preserve the selected rules instead of using a universal respawn.
- **Empire privileges, Three-Way War, arena/OX, Christmas, Easter, Ramadan, Halloween, Valentine, harvest and mystery-box events:** Every event has independent schedule/flag/content/reward/recovery needs. Some seasonal ride/costume items also depend on later-system profiles.

Evidence: [CThreeWayWar](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/threeway_war.cpp); [RegisterForkedFunctionTable](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/questlua_forked.cpp); [quest forked_road](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/forked_road.quest); [Detailed source checklist and coverage limits](server-audit.md).


## SYS-MARRIAGE

Marriage, wedding and divorce

### SRV-034

**Engagement, marriage, love points and couple items** — planned; P8.

Scope: classic social core.

Proposal/engagement, couple ring, married state, love-point updates, partner lookup/teleport and couple bonuses. Must persist atomically across both partners.

Implementation prerequisites: [SYS-MARRIAGE](#sys-marriage), [SYS-SKILL](#sys-skill).

Behavioral coupling: [SRV-003](#srv-003), [SRV-020](#srv-020), [SRV-028](#srv-028).

Named subfeatures and required behavior:

- **Emotes and mutual emote permission:** `cmd_info` exposes kiss, slap, French kiss, clap, cheers, dances and expressive emotes; `emotion_allow` and `do_emotion` handle paired consent. Motion/effect availability and restrictions need generated action IDs and two-client tests.
- **Character sex change:** Selected `item_change_sex.quest` checks level, engagement/marriage, polymorph and cooldown, consumes item 71048 and calls `pc.change_sex`. Decide what happens to equipped items, appearance assets and class restrictions transactionally.
- **Empire change:** Selected [`change_empire.quest`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/change_empire.quest) blocks engagement/marriage, polymorph and guild membership, checks gold/item/cooldown, then calls `pc.change_empire`. Reconcile all empire-keyed character, spawn, language, guild, friend and quest state atomically.
- **Couple-ring acquisition, proposal/engagement, dress and fee checks, ceremony conversion/gifts, guest list/join, music/dark/snow, partner proximity/love points, ring/bonus cleanup, mutual and unilateral divorce:** Selected `couple_ring.quest` and [`marriage_manage.quest`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/marriage_manage.quest), native `marriage` APIs, `TMarriage::NearCheck` and `WeddingMap` establish these as distinct scenario branches.

Evidence: [marriage::CManager / TMarriage](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/marriage.cpp); [CMarriage / CMarriageManager](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/db/src/Marriage.cpp); [quest marriage_manage](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/marriage_manage.quest); [Detailed source checklist and coverage limits](server-audit.md).

### SRV-035

**Wedding map instance and ceremony controls** — planned; P8.

Scope: classic social core + content.

Private ceremony map, guests, start/end, music/weather/client commands, exit and cleanup.

Implementation prerequisites: [SYS-MARRIAGE](#sys-marriage), [SYS-ACTOR](#sys-actor), [SYS-UI](#sys-ui).

Behavioral coupling: [SRV-034](#srv-034), [SRV-005](#srv-005), [SRV-028](#srv-028).

Named subfeatures and required behavior:

- **Couple-ring acquisition, proposal/engagement, dress and fee checks, ceremony conversion/gifts, guest list/join, music/dark/snow, partner proximity/love points, ring/bonus cleanup, mutual and unilateral divorce:** Selected `couple_ring.quest` and [`marriage_manage.quest`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/marriage_manage.quest), native `marriage` APIs, `TMarriage::NearCheck` and `WeddingMap` establish these as distinct scenario branches.

Evidence: [marriage::WeddingMap / WeddingManager](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/wedding.cpp); [marriage join_wedding / wedding_dark / wedding_snow / wedding_music](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/questlua_marriage.cpp); [wedding map](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/map/metin2_map_wedding_01/Setting.txt); [Detailed source checklist and coverage limits](server-audit.md).

### SRV-036

**Divorce and forced marriage break** — planned; P8.

Scope: classic social core.

Mutual or unilateral separation costs/rules and GM forced break. Clear both partner records, affects and wedding state transactionally.

Implementation prerequisites: [SYS-MARRIAGE](#sys-marriage), [SYS-ADMIN](#sys-admin).

Behavioral coupling: [SRV-034](#srv-034), [SRV-020](#srv-020).

Named subfeatures and required behavior:

- **Couple-ring acquisition, proposal/engagement, dress and fee checks, ceremony conversion/gifts, guest list/join, music/dark/snow, partner proximity/love points, ring/bonus cleanup, mutual and unilateral divorce:** Selected `couple_ring.quest` and [`marriage_manage.quest`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/marriage_manage.quest), native `marriage` APIs, `TMarriage::NearCheck` and `WeddingMap` establish these as distinct scenario branches.

Evidence: [marriage_remove](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/questlua_marriage.cpp); [do_break_marriage](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/cmd_gm.cpp); [HEADER_GD/DG_BREAK_MARRIAGE](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/common/tables.h); [Detailed source checklist and coverage limits](server-audit.md).

### CLI-017

**Marriage, lover state, paired emotions, and wedding presentation** — planned; P8.

Scope: Lover name/points and affect display, partner interactions, kiss/slap paired motions, wedding dress mode and wedding map/event feedback.

Explicitly retain this classic screen/animation family. Acceptance synchronizes two rigs at paired-motion markers, handles refusal/distance/disconnect and verifies wedding attire/map presentation.

Implementation prerequisites: [SYS-MARRIAGE](#sys-marriage).

Behavioral coupling: marriage state, events/instances, [CLI-024](#cli-024), [CLI-025](#cli-025), [CLI-026](#cli-026).

Evidence: [CPythonNetworkStream::RecvLoverInfoPacket](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/PythonNetworkStreamPhaseGame.cpp); [enum EName](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/GameLib/RaceMotionData.h).


## SYS-EVENT

Seasonal and live events

### SRV-049

**OX quiz, seasonal events and live event flags** — planned; P6.

Scope: classic liveops + content.

OX quiz, Christmas, Easter, Halloween, Ramadan, Valentine, Olympics, harvest, invasions, mystery boxes, moonlight/holiday drops and weekly/event flags. Each event needs schedules, idempotent start/stop and recovery.

Implementation prerequisites: [SYS-EVENT](#sys-event).

Behavioral coupling: [SRV-028](#srv-028), [SRV-051](#srv-051), scheduler, [SRV-011](#srv-011).

Named subfeatures and required behavior:

- **Empire privileges, Three-Way War, arena/OX, Christmas, Easter, Ramadan, Halloween, Valentine, harvest and mystery-box events:** Every event has independent schedule/flag/content/reward/recovery needs. Some seasonal ride/costume items also depend on later-system profiles.

Evidence: [COXEventManager](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/OXEvent.cpp); [Christmas event state](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/xmas_event.cpp); [quest event_easter](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/event_easter.quest); [Detailed source checklist and coverage limits](server-audit.md).

### MOD-055

**Event timezone, catch-up and overlap policy** — planned; P6.

Scope: modernization.

UTC instants with explicit business timezone/DST, missed schedules, offline advancement, cancellation/generation and overlapping event semantics.

Implementation prerequisites: [SYS-EVENT](#sys-event).

Evidence: [Event timezone, catch-up and overlap policy](development-and-admin.md).


## SYS-EXT

Later official and fork-specific systems

### SRV-033

**Flame dungeon and level 99-105 quest line** — planned; P9.

Scope: later content profile.

Nemere/Razador-era map and quest content demonstrates that this archive is broader than an early classic baseline; include only by explicit release/profile decision.

Implementation prerequisites: [SYS-EXT](#sys-ext).

Behavioral coupling: [SRV-030](#srv-030), [SRV-028](#srv-028), [SRV-011](#srv-011).

Named subfeatures and required behavior:

- **Devil Tower, catacomb, spider floors, Heaven's Cave/Blue Dragon/Dragon Lair and Flame Dungeon:** These are separate access, instance, encounter, timer and reward graphs; source presence does not prove a complete selected pack.

Evidence: [quest flame_dungeon](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/flame_dungeon.quest); [quest main_quest_flame_lv99](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/main_quest_flame_lv99.quest); [map settings](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/map/metin2_map_n_flame_dungeon_01/Setting.txt); [Detailed source checklist and coverage limits](server-audit.md).

### SRV-044

**Dragon Soul alchemy and dedicated inventory** — planned; P9.

Scope: later expansion core.

Grade/step/strength refinement, extraction, deck activation, effects and dedicated inventory. Explicitly profile as post-classic expansion content.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-STATS](#sys-stats), [SYS-ECONOMY](#sys-economy), [SYS-UI](#sys-ui).

Behavioral coupling: [SRV-013](#srv-013), [SRV-015](#srv-015), [SRV-010](#srv-010).

Named subfeatures and required behavior:

- **Dragon Soul extraction/decks, blend, hair and costume utilities:** `ITEM_DS`, `ITEM_SPECIAL_DS`, `ITEM_EXTRACT`, `ITEM_BLEND` and `ITEM_HAIR` have live handlers, but belong to later-feature profiles unless the chosen baseline includes them.

Evidence: [DSManager](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/DragonSoul.cpp); [CHARACTER Dragon Soul operations](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_dragonsoul.cpp); [Dragon Soul definitions](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/dragon_soul_table.txt); [Detailed source checklist and coverage limits](server-audit.md).

### SRV-045

**Costumes, belt inventory, energy and hair** — planned; P9.

Scope: mixed optional/later systems.

Costume body/hair slots, belt capacity, energy crystal, hairstyle quests/items and related buffs. Break into independently selectable content capabilities.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-STATS](#sys-stats), [SYS-ACTOR](#sys-actor), [SYS-ECONOMY](#sys-economy), [SYS-UI](#sys-ui).

Behavioral coupling: [SRV-013](#srv-013), [SRV-014](#srv-014), [SRV-010](#srv-010).

Named subfeatures and required behavior:

- **Dragon Soul extraction/decks, blend, hair and costume utilities:** `ITEM_DS`, `ITEM_SPECIAL_DS`, `ITEM_EXTRACT`, `ITEM_BLEND` and `ITEM_HAIR` have live handlers, but belong to later-feature profiles unless the chosen baseline includes them.

Evidence: [CBeltInventoryHelper](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/belt_inventory_helper.h); [COSTUME / BELT / ENERGY item handling](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_item.cpp); [quest energy_system](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/energy_system.quest); [Detailed source checklist and coverage limits](server-audit.md).

### SRV-055

**Auction, wish and sale boards** — decision; P9.

Scope: disabled compile-time variant.

Code and packet/command branches exist, but __AUCTION__ is commented out on master. Do not count it as baseline gameplay. If selected, redesign transactional listings, escrow, settlement and expiry.

Implementation prerequisites: [SYS-EXT](#sys-ext).

Behavioral coupling: [SRV-013](#srv-013), [SRV-020](#srv-020), [SRV-052](#srv-052).

Evidence: [commented __AUCTION__](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/common/service.h); [AuctionManager under __AUCTION__](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/auction_manager.cpp); [AuctionManager under __AUCTION__](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/db/src/AuctionManager.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### SRV-056

**Speed Server experience schedules** — decision; P9.

Scope: present but incomplete baseline hook.

Master has schedules and quest API but the EXP hook is commented. Branch e488f5a2444bae9bcb7ac30e1fcab0165d14d3e9 enables it; treat as branch-only evidence, not master behavior.

Implementation prerequisites: [SYS-EXT](#sys-ext).

Behavioral coupling: [SRV-007](#srv-007), [SRV-028](#srv-028), schedule service.

Evidence: [CSpeedServerManager](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/SpeedServer.cpp); [RegisterSpeedServerFunctionTable](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/questlua_speedserver.cpp); [commented SpeedServer EXP hook](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_battle.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### CLI-019

**Costume, belt, Dragon Soul, and energy extensions** — planned; P9.

Scope: Costume body/hair slots, belt inventory, Dragon Soul inventory/decks/activation/refine, energy gauge and related tooltips/effects.

The Europe profile compiles four switches, which proves conditional client availability only. Deliver and accept each extension independently with real server data, persistence, visuals and reconnect behavior.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-ECONOMY](#sys-economy), [SYS-STATS](#sys-stats).

Behavioral coupling: extended equipment definitions, Dragon Soul and energy rules, [CLI-005](#cli-005), [CLI-007](#cli-007), [CLI-014](#cli-014), [CLI-028](#cli-028).

Evidence: [ENABLE_DRAGON_SOUL_SYSTEM](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/Locale.h); [DragonSoulRefineWindow](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/bin/pack/root/uidragonsoul.py).

### REF-018

**Lycan class** — planned; P9.

Scope: Gameforge-domain live-product wiki expansion; absent from both emulator class/skill registries.

The community-maintained Gameforge-domain wiki indexes the live class; both inspected registries contain only the four earlier classes.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-ACTOR](#sys-actor), [SYS-MOTION](#sys-motion), [SYS-SKILL](#sys-skill).

Behavioral coupling: character creation, claw equipment, animation set, skill registry, combat balance, UI.

Evidence: [Lycan/Instinct](https://en-wiki.metin2.gameforge.com/index.php?title=Lycan&oldid=48334); [JobEnum](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/core/enum/JobEnum.ts); [EPlayerClass](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/CorePluginAPI/Game/Types/Players/EPlayerClass.cs).

### REF-019

**Belt equipment and conditional inventory** — planned; P9.

Scope: Gameforge-domain live-product wiki system; open-mt2 schema-only partial; QCX absent.

An enum and belt slot do not implement belt storage/refinement.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-ECONOMY](#sys-economy).

Behavioral coupling: [REF-006](#ref-006), refinement, sockets, capacity rules, atomic unequip.

Evidence: [General/Belt refinement/Belt sockets/Belt storage slots](https://en-wiki.metin2.gameforge.com/index.php?title=Belt_System&oldid=58127); [BELT_INVENTORY](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/core/enum/WindowTypeEnum.ts).

### REF-020

**Costume, weapon skin and transmutation** — planned; P9.

Scope: Gameforge-domain live-product wiki system; body/hair equipping partial in both emulators.

Neither emulator implements weapon skins, timed expiry, bonus transfer/reroll, set bonus or full transmutation.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-ACTOR](#sys-actor), [SYS-ECONOMY](#sys-economy).

Behavioral coupling: [REF-006](#ref-006), appearance projection, timed items, bonuses, set effects, destructive transform transaction.

Evidence: [Costume slots/bonuses/transfer/transmutation](https://en-wiki.metin2.gameforge.com/index.php?title=Costume_System&oldid=58122); [Equipment costumeBody/costumeHair](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/core/domain/entities/game/inventory/Equipment.ts); [Equipment COSTUME/HAIR cases](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/PlayerUtils/Equipment.cs).

### REF-021

**Shoulder sash combination and absorption** — planned; P9.

Scope: Gameforge-domain live-product wiki system; absent from both emulators.

Require preview plus exact item-instance locks for every destructive operation.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-ACTOR](#sys-actor), [SYS-STATS](#sys-stats), [SYS-ECONOMY](#sys-economy).

Behavioral coupling: [REF-006](#ref-006), appearance projection, item destruction, refinement outcomes, bonus aggregation.

Evidence: [Improving/Bonus absorption/removal/transfer](https://en-wiki.metin2.gameforge.com/index.php?title=Shoulder_Sash_System&oldid=60665).

### REF-022

**Pet lifecycle, growth and skills** — planned; P9.

Scope: Gameforge-domain live-product wiki system; absent from both emulators.

System pets are persistent progression entities, distinct from simple cosmetic follower pets.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-MOUNT](#sys-mount), [SYS-SKILL](#sys-skill).

Behavioral coupling: entity identity, pet seal item, authoritative wall-clock expiry, EXP, skills, appearance, reconnect.

Evidence: [Pet duration/feeding/EXP/evolution/skills](https://en-wiki.metin2.gameforge.com/index.php?title=Pet_System&oldid=61698).

### REF-023

**Dragon Stone Alchemy** — planned; P9.

Scope: Gameforge-domain live-product wiki system; open-mt2 constants only; QCX absent.

The compatibility enum is not an alchemy implementation.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-ECONOMY](#sys-economy), [SYS-STATS](#sys-stats).

Behavioral coupling: [REF-006](#ref-006), dedicated inventory, daily limits, refinement RNG, timed activation, derived bonuses.

Evidence: [Dragon Stone inventory/sets/upgrades/activation](https://en-wiki.metin2.gameforge.com/index.php?title=Dragon_Stone_Alchemy&oldid=60545); [DRAGON_SOUL_INVENTORY](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/core/enum/WindowTypeEnum.ts).

### REF-024

**Energy system** — planned; P9.

Scope: Gameforge-domain live-product wiki system; open-mt2 point wiring only; QCX absent.

A registered point does not implement production, activation or expiration.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-STATS](#sys-stats), [SYS-ECONOMY](#sys-economy).

Behavioral coupling: [REF-006](#ref-006), item destruction, craft RNG, authoritative timer, derived-stat pipeline.

Evidence: [Energy fragments/crystal/timed multiplier](https://en-wiki.metin2.gameforge.com/index.php?title=Energy_System&oldid=60423); [PointsEnum.ENERGY/ENERGY_END_TIME](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/core/domain/entities/game/player/delegate/PlayerPoints.ts).

### REF-025

**Mailbox with currency and item attachments** — planned; P9.

Scope: Gameforge-domain live-product wiki system; absent from both emulators.

Design attachments as escrow rows, not serialized client payloads.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-SOCIAL](#sys-social), [SYS-ECONOMY](#sys-economy), [SYS-OPS](#sys-ops).

Behavioral coupling: identity lookup, durable messages, Yang/Won, escrowed item, fees, atomic idempotent claim, expiry/capacity.

Evidence: [Mailbox Function/Additional Information](https://en-wiki.metin2.gameforge.com/index.php?title=Mailbox&oldid=61368).

### REF-026

**Offline/premium shop and market search** — planned; P9.

Scope: Gameforge-domain live-product wiki system; online-only partial in open-mt2; QCX player shop absent.

Use serializable/idempotent buy and claim reducers; connected avatar state must not own the listing.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-TRADE](#sys-trade), [SYS-OPS](#sys-ops).

Behavioral coupling: [REF-009](#ref-009), persistent listings independent of presence, Won, tax, entitlement/timer, search index, claim/close recovery.

Evidence: [Offline shop/management/tax/Yang-Won](https://en-wiki.metin2.gameforge.com/index.php?title=Private_Shop&oldid=61856); [PrivateShopService](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/game/app/service/PrivateShopService.ts); [TODO implement player shop](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/World/Shop.cs).

### REF-027

**Champion levels and Yohara progression** — planned; P9.

Scope: Gameforge-domain live-product wiki progression; absent from both emulators.

Model as a distinct progression layer with an explicit migration/content policy.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-PROGRESS](#sys-progress), [SYS-WORLD](#sys-world).

Behavioral coupling: level 120 cap, promotion prerequisites, Champion EXP, separate stats/skills, content gates, Yohara maps.

Evidence: [(Champion) Levels](https://en-wiki.metin2.gameforge.com/index.php?title=Experience&oldid=61873).

### REF-028

**Sung Mahi's Will and Yohara instances** — planned; P9.

Scope: Gameforge-domain live-product wiki progression; absent from both emulators.

A map and mobs do not implement the tower; it requires durable stage/objective/re-entry state.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-INSTANCE](#sys-instance), [SYS-STATS](#sys-stats).

Behavioral coupling: [REF-027](#ref-027), four will stats, instance ownership, objective state machine, restrictions, ranking, [REF-025](#ref-025).

Evidence: [Sung Mahi's Will/Structure/Rewards](https://en-wiki.metin2.gameforge.com/index.php?title=Sung_Mahi_Tower&oldid=61933).

### REF-029

**Elemental damage and resistance** — planned; P9.

Scope: Gameforge-domain live-product wiki feature; partial constants/calculation hooks only.

Centralize typed channels and resistance caps; enum presence alone does not establish full behavior.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-STATS](#sys-stats), [SYS-ECONOMY](#sys-economy).

Behavioral coupling: [REF-004](#ref-004), [REF-006](#ref-006), six typed channels, mob affinity, weapon element upgrades, derived stats.

Evidence: [Elemental damage on weapons](https://en-wiki.metin2.gameforge.com/index.php?title=Bonuses&oldid=60352); [RESIST_FIRE/ELEC/WIND/ICE/EARTH/DARK](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/core/enum/ApplyTypeEnum.ts); [TODO implement resist against fire etc.](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/World/Entities/Entity.cs).

### REF-030

**Auto-Hunt** — decision; P9.

Scope: Gameforge-domain live-product wiki optional automation; absent from both emulators.

If adopted, automate ordinary validated intents under server policy; never create a privileged bypass path.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-AI](#sys-ai), [SYS-SKILL](#sys-skill), [SYS-OPS](#sys-ops).

Behavioral coupling: [REF-001](#ref-001), [REF-004](#ref-004), [REF-005](#ref-005), [REF-006](#ref-006), target filters, entitlements, normal action validation.

Evidence: [Auto-Hunt target/focus/potion/skill/resurrection controls](https://en-wiki.metin2.gameforge.com/index.php?title=Auto-Hunt&oldid=58119).

### REF-031

**Set Bonus** — planned; P9.

Scope: Gameforge-domain live-product wiki system; absent from both emulators.

Temporary set bonuses depend on eligible multi-item combinations and must disappear when any required timed/equipped item stops qualifying.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-STATS](#sys-stats), [SYS-ITEM](#sys-item).

Behavioral coupling: [REF-006](#ref-006), [REF-020](#ref-020), [REF-022](#ref-022), mounts, timed items, derived-stat recomputation.

Evidence: [General/item-count thresholds](https://en-wiki.metin2.gameforge.com/index.php?title=Set_Bonus&oldid=61837).

### REF-032

**Set Effect** — planned; P9.

Scope: Gameforge-domain live-product wiki system; absent from both emulators.

This permanent equipment transform is distinct from REF-031 temporary set combinations; both may be active.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-STATS](#sys-stats), [SYS-ACTOR](#sys-actor), [SYS-ECONOMY](#sys-economy).

Behavioral coupling: [REF-006](#ref-006), refinement, catalyst, equipment transformation, set aggregation, effect removal.

Evidence: [equipment transformation/two- and three-item thresholds](https://en-wiki.metin2.gameforge.com/index.php?title=Set_Effect&oldid=58178).

### REF-033

**Soul Relic lifecycle and triggered bonuses** — planned; P9.

Scope: Gameforge-domain live-product wiki system; absent from both emulators.

Class relics have irreversible installation, activation duration, recharge and up to four bonuses with combat/mount/drop triggers.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-STATS](#sys-stats), [SYS-ITEM](#sys-item), [SYS-COMBAT](#sys-combat), [SYS-MOUNT](#sys-mount).

Behavioral coupling: [REF-004](#ref-004), [REF-005](#ref-005), [REF-006](#ref-006), [REF-018](#ref-018), repeatable quests, authoritative duration, trigger/cooldown engine.

Evidence: [Soul Relics/Crafting/Adding Bonuses/Recharging](https://en-wiki.metin2.gameforge.com/index.php?title=Relic_System&oldid=50531).

### REF-034

**Binding and timed unbinding** — planned; P9.

Scope: Gameforge-domain live-product wiki system; absent from both emulators.

Every item-mutating reducer must enforce bound/unbinding state; no single UI check is sufficient.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-ITEM](#sys-item), [SYS-TRADE](#sys-trade), [SYS-ECONOMY](#sys-economy).

Behavioral coupling: [REF-006](#ref-006), trade, drop, shop, refinement, enchantment, character deletion, scheduled deadlines.

Evidence: [soulbound restrictions/72-hour unbinding](https://en-wiki.metin2.gameforge.com/index.php?title=Binding_System&oldid=60675).

### REF-035

**Aura Outfit absorption and progression** — planned; P9.

Scope: Gameforge-domain live-product wiki system; absent from both emulators.

The page describes 250 levels across six stages and absorbed accessory values; persist the source and projected value audibly.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-STATS](#sys-stats), [SYS-ACTOR](#sys-actor), [SYS-ECONOMY](#sys-economy).

Behavioral coupling: [REF-006](#ref-006), [REF-020](#ref-020), appearance projection, accessory destruction, bonus aggregation, EXP/stage tables.

Evidence: [Absorption/Upgrading/Appearance](https://en-wiki.metin2.gameforge.com/index.php?title=Aura_Outfit_System&oldid=60698).

### REF-036

**Gaya currency and rotating market** — planned; P9.

Scope: Gameforge-domain live-product wiki system; absent from both emulators.

Generate offers server-side and make currency conversion and purchases atomic.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-ECONOMY](#sys-economy).

Behavioral coupling: currency ledger, [REF-006](#ref-006), craft RNG, per-player offers, authoritative refresh, row unlock entitlement.

Evidence: [currency acquisition/Gaya Market/refresh](https://en-wiki.metin2.gameforge.com/index.php?title=Gaya_System&oldid=61530).

### REF-037

**Monster Card missions, collection and account bonuses** — planned; P9.

Scope: Gameforge-domain live-product wiki system; absent from both emulators.

The audited revision says the five-star summon remained in development; do not record it as completed live behavior without newer evidence.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-PROGRESS](#sys-progress), [SYS-COMBAT](#sys-combat), [SYS-AUTH](#sys-auth).

Behavioral coupling: account-scoped state, [REF-003](#ref-003), [REF-010](#ref-010), [REF-011](#ref-011), polymorph, map/content lookup, reset/reshuffle policy.

Evidence: [Procedure/Collection/Achievement Bonus/Transformation](https://en-wiki.metin2.gameforge.com/index.php?title=Monster_Card_System&oldid=47611).

### REF-038

**Merc system presence and unresolved rules** — decision; P9.

Scope: Gameforge-domain live-product index entry; destination missing and rules unverified.

The system name and UI control are evidenced, while the dedicated wiki link is missing. Reward chests that cite Merc System do not define behavior.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-DATA](#sys-data).

Behavioral coupling: dedicated follow-up audit, explicit product rules, missions/operations, rewards, timers, UI.

Evidence: [Systems -> Merc System red link](https://en-wiki.metin2.gameforge.com/index.php?title=Template:Main_Page/EquipmentAndOthersV2&oldid=57872); [Merc System button](https://en-wiki.metin2.gameforge.com/index.php?title=User_Interface&oldid=61696).

### REF-039

**Titles unlock and active presentation** — planned; P9.

Scope: Gameforge-domain live-product wiki system; absent from both emulators.

Store unlock provenance and selected title authoritatively; Godot renders only validated presentation metadata.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-PROGRESS](#sys-progress), [SYS-UI](#sys-ui).

Behavioral coupling: account/character policy, achievements, events, server-owned unlock provenance, appearance projection.

Evidence: [General/title origins/equip UI](https://en-wiki.metin2.gameforge.com/index.php?title=Titles&oldid=60744).

### REF-040

**Item enchantment and sixth/seventh bonuses** — planned; P9.

Scope: Gameforge-domain live-product wiki feature; absent workflow in both emulators.

The audited rules separate 1-5 and 6/7 addition/reroll paths. Model them as separate transactions and keep pending 24-hour work durable.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-ECONOMY](#sys-economy), [SYS-STATS](#sys-stats).

Behavioral coupling: [REF-006](#ref-006), [REF-029](#ref-029), ordered bonus slots, exact item lock, materials, fallible outcome, durable pending timer.

Evidence: [1/5 bonuses/6/7 bonuses/elemental weapon upgrades](https://en-wiki.metin2.gameforge.com/index.php?title=Bonuses&oldid=60352).

### REF-041

**Glove slot, Demon Stones and Sung Ma stats** — planned; P9.

Scope: Gameforge-domain live-product wiki equipment family; absent from both emulators.

The license, socket family and randomized default values require more than adding an equipment enum.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-STATS](#sys-stats), [SYS-PROGRESS](#sys-progress), [SYS-ECONOMY](#sys-economy).

Behavioral coupling: [REF-006](#ref-006), [REF-027](#ref-027), slot unlock, socket compatibility, four Sung Ma stats, refinement.

Evidence: [license gate/Demon Stone sockets/SungMa STR-RES-VIT-INT/Serpent Gloves](https://en-wiki.metin2.gameforge.com/index.php?title=Gloves&oldid=56270).

### REF-042

**Talismans, elements and Will variants** — planned; P9.

Scope: Gameforge-domain live-product wiki equipment family; absent from both emulators.

Classic elemental talismans and later Will talismans share a slot but depend on different progression layers.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-STATS](#sys-stats), [SYS-ECONOMY](#sys-economy).

Behavioral coupling: [REF-006](#ref-006), [REF-027](#ref-027), [REF-029](#ref-029), [REF-040](#ref-040), equipment slot, refinement.

Evidence: [elemental talismans/Will talismans/random element/Sung Ma](https://en-wiki.metin2.gameforge.com/index.php?title=Talismans&oldid=61378).

### REF-043

**Precision Champion passive skill** — planned; P9.

Scope: Gameforge-domain live-product wiki secondary skill; absent from both emulators.

Register and test this passive as combat behavior; a book item or UI entry is not an implementation.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-SKILL](#sys-skill), [SYS-PROGRESS](#sys-progress).

Behavioral coupling: [REF-004](#ref-004), [REF-005](#ref-005), [REF-027](#ref-027), skill-book progression, enemy block calculation.

Evidence: [Champion requirement/book progression/block reduction](https://en-wiki.metin2.gameforge.com/index.php?title=Precision_(Skill)&oldid=57871).

### REF-044

**Serpent equipment crafting and progression** — planned; P9.

Scope: Gameforge-domain live-product wiki content family; absent from both emulators.

Keep this equipment family distinct from the Serpent Temple instance; a linked map or item constant implements neither progression nor recipes.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-ECONOMY](#sys-economy), [SYS-STATS](#sys-stats).

Behavioral coupling: [REF-006](#ref-006), [REF-027](#ref-027), [REF-028](#ref-028), [REF-040](#ref-040), [REF-041](#ref-041), craft recipes, class equipment, random base stats, refinement curves.

Evidence: [class weapon/armour crafting and upgrade uses](https://en-wiki.metin2.gameforge.com/index.php?title=Serpent_Design&oldid=56642); [level-120 Serpent Gloves +0 through +9](https://en-wiki.metin2.gameforge.com/index.php?title=Gloves&oldid=56270).

### REF-045

**Main-page map and dungeon destination index** — reference-only; P9.

Scope: Gameforge-domain community-maintained presence index; detailed rules not audited.

The exact grouped targets and display aliases are in docs/rebuild/evidence/reference-inventory.json. Heart of Greed is linked but missing at the audited revision.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-WORLD](#sys-world), [SYS-INSTANCE](#sys-instance).

Behavioral coupling: [REF-003](#ref-003), map geometry, spawns, content gates, dungeon orchestration, events, reconnect/reset/reward rules.

Evidence: [86 destinations in 11 groups](https://en-wiki.metin2.gameforge.com/index.php?title=Template:Main_Page/World_MapV2&oldid=61395).

### REF-046

**Switchbot policy decision** — decision; P9.

Scope: unverified official status; fork-specific until sourced.

Do not label this original or official based on private-server familiarity. No checked Gameforge-domain wiki feature page or emulator implementation established it.

Implementation prerequisites: [SYS-EXT](#sys-ext), [SYS-ECONOMY](#sys-economy), [SYS-QA](#sys-qa).

Behavioral coupling: explicit product policy, official source if parity is claimed, item bonus reroll, automation limits, anti-abuse/economy review.

Evidence: [complete-tree search: no switchbot implementation](https://github.com/willianmarquess/open-mt2/tree/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src); [complete-tree search: no switchbot implementation](https://github.com/MeikelLP/quantum-core-x/tree/ddab58ba493dfcedefd8b265513950f865edfffc/src).

### MOD-052

**Rules-driven optional expansion isolation** — planned; P9.

Scope: modernization.

Later official systems and fork-specific convenience plugins get explicit schema/content/migration/permission boundaries, not undocumented compile flags.

Implementation prerequisites: [SYS-EXT](#sys-ext).

Evidence: [Rules-driven optional expansion isolation](architecture-and-delivery.md).


## SYS-OPS

Operations and recovery

### CLI-030

**Locale/build variants, integrity checks, diagnostics, and release boundaries** — reference-only; P0.

Scope: Europe profile switches, Debug/Release/Distribute differences, optional OpenID/locale paths, CRC/process/XTrap/HShield legacy hooks, logs/profiling/console and packaged content boundaries.

A compile define is availability evidence only. Replace obsolete anti-cheat/integrity code through a separate threat model; keep powerful diagnostics local, authorized and absent from player exports. Audit PCK contents and run real export smoke tests per platform.

Implementation prerequisites: [SYS-OPS](#sys-ops).

Behavioral coupling: release manifests, local development tooling, [CLI-029](#cli-029), [CLI-031](#cli-031).

Evidence: [LOCALE_SERVICE_EUROPE](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/Locale.h); [ItemDefinitionGroup](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/UserInterface.vcxproj).

### REF-017

**Observability, plugins and world benchmark** — reference-only; P0.

Scope: QCX partial tooling reference.

The tick listener creates but does not observe its histogram, so treat it as a seam, not finished telemetry. Add reducer latency/rejections, subscriptions, scheduler lag and economy flows.

Implementation prerequisites: [SYS-OPS](#sys-ops).

Behavioral coupling: metrics boundary, stable labels, load fixtures, authorization for inspection.

Evidence: [PacketOperationListener](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Plugins/PrometheusPlugin/PacketOperationListener.cs); [ClientConnectedListener](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Plugins/PrometheusPlugin/ClientConnectedListener.cs); [WorldUpdateBenchmark.World_Tick](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Game.Benchmarks/Benchmarks/WorldUpdateBenchmark.cs).

### MOD-044

**Metrics, logs, alerts and slow-reducer diagnostics** — planned; P0.

Scope: modernization.

Tick/transaction/row/subscription/content-version metrics with correlation IDs; no credentials in logs; actionable health/load/expiry alerts.

Implementation prerequisites: [SYS-OPS](#sys-ops).

Evidence: [Metrics, logs, alerts and slow-reducer diagnostics](development-and-admin.md).

### MOD-045

**Auth/game/content coordinated backup and restore** — partial; P0.

Scope: modernization.

Define RPO/RTO, preserve keys, restore isolated snapshots, run actual clients and account login; backups alone are not proven recoverability.

Implementation prerequisites: [SYS-OPS](#sys-ops).

Evidence: [Auth/game/content coordinated backup and restore](development-and-admin.md).

### MOD-046

**Schema/content migration planner and rehearsal** — planned; P0.

Scope: modernization.

Validate removed IDs and old quest/item versions, dry-run migrations, backward/forward compatibility and rollback/forward repair.

Implementation prerequisites: [SYS-OPS](#sys-ops).

Evidence: [Schema/content migration planner and rehearsal](architecture-and-delivery.md).

### MOD-048

**External-service outbox and idempotent delivery** — planned; P0.

Scope: modernization.

Email/support/billing integrations outside gameplay reducers, authenticated scoped requests, idempotent consumption and retry/reconciliation.

Implementation prerequisites: [SYS-OPS](#sys-ops).

Evidence: [External-service outbox and idempotent delivery](architecture-and-delivery.md).

### MOD-053

**Monorepo quality gates and dependency provenance** — partial; P0.

Scope: modernization.

Pinned toolchains/libraries and source hashes, focused lint/parser/unit/integration checks, generated binding/content audits and maintained notices.

Implementation prerequisites: [SYS-OPS](#sys-ops).

Evidence: [Monorepo quality gates and dependency provenance](development-and-admin.md).

### MOD-056

**Content trust keys and rollback compatibility** — planned; P0.

Scope: modernization.

Verify signatures against configured trust roots, support key rotation/revocation, distinguish compatible artifact rollback from schema/content forward repair.

Implementation prerequisites: [SYS-OPS](#sys-ops).

Evidence: [Content trust keys and rollback compatibility](development-and-admin.md).

### MOD-057

**External integration retries and reconciliation console** — planned; P0.

Scope: modernization.

Persist retry/backoff and dead-letter status, correlate external outcomes, expose partial failures and reconcile without duplicate item/currency grants.

Implementation prerequisites: [SYS-OPS](#sys-ops).

Evidence: [External integration retries and reconciliation console](development-and-admin.md).


## SYS-ADMIN

Admin and support surface

### SRV-051

**GM commands, privileges and live administration** — planned; P3.

Scope: development/admin tooling.

234 parsed command rows include player commands, debugging, teleport, spawn/item grants, quest/event flags, reload, moderation, guild/war/monarch controls and shutdown. Rebuild as authenticated audited admin APIs/tools; never expose raw command or Lua execution to players.

Implementation prerequisites: [SYS-ADMIN](#sys-admin).

Behavioral coupling: [SRV-002](#srv-002), role-based authorization, [SRV-052](#srv-052).

Named subfeatures and required behavior:

- **Chat block/mute and vote-block moderation:** `AFFECT_BLOCK_CHAT`, `block_chat`, `block_chat_list` and `vote_block_chat` implement timed moderation across cores. Rebuild this as permissioned sanctions with actor/reason/expiry/appeal evidence rather than conflating it with a player's whisper block.

Evidence: [cmd_info / interpret_command](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/cmd.cpp); [GM command handlers](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/cmd_gm.cpp); [runtime command privilege overrides](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/conf/CMD); [Detailed source checklist and coverage limits](server-audit.md).

### REF-014

**Developer and GM command framework** — reference-only; P3.

Scope: both emulators useful; authorization must be redesigned.

open-mt2 states all players can execute commands. QCX checks groups but exempts some powerful-looking commands. Preserve the registry/docs lesson, not these defaults.

Implementation prerequisites: [SYS-ADMIN](#sys-admin).

Behavioral coupling: authenticated operator identity, server-side authorization, audit log, safe argument validation.

Evidence: [CommandManager](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/game/app/command/CommandManager.ts); [CommandManager.Register/CanUseCommand](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Commands/CommandManager.cs); [CommandNoPermission](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/Commands/ReloadPermissionsCommand.cs).

### MOD-037

**Operator roles and audited administration API** — planned; P3.

Scope: modernization.

Separate support/moderation/content/economy/deploy roles enforced at backend, operator MFA/sessions, reasons/action IDs and protected private views.

Implementation prerequisites: [SYS-ADMIN](#sys-admin).

Evidence: [Operator roles and audited administration API](development-and-admin.md).

### MOD-038

**Account support and sanctions console** — planned; P3.

Scope: modernization.

Exact lookup, session inspection/revoke, mute/ban expiry/unban/report history, permission-denial tests and privacy-aware retention.

Implementation prerequisites: [SYS-ADMIN](#sys-admin).

Evidence: [Account support and sanctions console](development-and-admin.md).

### MOD-039

**Character inspection, unstuck and repair tools** — planned; P3.

Scope: modernization.

Preview destination and version, inspect quests/inventory provenance, apply bounded authorized repair with before/after audit and idempotency.

Implementation prerequisites: [SYS-ADMIN](#sys-admin).

Evidence: [Character inspection, unstuck and repair tools](development-and-admin.md).

### MOD-040

**Economy investigation and grant/compensation audit** — planned; P3.

Scope: modernization.

Trace item/currency origin/transfers/consumption; approved compensation exactly once, anti-duplication investigation and bounded queries.

Implementation prerequisites: [SYS-ADMIN](#sys-admin).

Evidence: [Economy investigation and grant/compensation audit](development-and-admin.md).

### MOD-041

**Content staging, diff and activation controls** — planned; P3.

Scope: modernization.

Validated immutable manifests, dry-run spawn/shop/drop/event patches and compatibility-aware publish/rollback; no raw hot edits to generated assets.

Implementation prerequisites: [SYS-ADMIN](#sys-admin).

Evidence: [Content staging, diff and activation controls](development-and-admin.md).

### MOD-042

**Live event scheduler and intervention tools** — planned; P3.

Scope: modernization.

Rates/notices/seasonal events/tournaments/guild war/wedding support; server time, automatic expiry, start/stop retry and restart recovery.

Implementation prerequisites: [SYS-ADMIN](#sys-admin).

Evidence: [Live event scheduler and intervention tools](development-and-admin.md).

### MOD-043

**Moderation reports and interaction blocking tools** — planned; P3.

Scope: modernization.

Scoped chat evidence, safe text/name rendering, reports/appeals, access audit and action/rate/retention policy.

Implementation prerequisites: [SYS-ADMIN](#sys-admin).

Evidence: [Moderation reports and interaction blocking tools](development-and-admin.md).

### MOD-054

**Production operator limits and separated audit evidence** — planned; P3.

Scope: modernization.

Per-action amount/rate caps, expiring emergency access and configurable second-operator controls for high-impact production actions; tamper-evident audit under a separate permission boundary.

Implementation prerequisites: [SYS-ADMIN](#sys-admin).

Evidence: [Production operator limits and separated audit evidence](development-and-admin.md).


## SYS-DEV

Development and authoring tools

### REF-015

**Data conversion and validated content authoring** — reference-only; P1.

Scope: tooling reference in both emulators.

Build checked generators that fail on duplicate IDs, invalid references/probabilities and non-finite positions; never ship source archives.

Implementation prerequisites: [SYS-DEV](#sys-dev).

Behavioral coupling: pinned source data, schemas, ID registries, hash manifests, server/client generated outputs.

Evidence: [atlasConverter/attrConverter/mobProtoConverter/motion/drop/spawn converters](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/tools); [ParserService](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/Services/ParserService.cs); [AtlasProvider.GetAsync](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/Services/AtlasProvider.cs).

### REF-016

**Generated packet and command documentation** — reference-only; P1.

Scope: QCX tooling reference.

Use the pattern for SpacetimeDB bindings, reducer catalogs and admin documentation; legacy packet formats themselves are not a Godot dependency.

Implementation prerequisites: [SYS-DEV](#sys-dev).

Behavioral coupling: typed protocol schema, command/reducer metadata, build-time validation.

Evidence: [PacketSerializerGenerator](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Core.Networking.Generators/PacketSerializerGenerator.cs); [PacketDocsGenerator/CommandDocsGenerator](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Executables/DocsGenerator/Program.cs).

### MOD-006

**Content browser and reverse dependency explorer** — planned; P1.

Scope: modernization.

Search ID/path and explain source, dependencies, affected definitions and generated outputs; reveal unsupported/unreferenced records.

Implementation prerequisites: [SYS-DEV](#sys-dev).

Evidence: [Content browser and reverse dependency explorer](development-and-admin.md).

### MOD-011

**Animation, mount and equipment inspection laboratory** — planned; P1.

Scope: modernization.

Scrub clips and blends; show bind/bones/hit windows, swap equipment and mounted rigs; deterministic captures and deformation probes.

Implementation prerequisites: [SYS-DEV](#sys-dev).

Evidence: [Animation, mount and equipment inspection laboratory](development-and-admin.md).

### MOD-014

**Map/spawn/portal authoring and overlays** — partial; P1.

Scope: modernization.

Versioned patches on top of generated data; collision/terrain/portal/regen visualization, reachability checks and isolated map fixtures.

Implementation prerequisites: [SYS-DEV](#sys-dev).

Evidence: [Map/spawn/portal authoring and overlays](development-and-admin.md).

### MOD-018

**Quest debugger, branch coverage and restart simulator** — planned; P1.

Scope: modernization.

Inspect flags, waits, timers and events; scenario each branch/reward and recover stuck quests through authorized tools, not raw production row edits.

Implementation prerequisites: [SYS-DEV](#sys-dev).

Evidence: [Quest debugger, branch coverage and restart simulator](development-and-admin.md).

### MOD-032

**Combat and economy balance workbench** — planned; P1.

Scope: modernization.

Diff formula results, XP routes/drop distributions/sinks/sources, seeded cases and abnormal funnels; intentional balance changes reviewed.

Implementation prerequisites: [SYS-DEV](#sys-dev).

Evidence: [Combat and economy balance workbench](development-and-admin.md).

### MOD-050

**Developer editor docks over reusable CLI APIs** — partial; P1.

Scope: modernization.

Godot content/quest/map/motion inspectors invoke the same compiler libraries/commands used by CI; MCP local only.

Implementation prerequisites: [SYS-DEV](#sys-dev).

Evidence: [Developer editor docks over reusable CLI APIs](development-and-admin.md).


## SYS-QA

Scenario, fidelity and performance laboratory

### SRV-054

**Security, abuse controls and protocol hardening** — partial; P0.

Scope: modernization requirement.

The source explicitly says many public exploits are unpatched. Use it as behavioral evidence only. Validate finite/ranged inputs, ownership, phase, distance, cooldown, replay/idempotency and authorization; fuzz parsers and test adversarial sequences.

Implementation prerequisites: [SYS-QA](#sys-qa).

Behavioral coupling: all reducer/action IDs, threat model, rate limiting.

Current project: Existing local and exported two-client scenario runners cover the prototype; adversarial/full-game/load/Windows evidence remains work.

Evidence: [Bugfixes / Exploits warning](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/README.md); [CInputMain::Analyze and action validation](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/input_main.cpp); [CSequence](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/sequence.cpp); [Detailed source checklist and coverage limits](server-audit.md).

### MOD-022

**Classic UI reference gallery and input scenarios** — partial; P0.

Scope: modernization.

Fixed-size screenshots plus focus/IME/drag/keyboard scenarios; distinguish exact image pixels from complete original font/behavior parity.

Implementation prerequisites: [SYS-QA](#sys-qa).

Evidence: [Classic UI reference gallery and input scenarios](development-and-admin.md).

### MOD-030

**Two-client scenario runner with normal authenticated intents** — partial; P0.

Scope: modernization.

Reusable account/role fixtures, real subscriptions/rendered input, reducer rejection, concurrency/disconnect/reconnect; isolated database ownership.

Implementation prerequisites: [SYS-QA](#sys-qa).

Evidence: [Two-client scenario runner with normal authenticated intents](development-and-admin.md).

### MOD-031

**Network impairment and deterministic behavior traces** — planned; P0.

Scope: modernization.

Latency/jitter/reordered application intents/retries/tab suspension; seeded rule inputs and authoritative trace IDs, not video as simulation proof.

Implementation prerequisites: [SYS-QA](#sys-qa).

Evidence: [Network impairment and deterministic behavior traces](development-and-admin.md).

### MOD-033

**Performance and load laboratory** — planned; P0.

Scope: modernization.

2/20/100 initial test tiers on named hardware, reducer/row/bandwidth/client-frame/memory percentiles; capacity claims only after measurement.

Implementation prerequisites: [SYS-QA](#sys-qa).

Evidence: [Performance and load laboratory](development-and-admin.md).

### MOD-049

**Abuse limits and adversarial gameplay validation** — planned; P0.

Scope: modernization.

Rate/input/size bounds, unauthorized subscription/reducer attempts, bots/speed/range/item exploits; backend evidence instead of trusting old anti-cheat.

Implementation prerequisites: [SYS-QA](#sys-qa).

Evidence: [Abuse limits and adversarial gameplay validation](architecture-and-delivery.md).


## SYS-WEB

Browser delivery and portability

### CLI-032

**Modern rendering, streaming, Web compatibility, and performance budgets** — partial; P1.

Scope: Godot materials/lighting/shadows, batching/culling/LOD, distance animation, section streaming/cache, WebGL delivery, context/audio recovery, accessibility and resolution support while preserving classic visual rhythm.

Optimize against explicit visual error and timing bounds. Acceptance names hardware/browser/resolution/entity/effect density and records frame percentiles, memory, entry bytes/time and cache behavior alongside original-reference captures; no fidelity claim from load success alone.

Implementation prerequisites: [SYS-WEB](#sys-web).

Behavioral coupling: [CLI-021](#cli-021), [CLI-023](#cli-023), [CLI-026](#cli-026), [CLI-027](#cli-027), [CLI-028](#cli-028), [CLI-031](#cli-031).

Current project: Working Compatibility/single-threaded Web core plus section packs; broader lifecycle/cache/memory/performance qualification remains work.

Evidence: [CGrannyMaterial::CreateFromGrannyMaterialPointer](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/EterGrnLib/Material.cpp); [CMapOutdoor::Render](https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/GameLib/MapOutdoorRender.cpp).

### MOD-035

**Browser streaming cache and lifecycle robustness** — partial; P1.

Scope: modernization.

Priorities/cancel/retry, manifest integrity/versioning, bounded memory/storage, quota eviction, offline failure UI, tab suspension/context loss.

Implementation prerequisites: [SYS-WEB](#sys-web).

Evidence: [Browser streaming cache and lifecycle robustness](development-and-admin.md).

### MOD-036

**Audio, input, accessibility and portability matrix** — planned; P1.

Scope: modernization.

User-gesture audio, focus/cursor/IME, scalable readable UI, remapping/settings; actual Windows and supported-browser evidence alongside Linux.

Implementation prerequisites: [SYS-WEB](#sys-web).

Evidence: [Audio, input, accessibility and portability matrix](development-and-admin.md).


## SYS-RELEASE

Release and compatibility qualification

### MOD-047

**Automated reproducible release and package audit** — partial; P10.

Scope: modernization.

Actual exports, dependency/hash audits, no MCP/evaluator/secrets/source archives, intended database/issuer checks and real target-platform sessions.

Implementation prerequisites: [SYS-RELEASE](#sys-release).

Evidence: [Automated reproducible release and package audit](development-and-admin.md).

### MOD-051

**Content completeness and release-profile acceptance** — planned; P10.

Scope: modernization.

Every selected map/item/mob/skill/quest/UI/locale category has converted-and-verified counts and missing-record resolution; no blanket full-game claim.

Implementation prerequisites: [SYS-RELEASE](#sys-release).

Evidence: [Content completeness and release-profile acceptance](architecture-and-delivery.md).

### MOD-058

**Content distribution and replacement manifest** — planned; P10.

Scope: release content provenance.

For each selected asset and dependency, record the distribution basis/evidence, an authored replacement or a profile exclusion. Hash provenance alone is not distribution permission. Qualify the production release against this manifest and resolve unknown entries before that release; this planning record does not alter current development exports.

Implementation prerequisites: [SYS-RELEASE](#sys-release), [SYS-DATA](#sys-data), [SYS-IMPORT](#sys-import).

Behavioral coupling: [SYS-IMPORT](#sys-import), [SYS-DATA](#sys-data), [SYS-RELEASE](#sys-release).

Evidence: [Content compiler contract](development-and-admin.md); [Third-party provenance and distinct asset/code terms](../third-party.md).
