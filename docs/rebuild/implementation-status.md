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
