# Architecture and delivery design

These are proposed boundaries for the full rebuild. The implemented system is
described in [architecture.md](../architecture.md); the distinction matters.
The [catalog](feature-catalog.md) and [dependency data](plan.json) identify the
work required to reach these boundaries.

## Preserve experience, replace implementation where useful

Preserve class identities, weapon feel, movement/camera conventions, animation
timing, combat feedback, town layouts, item/economy relationships, progression,
social rituals and recognizable UI. Match a selected rules/content profile
instead of accidentally combining incompatible eras. Bugs, insecure packet
trust, old rendering APIs, unbounded scripts and hard-coded deployment topology
are not fidelity requirements.

| Classic contract to preserve | Modern implementation approach | Proof required |
| --- | --- | --- |
| Click/keyboard movement, camera and attack rhythm | Authoritative motion with bounded navigation; optional sequenced local prediction and correction | Route/collision fixtures plus delay/jitter tests and observed feel |
| Characters, equipment, skills and effects | Generated Godot resources and shared motion/action IDs | Deformation, grip, attack/cast timing and exported visual comparisons |
| Item/stat/skill/quest behavior | Typed versioned definitions and transaction-owned state | Formula fixtures, complete branch scenarios and invalid-intent rejection |
| Familiar windows and input behavior | Modular Godot controllers and original selected artwork | Screenshots, focus/IME/drag tests, original-client reference observations |
| Shared world, party, guild, marriage | Explicit membership/state machines and access-controlled replication | Two or more real clients, permissions, disconnect and restart coverage |
| Persistent progress and stable operations | Versioned migrations, auditable actions, measured workloads and restore drills | Old-save migration and tested recovery with intended client builds |

Do not add gameplay conveniences that change progression or economy merely
because they are common in modern games. Mark autoplay, offline shops,
cross-channel markets and similar changes as explicit rules-profile decisions.

## Proposed module and service boundaries

Keep a modular monorepo and initially one gameplay database. Auth remains the
existing separate service. A future operator/web service and content builder
have specific jobs; this plan does not require a microservice for every feature.

| Boundary | Responsibilities and state |
| --- | --- |
| Accounts and sessions | Stable account/character identifiers, selected character, controlling connection, permissions and token lifecycle |
| World and movement | Map/instance/channel membership, positions, region membership, navigation, transitions and presence |
| Definitions and content | Immutable versioned records and compatibility manifests; no arbitrary host file loading from gameplay reducers |
| Combat and progression | Action sequences, targeting, damage, statuses, cooldowns, resources, XP/level and skill learning |
| Items and economy | Unique item instances, placement, ownership, attributes, equipment, atomic currency/item movement and provenance |
| NPCs, quests and instances | Interaction checks, persisted event/state/action execution, timers, objectives, access and encounter lifecycle |
| Social | Chat audiences, friends/block lists, parties, guilds, wars, marriage and their permissions |
| Live operations | Authorized event/configuration changes, sanctions, audit, recovery and metrics |
| Client presentation | Scene/controllers per screen/system, immutable definition lookup, replicated-state adapters, animation/audio/VFX and local preferences |
| Offline tools | Source inventory, import/compile, authoring, validation, visual fixtures, schema/content diff and release artifacts |

Use tables with stable primary keys and indexes matching actual queries.
Separate persistent character data, transient presence, private inventory/quest
state, and public appearance. The current public `player` row exposes offline
fields and gold; redesign visibility before expanding it. RLS, validated reducers
and subscription readiness are independent concerns. Voluntary client filtering
is not access control. Test whether the pinned runtime revokes established
reads on expiry; do not assume the current JWT renewal test proves it.

SpacetimeDB reducers provide transaction boundaries and isolated execution;
long-lived mutable globals, filesystem access and arbitrary network side effects
are unsuitable for gameplay state. Use persisted tables and bounded scheduled
work. See [reducer semantics](https://spacetimedb.com/docs/functions/reducers/).
The project stays on the pinned 2.8.3 runtime/SDK combination until a tested
upgrade is justified; current website examples do not establish compatibility
with every feature on that pin.

## Shared technical contracts to establish early

1. **Identifiers and versions.** Distinguish account, character, entity instance,
   item instance, definition, map, instance, channel, quest and content release.
   Keep old Metin2 vnums as source IDs where useful, with explicit namespaces.
   Never derive runtime ownership from a display name or an unchecked client ID.
2. **Numbers and time.** Currency/items/XP use bounded integers and checked
   arithmetic. Validate finite movement values, normalized directions and
   admissible rates. Document rounding/order for formulas and time units.
   Server timestamps own cooldowns and deadlines; UI countdowns are estimates.
3. **Commands and outcomes.** Typed intents include necessary entity/version or
   action IDs. Report stable rejection codes and presentation keys. Critical
   multi-step operations have expected versions and idempotency/consumption
   rules; retries cannot duplicate a reward, payment, wedding or transfer.
4. **Replication.** Subscribe to authorized current world/nearby public state
   and scoped private state; wait for subscription application before exposing
   playable controls. Separate short-lived effect/action events from durable
   state, with bounded retention and sequence tracking.
5. **Definitions.** One versioned compilation creates client-facing descriptions
   and trusted server rules. Hidden drop tables or administrative data are not
   automatically included in the player pack. A matching hash is compatibility
   evidence, not a security boundary against modified clients.
6. **Timers and recovery.** Persist deadline and state-machine generation. On
   execution, verify current state, ownership and generation. Stale timers cannot
   close a new shop, pay a reward twice or resume an already finished instance.
7. **Observability.** Use structured correlation/action IDs, bounded metrics and
   audit events. Redact credentials and account-private details. Separate debug
   sampling from durable economic/admin provenance; avoid logging every movement
   row forever.
8. **Migrations.** Treat schema, definitions, auth/signing state and client
   compatibility together. Preserve item/quest IDs or publish explicit mappings.
   Rehearse on isolated snapshots, define rollback/forward-repair behavior and
   verify clients after restore.

## Stateful features need explicit lifecycle design

| Feature | Minimum state-machine contract | Failure cases to exercise |
| --- | --- | --- |
| Map/instance transfer | Requested → validated/reserved → destination loading → active, with timeout/return policy | Disconnect before/after commit, missing pack, full destination, old subscription, duplicate request; exactly one active location |
| Direct trade | Invite → open offers → both lock same revision → atomic commit or cancel | Offer changes invalidate acceptance; item use/sale/move while reserved; full bag, currency overflow, distance/death/logout |
| Player shop | Draft → open with reserved stock → atomic purchases → close/settle | Two buyers of last item, owner disconnect, expiry, map/channel move, inventory full and recovery |
| Quest | Persisted state + event version + waits/timers → validated transition/reward | Duplicate kill/item events, reconnect during dialogue, daily reset, abandoned branch and definition upgrade |
| Dungeon/war | Forming → entry → active phases → result → cleanup | Late/rejoining players, disconnecting leader, timeout, restart, reward replay, stale membership |
| Marriage/wedding | Proposal/eligibility → mutual agreement → ceremony reservation → ceremony → married → divorce/termination | Withdrawn consent, disconnect, double booking, item/fee consumption, guest entry, partner deletion and stale rings/bonuses |
| Admin repair/grant | Authorized preview → action with reason/version → atomic mutation + audit | Retry, stale target, insufficient privilege, partial external notification and recovery |

The exact marriage thresholds, partner restrictions, bonuses and divorce rules
come from the chosen source/content profile. The architecture must support
those rules without silently guessing them from a screenshot or a packet name.

## Interest management, channels and performance

Start by separating public presence from private persistent rows, adding
map/instance keys and replacing demonstrated full scans with indexed lookups.
Measure before partitioning the database. Use active-region simulation and
bounded AI/timer work; avoid updating every offline character every tick.
Subscriber delivery cost, row size and GDScript decode/main-thread cost count
alongside Rust reducer time. SpacetimeDB
[subscriptions](https://spacetimedb.com/docs/clients/subscriptions/) replicate
matching state; they do not choose our spatial scope or gameplay privacy rules.

A logical channel can initially be a membership field in one database if
authorization and cost permit. Separate databases introduce non-atomic
cross-database transfers and global naming/party/guild coordination. Make that
a measured architecture decision with a durable handoff protocol, ownership
leases and reconciliation; do not claim seamless cross-server transactions.
Economy, marriage and guild state must have one authority during a handoff.

Client scene chunks, server collision tiles, simulation regions and network
interest cells need not share dimensions. They must share content coordinates,
map identity and compatible boundaries. Client asset readiness must never
grant a new authoritative location.

## Delivery phases and gates

Phase numbers indicate an order of integration, not a promise that one person
can complete a full MMORPG in a few sprints. Work on independent tools and
client presentation can run in parallel after the relevant contracts stabilize.

| Phase | Deliverable | Dependency/exit gate |
| --- | --- | --- |
| P0: parity and foundation | Version/profile ledger; source/feature coverage; stable IDs and definition schemas; current-state gaps; performance baseline | Catalog mapped, unknowns explicit, initial rules and reference fixtures identified |
| P1: content and motion factory | Generalized compiler, race/motion metadata, weapon attachment, original enemy fixture, asset/visual inspector | Shared action IDs, deformed clips and equipment checked in Godot/Web/native; unsupported records fail visibly |
| P2: complete combat loop | Actual stats/XP/level, target/combo/skill foundation, original mobs/AI, full item-instance model and loot rules | Two characters fight, equip, progress, die/reconnect and cannot duplicate rewards; formula and timing fixtures |
| P3: starter-town experience | NPCs, shops/refine, starter/biologist-style quest capabilities, quest tooling, all classic class/sex motion fixtures and entry options | Defined town-to-field route complete, every branch/reward recoverable; content references and UI validated |
| P4: world generalization | Second map first, transfer/streaming, nav/layers, spawn/event authoring, remaining selected maps in batches | Interrupted transfer and return with two clients; every selected map has coordinates/collision/spawn/portal and content coverage |
| P5: economy and ordinary social | Direct trade, player shops, storage, crafting/refine detail, chat/whisper/friends/blocking, parties and PvP/alignment | Concurrent transfer/last-item races, scoped reads, permissions and disconnect behavior; admin audit/support tools |
| P6: instances and advanced combat | Dungeon framework/content, bosses, horse/mounts, fishing/mining/polymorph and selected auxiliary skills | Party entry/rejoin, progression/reward timers, mounted combat and gathering scenarios with restart recovery |
| P7: guilds and empire systems | Guild roles/progression/skills, treasury/storage as selected, land/buildings, war modes/ranking, empire conflict/monarch features | Multi-party permission/economy/war scenarios and restored schedules; relevant optional source systems adjudicated |
| P8: marriage and complete classic content | Proposal/ceremony/guests/rings/love bonuses/divorce; remaining events, quests, items, UI and content rows | Full ceremony-to-divorce lifecycle, all baseline catalog entries accepted or explicitly reclassified with evidence |
| P9: modern/variant expansion packs | Later official systems and selected modern conveniences from the extension ledger | Each profile has complete server/client/data/tooling coverage; classic profile remains testable |
| P10: release qualification | Sustained load, accessibility/localization, platform matrix, recovery and operator runbooks | Declared performance/support targets met, clean normal exports, real internet/platform tests and restore drill |

Operations, security, profiling and tools start in P0/P1 and advance with every
phase; P10 is their final qualification gate. Full-game completion is **not**
reached by delivering only P0–P3. Later official/variant scope is kept visible
even if the first playable release uses a classic profile.

Introduce referenced schema and fixture contracts before the full feature phase:
for example, horse item/quest references need stable IDs and motion fixtures
while P3 quests are built, even though the complete horse gameplay gate is P6.
Cross-system references must fail visibly rather than silently granting stub
rewards or activating an unfinished feature.

The next implementation slice after this plan is P1 plus its minimal P0
prerequisites: shared definitions/motion manifest, general animation import,
visible equipped sword, one original hostile mob and real timing feedback.
It should produce both a playable improvement and the automation used for
the remaining classes/monsters. Leveling and the first NPC/quest route follow.

## Work packages and realistic planning

Use four parallel tracks: server/rules; Godot presentation; content/tools; and
QA/operations. They can be people or focused agent tasks, but one integration
owner must reconcile IDs, timing, bindings, content versions and acceptance.
Do not count an independently generated screen or reducer as an integrated
feature. Server/client/content changes land as reviewable vertical slices.

For every catalog row, create a work package containing:

- Source evidence, exact observable behavior and intentional differences.
- Dependencies, state/permission model and definition/content IDs.
- Client/UI/assets, server reducers/tables, authoring/admin needs and migration.
- Two-client happy path, rejection, concurrency, disconnect/reconnect and restart
  scenarios appropriate to the system.
- Visual/performance fixtures and platforms actually exercised.
- Evidence links and remaining gaps; mark complete only when the specified
  behavior is integrated, not merely because an asset or enum exists.

Estimate after the representative fixtures establish throughput. First measure
time per rig/motion family, enemy archetype, map type, quest API family and UI
screen; then combine those rates with inventory counts, integration effort and
unknown-format risk. Broad reuse can reduce repetitive work substantially,
but formula parity, quest semantics, rendering fidelity and multiplayer failure
cases still require engineering and review. This is a large multi-phase rebuild;
SpacetimeDB replaces substantial networking/persistence plumbing, not the game
rules, content compiler, Godot client or live-operations work.
