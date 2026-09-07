# Rebuild implementation status

This execution ledger begins the implementation phase after the source-backed
planning deliverable. It complements the [full rebuild plan](../full-rebuild-plan.md)
and its canonical [feature catalog](plan.json); it does not replace, collapse,
or reclassify that scope.

## Scope retained

At `8b3ecd3`, the canonical plan contains **194 feature records across 41
systems**, sequenced from P0 through P10. The first active work package is a
small P0/P1 vertical slice. It is not a declaration that P0 or P1 is complete,
and it does not reduce the remaining catalog to this slice.

| Area | Catalog relationship | Execution status | Evidence in this ledger |
| --- | --- | --- | --- |
| Full rebuild scope | 194 catalog records / 41 systems | Retained | `docs/rebuild/plan.json`; `docs/rebuild/validation.md` |
| P0 foundations | Definitions, stable IDs, profile/coverage and trust boundaries | Selected Warrior/Sword+0/Wild Dog slice accepted locally; full P0 remains incomplete | Work packages and verification below |
| P1 content and motion factory | Compiler, actor/motion metadata, equipment attachment and enemy fixture | Selected fixture accepted locally; full P1 and public qualification remain incomplete | Work packages and verification below |

## First active P0/P1 slice

The work uses one normalized, versioned content identity to produce both
client-facing presentation data and server-trusted definitions. A local visual
attachment must remain a projection of subscribed server-owned equipment; it
must never grant a weapon, a stat change, or an action.

| Work package | Owner | Depends on | Status | Deliverable |
| --- | --- | --- | --- | --- |
| P0 definition and compiler contract | Content/tools owner | Selected profile and pinned source inputs | Accepted for the selected local fixture; broader definition/content coverage pending | Deterministic normalized records, dependency/provenance report, explicit unsupported records and generated client/server payload boundary |
| P1 warrior and starter-sword vnum 10 fixture | Content/tools owner | P0 contract; Blender conversion environment | Accepted locally with generated records, native fixture and actual-PCK audits | One named warrior presentation record, selected clips, starter-sword vnum 10 attachment metadata and reproducible output identity |
| P1 WildDog 101 fixture | Content/tools owner + server/rules owner | P0 contract; selected source fixture | Accepted locally with generated records, lifecycle and actual-PCK evidence | One hostile-mob presentation/definition record with explicit unsupported-source handling |
| P0 public appearance / trusted actions | Server/rules owner | Stable definitions and identifiers | Accepted for the local slice with authenticated authority and lifecycle evidence | Public appearance projection separate from private equipment state; authoritative action definitions keyed to the same action IDs as presentation events |
| P1 actor and equipment integration | Client actor owner | Generated warrior/equipment payload; subscribed appearance state | Accepted locally in editor, native and independent browser/Linux clients | `player_actor` integration that selects visual equipment from subscribed state, including visible starter sword vnum 10, without local authority |
| Slice integration and acceptance | Integration/QA owner | All preceding packages | Local fixture accepted; normal export, current Windows and public P1 qualification pending | Reproducible fixture run, two-client evidence and recorded limitations |

Owners are execution roles for assignment and handoff. These statuses accept one
bounded local fixture; they do not mark the full P0/P1 catalog phases complete.

## Current P1 artifact evidence

The generated `p0-warrior-dog` manifest currently records source-content hash
`c43d781897983618ae669121a5eda067ec2f309a522c2326030c4e0d8a3e5a37`,
gameplay-definition hash
`44b8f276a6dc3bf566886f898f30aa3359b72be7dabe644c59d0a9dbb8226c69`,
and presentation-output hash
`2bcd691596bfb76f90359955a6469eda9a5a2d65045d00452f3b66fcc699c839`.
It lists the three intended GLBs and 27 Warrior/13 Wild Dog motion records.
`make content-validate` accepts the generated profile/action pair. A local
native `test-actors` fixture reported 44 checks and rendered captures that were
reviewed for local visual plausibility. This is not an original-client visual
comparison or full actor/content coverage. Per-client handoff also records 52
source-freeze headless/native actor checks and 27 intro checks.

## Scoped P1 verification evidence

The isolated `mt2-p1-final` environment used auth at `127.0.0.1:8186` and game
at `127.0.0.1:13223`. Its fresh two-account authenticated suite passed 94/94
checks, including private inventory reads, public equipped-weapon projection,
source-derived delayed hits, exactly-once rewards, disconnect removal, switching
and reconnect. The accepted server/client definition contract was
`definition_profile = p0-warrior-dog`, definition hash
`44b8f276a6dc3bf566886f898f30aa3359b72be7dabe644c59d0a9dbb8226c69`, and
protocol 4 bindings schema hash
`f29b2e1a35cc5bfe87b185bf2f0db354dfeb5f5bcdac851d4b97386b2f7e2317`.
The report is `.local/p1/accounts-final.json`.

The follow-up combat-ordering change passes 30 Rust tests. Deterministic unit
coverage exercises both directions of cross-side lethal hits within one 50 ms
tick and the documented exact-timestamp tie; this precise scheduling boundary
was not forced through a timing-sensitive live test. The complementary fresh
authenticated Godot run passed the existing 94 authority, lifecycle,
cancellation and exactly-once checks against the disposable
`mt2-p1-hit-order-20260906` database. Its report is
`.local/p1/accounts-hit-order-20260906.json`.

The final P1 checkpoint tool suite passed 101 tests, all configured lint passed,
and the current Rust suite passes 30 tests. The earlier combined check record
predates the two combat-ordering regressions and includes 28 Rust checks, four
auth checks and plan validation of 194 records across 41 systems. Evidence is
retained in `.local/p1/test-tools-post-review.log`, `.local/p1/lint-final.log`
and `.local/p1/make-checks-final.log`.

Isolated instrumented P1 exports passed actual-PCK inspection: Web checked 711
packaged paths and Linux checked 1,514. Both loaded the three generated models,
all 40 declared clips, and all 197 UI images against exact decoded RGBA hashes;
the Web export also passed all 20 Yongan world-section audits. Their inventories
contained no GR2/source archives, Granny/Blender runtime, server action artifact,
MCP bridge or secret material. The manifests are
`.local/p1/web/build-manifest.json` and `.local/p1/native/build-manifest.json`.
They include the test probe for isolated QA and do not establish normal-export
packaging by themselves.

Godot MCP inspection of the local fixture observed the Warrior, equipped sword,
key-2 swing, death/return/repeat behavior and three original tabs/settings
without replacing the open editor state. The gallery report and captures are in
`.local/p1/mcp-gallery/`. This is local fixture/editor evidence only.

Completed scoped runs include 52 source-freeze headless/native actor checks, the
94/94 authenticated server checks above, 30 Rust tests, 101 Python tool tests and
the final 111-check local browser/Linux run in
`.local/p1/browser-source-row-final/report.json`. The two real session timers
renewed from `10454→248832` ms in Web and `60749→301232` ms in Linux while both
identities, self actors and peer actors remained present; no engine errors were
recorded.

An earlier visible run exposed real DOM mouse/WASD input during its intended
idle period. The first isolated rerun then exposed a QA-only snapshot race: a
deferred local actor briefly made the native convenience `server_position`
appear as `[0,0,0]` while the subscribed own-player row was already correct.
The runner now uses the finite online own-identity row as its authoritative
baseline and keeps rendering as a separate final assertion. A post-run audit of
all 55 retained trace samples found zero XYZ drift for both accounts and zero DOM
input events; see `.local/p1/browser-source-row-final/xyz-drift-audit.json`.

The P1 development build was published without deleting data as release
`20260906T204513591109Z` on `mt2-p1-v4`; HTTPS discovery, database availability
and the served manifest passed. The workstation HTTP record is
`.local/p1/public-http-report.json`. Public exported-gameplay qualification
remains pending. The preceding `mt2-accounts-v3` database remains stored but is
no longer routed publicly.

This accepts the bounded local fixture. Full P0/P1 scope, normal-export package
qualification, current Windows execution and original-client visual/behavioral
parity remain incomplete.

## Bounded P2 progression slice

The next vertical slice implements the male Warrior portion of `SRV-007` on top
of the accepted character (`SRV-003`), combat (`SRV-009`) and Wild Dog
(`SRV-011`) fixtures. It also connects the bounded status presentation from
`CLI-006`/`CLI-010` and adds default-deny development commands. This is a
partial implementation of those catalog records, not completion of P2.

| Work package | Current status | Implemented boundary |
| --- | --- | --- |
| Source-backed definitions | Integrated and compiler/build validated | Original EXP table through compiled level 120, runtime cap 99, normal level-delta percentages, exact single-precision quarter thresholds, male Warrior initial/growth constants, Wild Dog 101 level and 15 EXP reward, potion vnums 27001/27002 |
| Authoritative progression | Integrated; live level-up run accepted | Owner-private row, level/EXP quarters, points, random HP/SP growth, alive-only quarter refill, automatic potion stack/bag/drop delivery, capped combat grants and closed stat allocation |
| Non-party kill sharing | Integrated; live two-account split/reconnect accepted | Per-monster-life registered-damage/overkill ledger, same-live-connection and source approximate-50 m eligibility, 20% highest-contributor reserve plus 80% single-precision proportional shares |
| Status/client protocol | Positive-XP exported Chrome/Linux path accepted | Protocol 5, owner-only progression and feedback subscriptions, server-authoritative `next_exp`, `C` status panel, reducer-backed point allocation, ordinary five-kill first-quarter/VIT interaction and real refresh persistence |
| Development commands | Default-deny path live-tested; privileged path pending explicit approval | Private `/help`, capability-gated `/xp` and raise-only `/level`, bounded feedback/audit/receipts, action/argument replay binding, validation and rate limits |

The canonical P2 compile records source-content hash
`28ef6604c09daf6df371fdde1b09ae8b8b508302ba8bade5c38918b824d49c8f`
and gameplay-definition hash
`7719eec33753a367bb594e38181331dec359c5ec235db53b57d563d72bffbb35`.
The three regenerated GLBs retain P1 presentation-output hash
`2bcd691596bfb76f90359955a6469eda9a5a2d65045d00452f3b66fcc699c839`.
Generated protocol-5 Godot bindings use schema hash
`c3e5a8acbff528458936815c8a8903830e35a86b7573a1452cc302e011328fb3`.
The P2 Rust suite passes 40 tests, including exact quarter/cap behavior,
contribution splits and approximate-distance boundaries. Content extraction and
malformed-artifact tests validate the same thresholds at Python and Rust build
boundaries. The current combined Python tool suite passes 121 tests, all lint
groups pass individually, and the 194-record/41-system plan check passes.

The disposable training database `mt2-p2-progression-20260906` runs a
default-deny protocol-5 module. Its final two-account headless run passes 298
checks in `.local/p2/accounts-progression-20260907T0349.json`. The 105-check
base verifies progression read privacy, exact initial Warrior state, no-point
and foreign-character stat rejection, an ordinary Wild Dog's exact +15 EXP,
and progression continuity through leave/reconnect. The shared test uses an
untouched character, verifies registered-damage splits of 70/35 to 11/4 EXP and
75/35 to 11/3 EXP on separate monster lives, reconnects between lives, and
proves owner privacy and no old-life credit reuse. Four freshly authenticated
five-kill segments preserve the production 12-second respawn and reach exact
75/150/225 EXP quarter states before level 2 with zero carried EXP. They also
verify exact automatic-potion counts, bounded HP/SP growth and VIT increasing
maximum HP by 40 without healing current HP. The fixture establishes the
authoritative out-of-range precondition before its delayed-hit checks; all base,
shared and progression-segment assertions pass.

The fresh default-deny Yongan database `mt2-p2-yongan-20260906` was published
without deleting data from artifact SHA-256
`c7a9535d10a8642fc55d7b46d92e76512248a9c0d0208ecdc3dfdc05f283d8b8`.
It targets `metin2_map_a1`, protocol 5 and the definition hash above. P2 exports
read back `Connected to Yongan.`, the exact gameplay-definition hash, nine loaded
map chunks and no content error. Actual-PCK audits pass for 795 Web and 1,598
Linux paths, all 225 selected UI images, all 40 declared clips and all 20
isolated Yongan sections; see `.local/p2/export-root-audit.json`. The accepted
exported Chrome/Linux progression-combat evidence passes 199 checks in
`.local/p2/browser-positive-progression-fresh-read/report.json`. It uses ordinary
movement and 20 actual Space attacks for five normally respawning Wild Dog
lives, proves exact +15 XP per life and the first 75-EXP/+2-small-potion quarter,
renders the source Status/orb, and performs a real VIT click that keeps current
HP 740 while maximum HP changes 760 to 800. Positive state persists through
switch, reconnect, reload, login and both real four-minute refresh timers. The
AMD Radeon 860M WebGL2 Chrome client and exported Linux client recorded no
browser or native engine errors; two transient partial native report reads
recovered in 11 ms with no unavailable snapshot. The earlier 129-check zero-XP
run remains narrower lifecycle evidence. The default-deny admin smoke passes 15
checks. A
distinct one-account bootstrap
artifact is prepared only for local privileged permission/replay/revoke tests;
publication was rejected by automatic approval review and remains pending
explicit user authorization. Privileged selection-change replay behavior is
therefore source-reviewed but not live-tested: a matching replay returns the
receipt's original outcome without mutating the newly selected character.

This slice deliberately leaves all other classes and sex variants, skills,
party grouping, alignment, death EXP loss/luck, stat-driven full combat balance,
complete item/loot parity, medium-potion consumption, levels above the default
cap, champion progression and reset/lower-level operations for later catalog
work. The current Wild Dog attack, health and damage values remain prototype
balance even though its level and EXP reward are source-backed.

## Protocol 6 target Slice A

The local target slice adds an owner-private selected monster ID/life projection,
a public authoritative monster level and validated select/clear intents. Server
controllers retain a checked 64-bit target revision and change deadline across
clear and reconnect. Explicit selection locks later attacks to that exact
generation without nearest-enemy fallback, while the already accepted pending
hit retains its captured target, equipment, action and damage. The reviewed dual
Wild Dog fixture gives each copy its own trusted AI/leash/respawn home and adds
no spawn reducer or player capability.

The default-deny two-account server run passes 53 of 53 checks in
`.local/p2-target/targets-root-reconnect-fixed-20260907.json`. It verifies
private ownership, same/clear/reselect deadlines, stale and missing rejection,
far selection with a nearer candidate, fallback presentation, unchanged pending
hits, a sub-850 ms same-JWT reconnect, natural respawn and target-life/owner-death
cleanup. This is focused server evidence; it does not qualify a public route or
an exported client.

The client implementation now includes ray-verified actor and ground picks, an
authoritative level/name/health target board, separate source-derived hover and
target effects, and selected-target Space routing. The exported Web/Linux runner
exercises real browser canvas input and the native probe's fixed
pointer/Space allowlist against the normal one-dog Yongan fixture. The reviewed
instrumented packages pass actual-PCK audits for 832 Web and 1,635 Linux paths,
all 226 UI images at exact decoded RGBA, three actor models, all 40 declared
clips, all 20 Web world sections and both 11-frame source-derived target effects
with four declared and four engine-derived texture hashes. The report is
`.local/p2-target/exports-root-reviewed.json`. Second probe exports pass the same
audits, and their 175-file source-freeze comparison differs only at
`export_probe.gd` as expected between instrumented builds; normal exports exclude
that test probe. The second Web PCK SHA-256 is
`a727af24fd4a6ba91a3c3973a5567968590a504ee48cc7bedf0d5e767d8dcf80`
and Linux is
`547791d7892d59b7b4dd24430d3849293fcb0cca3f9b9952ab069e1a581761ab`.
The native probe now moves its isolated test-window cursor before routing its
fixed pointer event because a focused Xvfb/Godot 4.7.2 check proved that pushed
or parsed events alone do not update the cursor read by the production polling
path. This behavior remains confined to instrumented test code that normal
exports exclude; the no-network record is
`.local/p2-target/probe-pointer-semantics-20260907.log`.
The full configured lint suite and 139 Python tool tests pass.

The final exported Web/Linux run passes 174 checks in
`.local/p2-target/browser-root-final-20260907/report.json`, with no engine
errors. It exercises actual Web canvas input and the native probe's fixed
pointer/Space allowlist, target privacy/UI/effects, selected-target damage,
target churn and movement, death/respawn, character and account lifecycle,
actor/inventory/panel composition, mutual movement, rejection, switch,
reconnect, reload, logout/login and both real four-minute refresh timers. One
ordinary unarmed kill uses four exact 25-damage hits, advances Wild Dog life 2
to 3 and observes the production respawn after 11.946 seconds; the distinct
protocol-5 199-check progression run remains the five-kill evidence. The 53-row
refresh trace contains 51 valid positions per client with zero maximum
authoritative drift and two transient unavailable position rows per client
during lifecycle transitions. Three partial native report reads recover within
52 ms, no snapshot read becomes unavailable, and the report's 72 ms maximum
includes initial file I/O.

A retained earlier 85-check failure and
`.local/p2-target/browser-root-settled-20260907/root-pointer-review.json` show why
the lifecycle setup now waits: after respawn, a momentarily valid projected
point moved by more than 100 pixels while the rendered dog closed a 1.82 m gap
to its authoritative row. The actual OS cursor matched the requested point plus
the native window offset. The runner consequently requires a stable ray-verified
projection and matching rendered/authoritative positions for 0.5 seconds before
sending one input.
Godot MCP was unavailable for this checkpoint. The accepted evidence is local
and instrumented; it does not establish an original-client pixel comparison.
Queued combo sequencing, automatic chase, broader combat and social target
actions, public protocol-6 deployment, Windows execution, full P2 and the full
game remain incomplete.

The root acceptance record
`.local/p2-target/root-acceptance-review.json` binds the 175 unchanged client
sources, 17 server source hashes, three module artifacts and both accepted PCKs.

## Required QA evidence

| Package | Required task evidence before review | Integration gate |
| --- | --- | --- |
| P0 definition and compiler contract | Deterministic repeat run; stable content/action IDs; source hash and override provenance; malformed, missing, duplicate and unsupported input fails visibly; generated client payload contains only public/presentation fields; trusted server payload remains server-side | Generated outputs agree on IDs/version and are consumed by both sides without hand-edited duplicate definitions |
| P1 warrior and starter-sword vnum 10 fixture | Skeleton/bind and skin deformation probe in Blender and Godot; clip name/duration/loop report; hand-alignment and bounds capture; missing attachment bone or source path fails with an actionable report | Native Godot and Web/Linux fixture use the same generated asset identity; package audit contains no source GR2/Blender runtime dependency |
| P1 WildDog 101 fixture | Model/motion/scale/bounds report; generated public appearance and trusted action references resolve; unsupported visual/effect records are explicit | Two independent clients render the same subscribed mob identity and lifecycle without a client-generated spawn or action result |
| P0 public appearance / trusted actions | Reducer tests reject invalid/non-finite/out-of-range intent, wrong equipment/mode, stale or unauthorized action; subscription inspection proves private item state is not exposed as public appearance data; reconnect/disconnect action/presence behavior covered | Server validates timing, range and equipment; a client animation callback cannot cause damage or grant inventory/stat changes |
| P1 actor and equipment integration | Godot parser/lint plus editor inspection of the connected project, current scene/runtime tree, rendered fixture and equipment input behavior; visual change follows subscription acceptance and correction | Two real authenticated identities see each other; equipping/unequipping changes remote appearance only after authoritative state update; reconnect preserves and reprojects appearance |
| Slice integration and acceptance | `python3 tools/dev.py lint`; relevant Rust/GDScript/Godot checks; generated-binding/schema check if protocol changes; native and Web/Linux fixture evidence | Actual one-server, two-client test: both see each other, each moves, remote movement updates, equipped starter sword vnum 10 is visible to the peer, WildDog 101 appears consistently, invalid action is rejected, and disconnect removes presence. Record commands, database name, client identities, outputs and any unrun platform separately. |

## Readiness record

The initial readiness record is stored in ignored `.local/p1/readiness.json`.
It reports only what was visible to this execution environment, contains no
identity tokens or profiles, and is not gameplay, asset-conversion, editor,
export, or two-client acceptance evidence. Godot MCP successfully confirmed
the connected Godot 4.7.2 project path and `main.tscn`; the sandbox could not
establish host process, port, or Blender-installation status.
