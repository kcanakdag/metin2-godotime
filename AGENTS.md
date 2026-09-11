# Development guide for coding agents

This file is the shared project guide for any coding harness or human contributor.
It does not require a particular model, agent framework, MCP connection, or IDE.
Follow the user's instructions and your harness's permission rules. Preserve
documented authorization and preferences across handoffs; do not infer permission
for unrelated actions. If your harness does not load this file automatically,
start by asking it to read `AGENTS.md` and the starting documents listed below.

## Project and starting context

Build a modern Metin2-like game with a standard Godot/GDScript client and a Rust
SpacetimeDB server in one monorepo. Preserve the familiar movement, camera,
characters, original selected assets, UI and pacing while modernizing authority,
tooling and implementation. This is a new protocol, not a server compatible with
the original Metin2 executable. Original GR2 assets are converted offline; the
game uses converted Godot assets and does not require Granny or Blender at runtime.

Start each new task or handoff by inspecting `git status`, recent commits and the
relevant source. Read these maintained documents rather than relying on an old
chat summary:

- `AGENT_HANDOFF.md`: the newest takeover document. It records workstation and
  deployment state, the slice currently in flight and its investigation, plus
  the immediate next actions. Revalidate its observed facts before acting.
- `README.md`: setup, controls, supported behavior and deployment overview.
- `docs/rebuild/implementation-status.md`: accepted milestones, active work and
  evidence. Local work and the public deployment may be different versions.
- `docs/full-rebuild-plan.md` and `docs/rebuild/plan.json`: full scope and feature
  dependencies. Accepting one fixture does not complete its entire phase.
- `docs/architecture.md` and `docs/development.md`: implemented contracts,
  process layout and commands. Read before changing architecture or run workflow.
- `docs/third-party.md`: source, tooling and asset terms; read before importing
  external code or extending an asset fixture.

Do not hardcode the current phase, protocol, database or tool installation path
from this file. Inspect current manifests, configuration, running processes and
the status ledger. Ignored evidence may exist only on the development workstation;
missing reports or assets on a fresh checkout are not proof that checks passed.

## Current implementation priorities

The full objective includes all milestones and eventually quests, with world
population first. Earlier requests to defer quests describe sequencing, not their
permanent exclusion. Complete playable mobs/combat, map NPCs, missing scenery,
all four classes/all 44 classic abilities, additional maps and developer tools.
The desired final experience is indistinguishable from classic Metin2, while
content remains data-driven, extensible and customizable. Converted assets alone
do not meet gameplay acceptance. Preserve the full scope across handoffs.
Extend reusable definitions and importers alongside each gameplay slice. Use
the offline [world-content tools](docs/world-content.md) for population drafts
and visual inspection; live admin actions still require server authorization.

## Repository map

| Path | Responsibility |
| --- | --- |
| `client/scripts/`, `client/scenes/` | Godot gameplay presentation, input, camera, account flow and classic UI |
| `client/scripts/net/` | Typed gameplay facade, authentication and subscriptions |
| `client/addons/SpacetimeDB/` | Pinned GDScript SDK; keep patches in its provenance file |
| `client/spacetime_bindings/` | Generated database/reducer bindings; regenerate, do not hand-edit |
| `server/src/` | Authoritative Rust gameplay, accounts, permissions and simulation |
| `server/build*.rs` | Validation and code generation from trusted content |
| `auth/` | Better Auth service, HTTP authentication and signed game sessions |
| `content/profiles/`, `tools/` | Selected source inputs, conversion, compilation, checks and export/deployment tools |
| `client/tests/`, `server/tests/`, `tests/` | Godot scenarios, Rust integration checks and Python tooling tests |
| `docs/rebuild/` | Feature catalog, source research, decisions and implementation status |
| `assets/source/`, `client/assets/imported/`, `server/content/` | Ignored original assets and generated client/server content |
| `.local/`, `.cache/`, `dist/` | Ignored local state, evidence, caches and builds; may contain private data |

## How to implement a feature

1. Identify the requested behavior, relevant catalog entries, current implementation
   and evidence needed to prove it. Check pinned source metadata when reproducing
   original behavior. Record unknowns and intentional approximations explicitly.
2. Implement a coherent vertical slice across server, content and client. Preserve
   the full requested scope; a convenient fixture is a validation boundary, not a
   replacement for the feature. Batch closely related changes into one milestone.
3. Agree on shared action IDs, schema fields, units, timing and lifecycle rules
   before parallel code depends on them. Keep interfaces small and source-backed.
4. Follow the user’s testing preference: run checks for touched behavior and its
   affected dependencies; reserve full suites for major milestone completion or
   evidenced broad impact. Run focused checks while implementing. Review and integrate the complete slice,
   then run the relevant two-client/exported qualification once it is ready.
5. Fix demonstrated failures at their cause. Repeat affected checks after fixes;
   avoid restarting the entire suite after every small edit when a focused replay
   or component check can first establish the correction.
6. Update documentation and record a reviewable checkpoint with actual results,
   remaining limitations and the next implementation step.

The user's current preference is solo implementation: do not spawn subagents
unless the user changes that preference. The following coordination guidance
applies only when delegation is authorized. Use agents for independent
work such as asset conversion alongside server implementation. Give each file or
subsystem one owner and each feature a clear integration owner. Share the contract
once, coordinate changes directly, and review at meaningful checkpoints. Avoid
delegating tiny serial fixes, duplicating investigations or making routine edits
wait for repeated coordinator approval. Respect any explicit user preference for
models, delegation or review. Preserve other contributors' uncommitted work; use
separate worktrees when isolation is useful, and stage only the intended changes.
With multiple agents, the coordinator owns contracts, review, integration and
acceptance while implementation owners build their assigned parts. A single
agent performs those same responsibilities sequentially.

## Authority and gameplay contracts

- The server owns identity, presence, movement limits, gameplay state, rewards and
  action validation. Clients send intents; they cannot grant positions, damage,
  items, currency or permissions. Validate client numbers for finite values and
  expected ranges before use. Animation or prediction never establishes authority.
- Synchronize database/reducer changes, generated bindings, client protocol checks
  and multiplayer tests. Generate bindings from the module actually being tested.
  Keep application protocol versions distinct from SpacetimeDB wire versions.
- Design rejection, disconnect, reconnect, expiry, death, character switching and
  stale entity/action generations when relevant. Accepted actions must not replay
  damage, rewards or movement after their lifecycle has ended.
- Keep private account, inventory, progression and privileged state behind
  server-enforced read filters. Client-side filtering is not access control.
- Developer menus may inspect state and send ordinary validated intents.
  Privileged commands require server-side capabilities. Do not grant privileges,
  weaken validation, bypass rate limits or enable public guest access to pass QA.
- Preserve standard Godot/GDScript and pinned dependencies unless an evidenced
  requirement justifies a change. Document engine, SDK and protocol assumptions.

## Commands and environments

New test exports require explicit probe activation. Browser harnesses must use a
context init script setting `window.mt2ProbeEnabled = true` before navigation;
the standard browser runners already do so. Native harnesses use their existing
`--probe-report` / `--probe-commands` arguments. Ordinary launches remove the
probe before installing callbacks or producing snapshots. This does not grant or
remove server privileges. See `docs/distribution.md#browser-test-builds` and
`tools/test_probe_activation.py` for focused activation/ordinary-play checks.
Do not mistake a deliberately absent `mt2Snapshot` for a broken ordinary client.

Use the existing tools rather than inventing a second build/run workflow. Resolve
installed executables locally; `GODOT`, `BLENDER`, `SPACETIME`, `SERVER_URL`, `DB`
and related overrides are documented in `Makefile` and `docs/development.md`.
Some Make defaults are historical placeholders, not the active development target.
Pass the intended database and endpoint explicitly for stateful operations.

For a fresh checkout, first install the quality tools:

```sh
python3 tools/dev.py setup
# POSIX shell: use the installed Python dependencies for subsequent tool commands.
. .local/venv-dev/bin/activate
```

Install the pinned auth dependencies, Rust target, engine export templates and
required content using the README setup sequence. Missing generated assets must
be rebuilt from pinned inputs; do not fabricate fixtures or disable their checks.

| Work | Existing entry points |
| --- | --- |
| Focused lint | `python3 tools/dev.py lint --only python` (also `gdscript`, `rust`, `typescript`) |
| Milestone checks | `python3 tools/dev.py lint`, relevant `make` checks, `make check` for the combined gate |
| Formatting owned code | `python3 tools/dev.py format --only python` or another affected group |
| Server/tool/auth tests | `make server-test`, `make test-tools`, `make test-auth` |
| Content and actors | `make content-build`, `make content-validate`, `make content-probe`, `make test-actors` |
| Classic classes | `make characters-build`, `make test-classes`; see `docs/characters.md` |
| Map and UI pipeline | `make import-map`, `make bake-map`, `make test-map`, `make import-ui`, `make test-ui` |
| Authenticated multiplayer | `tools/test_accounts.py`, `tools/test_targets.py`, `tools/test_combos.py` |
| Authenticated exported QA | `tools/test_browser_accounts.py` with the relevant feature flags and an actual native export |
| Playable exports | `tools/export_playable.py` or `make export-web` / `make export-linux` |
| Local replica storage | `make storage-report`, `make storage-sweep`, `make storage-clean`; see `docs/development.md#local-replica-storage-maintenance` |

Read each tool's `--help` and the development guide for required arguments.
Legacy guest smoke commands are not substitutes for authenticated multiplayer.
Raw Cargo defaults to the training world; Make normally enables Yongan, which
requires its baked content. A training-only result does not qualify Yongan.

Replica storage grows with every QA database, so run `make storage-report` when
the development disk falls below roughly 10 GB free, and `make storage-clean` to
drop obsolete entries plus their replica directories. Both phases are
identity-scoped and default to a dry run; the tool never removes a directory
owned by another CLI identity. Never delete directories under
`<data-dir>/replicas/` by hand or wipe a data directory to free space — that
destroys another identity's live database and the `db.lock` mapping the tool
relies on.

This workstation also carries a weekly user cron entry (Mondays 04:17) that runs
`make storage-sweep`: it reports, then removes only directories whose database
entry is already gone, so a scheduled run can never drop a live database. Its
output appends to `.local/maintenance/storage-sweep.log`; check it when starting
a handoff. `storage-clean` remains a reviewed manual step because deleting
obsolete named QA databases requires knowing which ones the ledger still cites.

Before starting or restarting services, inspect existing listeners, process
ownership, data directories and proxy routing. Reuse verified services or choose
separate ports and data directories. Never start another MCP server on an active
bridge port. After a timeout, inspect or poll the same process before declaring it
dead or starting a replacement. Coordinate tests that create accounts and respect
the authentication service's rate limits.

Use a fresh, explicitly named database for incompatible schemas and disposable
tests. Never overwrite or wipe existing development data to make tests pass.
The auth issuer compiled into the module must match the auth service exactly.
Do not publish a local-issuer module or privileged test fixture publicly.
Instrumented exports may use the public playtest endpoint when the user has
authorized that QA build; keep probes out of normal friend/release builds.
Deployment, external access and privileged actions must respect the user's
authorization and the harness's permission controls. If an action is blocked,
explain the concrete action/reason and continue unaffected work; do not bypass it.

## QA, tools and evidence

- Python uses Ruff; GDScript uses gdformat/gdlint plus the real Godot parser and
  runtime; Rust uses rustfmt/clippy/tests; Node services use strict TypeScript and
  dependency locks. Fix findings instead of globally disabling checks. Do not
  reformat vendored addons or `tools/godot-mcp-server` wholesale; document patches
  in the existing provenance files. Formatting can affect an entire selected
  group, so coordinate ownership before running it during parallel work.
- Use focused tests for meaningful rules and regressions. A linter pass alone
  does not establish that an editor or exported game works. Documentation-only
  changes need link/command review and `git diff --check`, not a full game run.
- For networking/gameplay, use two independent authenticated identities on one
  actual server. Verify mutual subscriptions, movement in both directions,
  rejection behavior, presence removal and relevant reconnect/state persistence.
  A database query is not proof that a client received a subscription update.
- For visual/input changes, inspect the rendered game and real input behavior.
  Use Godot MCP when available to inspect project path, scene/runtime trees and
  screenshots. Confirm the project before editor mutations and preserve unsaved
  work. Without MCP, use isolated Godot CLI fixtures and rendered exports; record
  missing editor evidence instead of claiming it. Use browser MCP or the existing
  Playwright harness for browser QA; Blender MCP or background Blender for assets.
  Missing MCP does not block work that equivalent CLI tools can safely verify.
- Keep editor bridges local. Do not create ad hoc remote script evaluators to
  replace unavailable tooling. Prefer isolated test/import/export projects when
  the user's editor is open; `make check` includes a real project import/runtime
  check, so inspect its effect on the current editor before running that gate.
- For timing-sensitive tests, send inputs promptly and collect large histories
  afterward. Retain exact reducer acknowledgements and subscribed action rows.
  Diagnostic logging must tolerate expected empty disconnect/loading snapshots;
  gameplay assertions must still enforce their required fixture and state.
- At acceptance, bind evidence to the actual source, generated-content identity,
  module, endpoint/database and exported package hashes. Freeze inputs during a
  qualification run, preserve failed-run diagnostics and label superseded results.
  Do not pass off tests of older artifacts as verification of changed code.
- Run actual exports, inspect their packaged contents and test against the
  intended endpoint. Distinguish local from verified internet connectivity,
  instrumented from normal exports, and Linux from Windows execution. Test probes
  belong only in explicitly authorized QA builds. Normal friend/release builds
  must omit MCP bridges, evaluators, probes, tokens, logs and source archives.

## Assets and handoffs

Use the existing Blender conversion/content tools and pinned source inputs.
Preserve source commit/hash provenance and keep original assets, converted
derivatives and downloaded third-party code in their ignored directories. Extend
only the selected fixtures needed by the feature; do not silently import every
asset or copy an external project. A source reference is not a license grant;
GPL reference code, original Metin2 assets and MIT tooling have different terms.

Fix generators rather than editing `.godot`, generated bindings, build/cache
output or downloaded sources. When import logic changes, check deformation,
durations/attachments and actual Godot appearance. Preserve accepted generated
inputs and packages before a new compiler revision replaces local outputs.

Update README and relevant architecture/development notes when contracts,
commands, dependencies, controls or export behavior change. Keep current progress
in `docs/rebuild/implementation-status.md`, not in harness-specific memory alone.
For a handoff, record the commit and remaining dirty files, implementation scope,
actual checks and evidence paths, active service configuration, unresolved issues
and the next action. Exclude credentials. Distinguish implemented, tested,
accepted and deployed; never claim full-game or original-client parity from one
bounded fixture. Continue authorized work without repeatedly asking permission
for routine implementation choices.

## Current continuation snapshot — world population deployed, combat polish active (2026-09-11)

The repository root `AGENT_HANDOFF.md` is the detailed takeover document for this
checkpoint. It records a moment, not configuration: revalidate its processes,
endpoints and hashes before restarting, publishing or claiming status.

The active slice is **combat polish**: held-space combo continuation with and
without a live target, a data-driven weapon-mode chain so the two-handed warrior
and other classes reuse one path, then skill learning and upgrading. The
investigation (file and line anchors, original-server comparison and a suggested
change order) is recorded in `AGENT_HANDOFF.md` section 5; no code has changed yet
and the worktree is clean.

The public playtest endpoint serves release `20260911T123640567701Z` on database
`mt2-public-quests-v32-20260910` (`delete_data: never`): module
`/opt/metin2-godotime/mt2_server.wasm` sha256
`ba665d3f7507f1f343183093ab35269fd359b9f765e0fb3b1ebe9cc32075051a` (3,720,905
bytes), built from `.local/world-population-r1/mt2_server.maintain-r1.wasm`, and
the served web pack `index.pck` sha256
`4db41122b687608511a634e0011a9a76ffcf257b8231497019a9d090b3840ab5`, byte
identical to `.local/world-population-r1/export/web-r8`. The previous baseline
was release `20260910T132257494611Z`, module
`3f96b25aea5563059b1c6cc80966ae234ace7a1dd99effa49c2f088c47f26f9d`; its local
candidates under `.local/public-quests-v32-r1/` (web-r4, web-r5, linux-r6) are
superseded history and must not be re-deployed. Confirm the live release from
`/opt/metin2-godotime/deployment-status.json` plus `sha256sum
/opt/metin2-godotime/mt2_server.wasm`; the SpacetimeDB CLI "program hash" is over
a normalized module and does not equal the file hash.

That deployment added the private `monster_regeneration_registry` table with 945
entries (a top-up over `monster_regeneration`) while retaining the protocol-32
quest catalog and account rows, so the deployed module itself embeds the
regeneration-registry receipt (945 entries). `server/build.rs` plus
`tools/deploy.py` now refuse to hot-swap a module whose registry is empty unless
`--allow-empty-regeneration` or `--reset-database` is passed. Read
`docs/development.md#regeneration-registry-hot-swap-hazard` before publishing
over an existing database, and keep a registry-covering population file
(currently `.local/mobs/yongan-runtime-policy-r2/population.v1.json`, 945
entries) available for top-ups like the deployed
`.local/world-population-r1/mt2_server.maintain-r1.wasm`.
`content/worlds/yongan.population.json` still has no `regeneration` key.

## Superseded continuation snapshot — protocol 32 quests (2026-09-10)

Superseded by the 2026-09-11 deployment above; the quest runtime and its sources
of truth remain current.

The protocol-32 server-authoritative quest runtime was deployed publicly as
release `20260910T132257494611Z` (module SHA-256
`3f96b25aea5563059b1c6cc80966ae234ace7a1dd99effa49c2f088c47f26f9d`).

Quest sources of truth: `server/src/quest.rs` (runtime), `tools/build_quest_catalog.py`
(compiler), `tools/metin_quests.py` (pinned corpus reader), profile
`content/profiles/classic-quests-opening.json`, and `server/build_quests.rs`, which
embeds the compiled catalog through `MT2_QUEST_CATALOG`. The profile compiles
`main_quest_lv1`, `main_quest_lv2`, `main_quest_lv3` and `find_squareguard` from
git.old-metin2.com revision `7ee9c84`; text stays as original Gameforge
localization keys resolved from the pinned `translate_en.lua` at build time. An
empty catalog fails closed, oversized state chains are bounded, unanswered
questions expire, and rewards roll back with the reducer transaction. The
published module demonstrably contains the catalog — verify a deployment with
`grep -c find_squareguard mt2_server.wasm` rather than trusting a release name.
`quest_state`, `quest_objective` and `quest_selection` are account-filtered with
`:sender` visibility filters; branch bodies never leave the server.

The regeneration-registry receipt described in this snapshot is no longer
unpublished: `server/build.rs` embeds
`mt2spacetime.regeneration-registry.v1 count=<n>`, `tools/deploy.py` refuses a
hot-swap whose receipt is empty, and the currently deployed module carries 945
entries. See the newest snapshot above.

## Superseded continuation snapshot — protocol-31 self-buffs (2026-09-09)

Protocol 32 keeps this schema, so the details below remain accurate history; use
the newest ledger entries for its evidence paths and limits.

The active slice is the protocol-31 reusable self-buff lifecycle for Berserk (3),
Aura of the Sword (4) and Strong Body (19). The corrected local-only candidate is
`.local/p6-self-buffs-r1/module-r3.wasm` (SHA
`6dc6856b7d4a6c9963610ad060f5f8cfded7c2c5564c40b215add94bf64731d2`) with
catalog `.local/p6-self-buffs-r1/catalog.v1.json`. Berserk, Aura and Strong Body
each pass 41 authenticated lifecycle checks; Aura passes 45 with the actual HUD;
Strong Body passes 17 death/respawn checks after a 39-check preparation pass.
Rank-20 ordinary-combat replays pass 29 Aura outgoing checks, 26 Strong Body and
26 Berserk incoming checks; movement passes 24 Berserk and 29 Strong Body checks.

Exported Web two-client casting is now accepted for all three buffs. The r5
build at `.local/p6-self-buffs-export-r5/web` stages the matching motion-effect
package and passes **33 checks per buff** in Chromium against local database
`mt2-p2-self-buffs-v31-export-r2-20260909-2ffc5096`. The reports are
`.local/p6-self-buffs-browser-r1/berserk/report.json`,
`.local/p6-self-buffs-browser-r1/aura-r2/report.json` and
`.local/p6-self-buffs-browser-r2/strong-body-r3/report.json`. This covers the
real HUD/quickslot, owner-only status, one SP payment, cooldown rejection,
countdown, reconnect restoration and expiry with no browser engine errors.

Next qualify native/Linux exported parity and rendered world-effect/UI
presentation for the three buffs, then continue the remaining 41 prepared
abilities and full world population. The candidate uses the local
issuer/bootstrap identity and must not be published publicly. See the newest
ledger entry for export hashes, databases, reports and remaining limits.
Read the newest entries in `docs/rebuild/implementation-status.md`; the older
snapshot below is historical. Source and generated bindings now use protocol 31.
The selected candidate is `.local/p6-self-buffs-r1/catalog.v1.json`; installed
content still selects the accepted Warrior skills. Do not call all 44 prepared
definitions/motions playable.

The frozen training QA module `.local/p6-buffs-server-r1/module.wasm` is published
to `mt2-p2-buffs-v30-r1-20260909-e81e5a1c` on local port 13223. Its receipt binds
module/source/catalog/schema identities. It uses local issuer
`http://127.0.0.1:8186/auth`, disables guests and bootstraps the retained first QA
identity. It is not public-deployable. Existing auth/database/proxy processes were
reused; the served local protocol-29 and public protocol-26 builds are unchanged.
The saved CLI token failed signature validation; supported anonymous publication
created only this new disposable database. Do not change global credentials to
repeat QA or reset existing databases.

Live `tools/test_progression_admin.py buff` evidence: `multiplayer-r2.json` passes
26 activation/rejection/reconnect checks; `multiplayer-r3.json` passes 29 checks
including full expiry after a two-second offline pause (66,427 ms wall time).
Private accounts remain `.local/p6-charge-r2/private.json`; never print its content.
The replay reuses rank one and requires cooldown to have elapsed. Test source and
the post-run lint-only refactor are distinguished in the ledger.

Native candidate actor qualification passes 196 checks in
`.local/p6-buffs-render-r2/report.json`. All eight Berserk captures were reviewed
and hashed in `berserk-review.json`. The actor runner now accepts `--skill-catalog`
without installing content. These captures do not prove live world displacement,
blend transitions, unarmed rendering or browser parity. Original source does not
automatically suppress root movement for standing skills; female Berserk's MSA
endpoint still needs comparison with actual GR2 trajectory before changing it.

Next: native/Linux exported parity and rendered world-effect/UI presentation,
then continue the remaining prepared abilities and full world/class/content
objective. An authorized public update still requires a production issuer/build.
The scoped local evidence includes stored state, stats, action/payment, reconnect,
expiry, quantitative combat, movement and exported browser casting. Latest
cleanup makes the legacy single-effect movement wrapper test-only; strict library
Clippy and 14 movement checks pass. The frozen QA module predates that
non-gameplay cleanup. Preserve pre-existing untracked actor/content/test UID
files when staging commits.

## Handoff snapshot — 2026-09-08

This section records observed state at handoff, not immutable configuration.
Revalidate processes/endpoints before restarting or deploying. The latest code
checkpoint is `3b27f19` (particle recipes/textures), preceded by `1bf21ea` (arrow
mesh conversion) and `558dee3` (flight-definition discovery). The interrupted
follow-up initially researched particle runtime behavior. After the handoff request,
work resumed: `client/scripts/actors/particle_emission.gd` implements emission
and lifetime tracking, with `particle_motion.gd` and `particle_simulation.gd`
adding kinematics. `particle_style.gd`/`particle_effect.gd` now render the selected
effects in an isolated native gallery; live projectile integration is unfinished.

### Playable state versus prepared content

- Local accepted gameplay has four classes/both appearances, basic combat,
  Sword Spin, the Blender-authored training dummy, six authored Wild Dog homes,
  and town NPCs. Only Sword Spin is a live ability; the other 43 remain unfinished.
- The dummy is already installed. Its profile is
  `content/profiles/training-dummy.json`: 30,000 HP, two-second respawn, Yongan
  placement `(662, 580)`, plus a Training Grounds placement. It grants no rewards.
  `tools/build_training_dummy.py` regenerates configurable appearance and clips.
  See `docs/training-dummy.md`; do not create a second dummy to repeat this work.
- All 44 candidate class skills have data/formulas and imported motions, not
  complete gameplay. Shared handlers, specialization selection, weapon modes,
  buffs/status effects, healing/friendly targeting, UI and two-client casting
  remain required. See `docs/skills.md` for tuning and qualification workflows.
- Full Yongan mob preparation covers 44 definitions sharing 19 GLBs/271 unique
  clips. `.local/mobs/population-conversion-acceptance-r1.json` binds the conversion;
  `.local/mobs/population-actors-r1/report.json` records 2,818 native asset checks.
  These additional mobs are **not installed in the live population**.
- `.local/mobs/population-gameplay-r2/gameplay.v1.json` links 78 attacks: 52 melee
  and 26 projectile variants. White Oath definitions use original MAGIC damage,
  including visually sword/bow-equipped actors. Do not substitute physical damage.
- Group placement and regeneration have reusable offline Rust cores/diagnostics.
  Their live database integration remains unfinished. Original capacity is owned
  by group leaders and released on destruction; surviving followers can remain.
  See `docs/mobs.md` before replacing the authored-home runtime. Current combat
  validation still relies on `trusted_spawn` and generated static definitions.

### Immediate continuation: projectile presentation and world integration

`tools/metin_particles.py` and `tools/import_particle_effects.py` convert seven
selected MSE effects, 22 particle systems and 12 referenced textures. They retain
original units, scalar curves, packed color keys, ordered texture frames, blend,
billboard, attachment and rotation settings. They do not simulate/render effects.
The arrow mesh is converted and has a native-tested opaque-target material;
original-client blend parity remains unfinished.

Evidence: `.local/mobs/particle-effects-r2` and `particle-effects-r3` are identical
online/offline builds. `.local/mobs/particle-acceptance-r1.json` records 20 focused
tests, owned Python lint, catalog/receipt hashes and `runtime_qualified: false`.
Source texture decoded pixels match converted PNGs. These checks do not establish
Godot rendering, exported gameplay or additional playable abilities.

The emission/lifetime component now passes 90 actual Godot checks, including all
22 systems, in `.local/mobs/particle-emission-r2/report.json`. Reproduce with
`tools/test_particle_emission.py --godot GODOT --catalog PARTICLE_CATALOG --output
NEW_DIR`. The test isolates user data and binds source hashes; it performs no
rendering or server integration. See `docs/mobs.md#godot-emission-lifecycle`.

Particle motion now passes 89 actual-engine checks in
`.local/mobs/particle-motion-r1/report.json`; the runner's `--scenario motion`
exercises original trajectories/forces, attached/world coordinates, shapes and
seeded replay across all 22 systems. The emission regression passes 90 checks in
`particle-emission-r3`. There is still no rendered or live-game qualification.
Nonzero emitter angular orbit rejects explicitly; the selected systems use zero.

The selected renderer now passes 62 native Godot checks in
`.local/mobs/particle-render-r2/report.json`, with 35 hashed captures. All seven
early captures were visually inspected; see `particle-render-review-r1.json`.
The runner's `--scenario render` uses Linux/Xvfb Compatibility (observed llvmpipe).
Original-client gamma/blend comparison, hardware/browser exports, occlusion and
population performance remain unqualified. Motion regression passes 89 checks
in `particle-motion-r2`. These are component effects, not new live mobs/skills.

`projectile_flight.gd` now passes 80 actual-engine trajectory/homing checks across
the four original definitions in `.local/mobs/projectile-flight-r1/report.json`.
The same runner's `--scenario flight --catalog FLIGHT_INVENTORY` checks swept hits,
range-before-hit ordering, force/homing order and state-preserving rejection.
It emits presentation events only; effects are connected below, combat is not.

The combined `projectile_effect.gd`/`projectile_trail.gd` now passes 53 native
checks in `.local/mobs/projectile-render-r1/report.json`, with nine hashed captures.
All three particle-based flights and impacts were visually reviewed; see
`projectile-render-review-r1.json`. Reproduce with `--scenario projectile --catalog
PARTICLE_CATALOG --flights FLIGHT_INVENTORY`. Paired attachment spacing, flight-end
cleanup, impact lifetime and trail expiry are covered.

The arrow follow-up adds `mesh-effects.v1.json` to the Blender package and
`projectile_mesh_effect.gd`. `arrow-material-r4/report.json` passes 527 native
checks: a full byte ramp over two backgrounds, discrete morph timing, catch-up
backlog and rejection of transparent viewports/unsupported recipes. Compatibility
color-transfer approximation caused a real low-green error; the bounded material
compensation reduces the worst channel error to 0.73 bytes. See third-party notes.
This adapts the opaque-destination case, not arbitrary original 3/8 blending.

The combined wrapper now accepts a mesh resource map. Reproduce all four flights
with `--scenario projectile --catalog PARTICLE_CATALOG --flights FLIGHT_INVENTORY
--meshes .local/mobs/arrow-mesh-r3/mesh-effects.v1.json`.
`projectile-render-r3/report.json` passes 61 native checks with 12 captures; the
arrow frame-8, impact and separate material close-up were reviewed and bound in
`arrow-render-review-r1.json`. A prior test catalog-key error is fixed. The runner
now terminates its isolated process group on timeout. Owned Python/GDScript lint
and 20 parser/accessor tests pass. No editor MCP, browser/export, live launch or
server damage evidence is claimed.

The subsequent `population-launch-r2/report.json` passes 1,440 native Godot
checks across the full 44-definition/78-attack selection. The presentation compiler
now includes all 26 source launch declarations, and ActorPresentation emits them
once per action/sequence through PveActor. All converted bones resolve; source
clock, heading-independent original offsets, resync deduplication and late joins
are exercised. See `docs/mobs.md#mob-motion-launch-events` for the surprising
original model-space offset semantics and long-frame completion coverage.
Archer/Jin-Hee idle gallery captures were reviewed; not launch-render evidence.
Eleven Python tests and scoped lint pass. This fixture uses controlled rows.

The worktree now uses protocol 19: public Monster rows capture `attack_target`
and `attack_target_life_sequence` at action acceptance. Private hit consumption
preserves the presentation snapshot; action completion, death/respawn and recovery
clear it. Both subscriptions see the correct snapshot in the 104-check live
training scenario, `.local/mobs/attack-target-training-r1/multiplayer.json`.
Server tests pass 138 and strict library Clippy passes. Bindings are generated
from the actual database; schema hash is
`0e20635c4f614a884e4d08c2eba09d2f19c6e027d5eb5a96fe5567c1c480234a`.
The separate frozen Yongan module is `.local/mobs/attack-target-r1/module.wasm`;
the training module/database uses `attack-target-training-r1` and
`mt2-p2-attack-target-training-r1-20260908`. The melee harness requires a training
build without the yongan feature; earlier formatting/wrong-map attempts failed.
The served local/public artifacts below remain unchanged. Never infer their
protocol from the newer worktree.

The world projectile lifecycle component now exists at
`client/scripts/world/world_projectiles.gd`: trusted resource maps plus an exact
identity/life/position resolver create and track the existing renderer. Original
lost-object behavior retains its last position and permanently disables homing,
including after reconnect/respawn. A source removal only retires deduplication;
world clear removes flights/impacts/cache. `projectile-world-r2/report.json` passes
125 native checks and 16 captures; paired-effect and arrow captures were reviewed.
Scoped lint passes. These are controlled replicas, not live scene integration.

The portable package/loader now exists: `tools/build_projectile_catalog.py` and
`client/scripts/content/projectile_catalog.gd`. `projectile-package-r2/r3` under
`.local/mobs` have identical catalog bytes/hash
`90ca48025f36e774a8fcde7aa664740ed013671b647f54119474c8c840d8138b`.
Four flights share 14 source assets plus 13 generated PNG import sidecars.
Default Godot import altered one texture; the generator now pins lossless/no-mip/
no-3D-compression/no-alpha-border settings. `projectile-package-render-r3` passes
145 native checks, including all 12 particle texture RGBA hashes, malformed-load
rejection and world flight lifecycles. Three Python tests and scoped lint pass.
Reproduce via `test_particle_emission.py --scenario package --catalog PACKAGE/catalog.v1.json`.
The package is not installed and has no main-scene/export/browser qualification.

Main-scene projectile checkpoint: Main now loads the required package, connects
real PveActor launch signals and resolves the rendered player's transformed body
bounds center. `.local/mobs/projectile-main-r4/report.json` passes 31 native checks
with four hashed captures, including equipped target idle, source removal,
duplicate suppression, impact draining and disconnect while a shot is active.
Reviewed the flame and arrow captures: both appear between the converted attacker
and equipped warrior in the training scene. This fixture controls state and time;
it does not establish live subscriptions, browser behavior or original-client
visual parity. Earlier QA caught an empty-animation snapshot error and an invalid
fixture sword ID; both are corrected. Godot MCP tools were unavailable; native
isolated Godot/Xvfb was used without touching the open editor. No content package,
server or public deployment changed. Next: authoritative original magic/ranged
combat and live population integration, followed by exported multiplayer QA.

Do not keep substituting inventory reports for integration.
The interrupted investigation inspected pinned primary files under
`.cache/full-game-research/client/source/src/EffectLib/`:

- `EffectElementBaseInstance.cpp`: local time advances before particle update;
  a delayed start activates on one update and begins simulation on the next.
- `ParticleSystemInstance.cpp`: fractional emission residue is preserved;
  capacity-clipped integer emission is discarded. Loop count zero repeats
  continuously; nonzero counts stop emission while live particles can remain.
  Only one cycle length is subtracted per update, not an arbitrary catch-up loop.
- `ParticleInstance.cpp`: remaining life is reduced first and expires when
  strictly negative. Decorators run before velocity-based position integration.
- `EffectUpdateDecorator.cpp`: air resistance scales velocity per update;
  gravity changes original Z velocity using elapsed time. Do not assume generic
  engine particles automatically reproduce these rules. Rendering/attachment and
  coordinate conversion still need source investigation and actual visual QA.

### Last accepted service artifacts (liveness not rechecked at handoff)

- Local URL: `http://127.0.0.1:8186`, application protocol 18, database
  `mt2-p2-npc-areas-qa-r1-20260908`.
- Frozen module: `.local/npcs/area-module-r2.wasm`; web export:
  `.local/npcs/exports/area-web-r1`; Linux export:
  `.local/npcs/exports/area-linux-r1/MT2Spacetime.x86_64`.
- Spacetime endpoint `127.0.0.1:13223`, data `.local/p1/server`; auth endpoint
  `127.0.0.1:13224`, data `.local/p1/auth`; exact local issuer
  `http://127.0.0.1:8186/auth`, guest access disabled. Inspect existing routing.
- `.local/npcs/area-browser-r2/report.json` records 115 Chrome/Linux checks.
  Public `https://kcanakdag.com:8443` was still the older protocol-4 deployment.
  Recent imports/cleanup did not deploy or qualify the public endpoint.
- Godot MCP was unavailable and Blender MCP previously unreachable in this
  harness. Use existing isolated CLI tooling when needed; recheck availability
  rather than asserting that a connected editor was inspected.

### Disk cleanup and worktree preservation

The user explicitly authorized removing unused files. Cleanup removed 44 historical
Cargo build directories identified by `.rustc_info.json` and `.fingerprint`
under `.local/`, after confirming no host `cargo`/`rustc` process was active.
Measured recovery was **17,050,132,480 bytes (15.88 GiB)**. An earlier pass removed
approximately 289 MiB of inactive `server/target/debug/incremental` cache.
The detailed deletion inventory is
`.local/cleanup/compiler-caches-20260908-114842.json`.

Databases/auth state, original and imported assets, test reports, frozen modules,
game exports and the main `server/target` build tree were preserved. Historical
test compilation caches must be rebuilt if those scenarios are run again;
missing cached executables now are expected, not evidence that source was lost.
Free disk space was 49 GiB at the documentation check; other activity changed
space concurrently, so do not attribute that entire amount to this cleanup.
Check `df` before large exports. Never delete `.local` wholesale: it contains
databases, secrets and irreplaceable evidence alongside rebuildable caches.

Five pre-existing untracked Godot UID files were deliberately left untouched:
`client/scripts/actors/attack_input.gd.uid`, `attack_timing.gd.uid` in that same
directory, `client/scripts/content/character_catalog.gd.uid`, and
`client/tests/fan_actor_smoke.gd.uid`, `physical_classes_smoke.gd.uid` in that
test directory. Review their ownership before staging or deleting them.
Check git status for the emission implementation/checkpoint. Keep credentials out of handoff text,
tool output and commits; inspect only sanitized fields from local QA state.

### Ordinary mob damage follow-up

Ordinary mob damage dispatch now uses a typed field on the trusted mob definition.
The installed dog selects Normal; the shared `mob_damage` finalizer also implements
NormalRange and Magic under the current zero-bonus policy. NPC magic repeats the
low-damage floor after melee calculation, applies magic resistance, and uses the
reduced skill critical probability. NormalRange uses bow resistance and full
normal critical probability. Resistance truncates before critical doubling;
bounded arithmetic and invalid RNG rejection prevent wrapping or invalid rolls.
Source reference: pinned server `battle.cpp` CalcMagicDamage/CalcBattleDamage and
`char_battle.cpp` FuncShoot/CHARACTER::Damage. This is independently authored logic.
The magic and range branches are covered by deterministic arithmetic tests, not
live enemies. Their action scheduling, canonical resistance adapters, population
registry installation and live two-client qualification still remain unfinished.
Party/affect/penetration and hit/skill bonus stages are not implemented by this
finalizer; the installed policy keeps them at zero. No server was republished.

NPC ranged/magic scheduling now follows the original synchronous `Attack` ->
`Shoot` call. Trusted ranged/magic actions require zero melee hit-window offsets;
normal melee actions retain their existing bounded window. Simulation publishes
the accepted action and immediately consumes/resolves its captured hit in the
same transaction. Existing target identity/life, health, range and collision
validation still applies. Client projectile events never authorize damage and
flight travel time does not delay this original NPC damage path.
Tests cover both ranged/magic registry dispatch, malformed melee-window rejection
and single consumption at acceptance with no later tick replay. No ranged/magic
mob is installed yet, so live multiplayer acceptance for this branch is pending.
Original population registry generation, canonical resistance adapters and original
AI/distance policies still need integration before release qualification.

The runtime physical-policy gate now accepts finite positive authored NPC damage
multipliers within the existing arithmetic bound (100). Player NPC-multiplier
fields and the unrelated final multiplier still require 1.0. The full Yongan
candidate contains 24 definitions at 1.0, 13 at 1.4 and seven at 2.0; the old gate
would reject those 20 non-unit definitions despite arithmetic support.
Two new runtime-path tests cover exact source-ordered results for all three
multipliers, the mob-definition adapter, invalid/nonfinite bounds and rejection
before RNG. All-target Rust tests pass (145 library tests plus other suites),
as does strict all-feature Clippy. Evidence: `.local/mobs/multiplier-runtime-r1`.
The installed dog still uses 1.0; no database, content installation or deployment
changed. Full registry generation and population integration remain pending.
Seven MAGIC variants (391,392,393,395,396,397,398) also have source penetration 1;
the finalizer does not yet consume it. Do not silently discard it during registry
installation. Original MAGIC penetration reduces the chance but still consumes
a random draw for a nonzero source value, even when the resulting chance is zero.

Ordinary NPC penetration is now a trusted physical-definition field and flows
through the runtime damage finalizer. It adds the canonical victim defense after
resistance and critical doubling; critical does not double that add-back.
Normal/normal-range use the full chance; magic uses the source skill reduction.
A nonzero 1% MAGIC value consumes a draw but cannot proc after reduction, matching
the seven selected White Oath variants. Invalid chance/roll and u16 result overflow
reject. The installed dog remains at zero penetration with unchanged random draws.
All-target Rust tests and strict all-feature Clippy pass (148 library tests plus
other suites); evidence: `.local/mobs/penetration-runtime-r1`.
Penetration resistance, its passive skill modifier and nonzero defense-percent
bonuses remain outside the installed zero-bonus policy. Full population registry
installation and live ranged/magic multiplayer QA are still pending. No server,
client export or public deployment changed. The earlier note that penetration is
not consumed is superseded by this checkpoint.

`build_mob_catalog.py` now emits `combat-registry.rs` alongside its existing
JSON artifacts, with a hash in the receipt. The generated tables use the actual
server MobPhysicalDefinition, WeightedMobAttack and AttackDefinition types.
They preserve all 44 physical definitions, damage-kind dispatch, multiplier/
critical/penetration values and 78 source-timed weighted attacks. Projectile
rows have immediate zero hit offsets; melee rows preserve the single converted
window. Unsupported layouts and invalid numeric/identity/weight data reject.
The emitter deliberately does not invent spawn, AI, regeneration or reward policy.

Evidence: `.local/mobs/server-registry-r1/r2` have byte-identical registry output
(SHA-256 `7135d451f51e45ded3df85416fc6cdf3fd71b99cd7ae7da57646b6b7ea7d234c`).
The r1 Rust harness includes the actual generated server types and action validator:
11 tests pass, including all 4,400 weighted selections and exact action lookups.
Its type inputs are hashed in `type-inputs.json`. Fourteen Python compiler tests
and scoped Ruff pass. This validates candidate combat tables, not installed
population or live multiplayer behavior. No database or deployment changed.
Next integrate these tables with the full runtime mob registry and the matching
client content hash/installation path; retain original AI/regeneration/reward
metadata and explicitly handle unsupported mechanics rather than dropping them.

Species data is now separated from world lifecycle policy in the actual server
MobDefinition. The installed dog uses the same values through MobSpeciesDefinition;
acquisition/leash and respawn remain explicit world policy. The generated candidate
adds 44 species records for health, model/motion IDs, movement, defending spheres,
reactions and XP/gold ranges, alongside its existing physical/action tables.
Evidence: `.local/mobs/species-registry-r1` compiles against actual server types
and passes 11 Rust fixture tests (including all weighted selections). Fourteen
Python compiler tests, all-target Rust tests (148 library tests) and strict Clippy
pass. Source mismatch, invalid movement and reversed reward ranges reject.
The full population remains uninstalled; original AI/regen/drop integration is
still required. Public deployment was requested after this slice and is in progress
under `.local/public-progress-r1`; do not report it deployed until verified.

### Current public deployment — 2026-09-08

The public development endpoint is now `https://kcanakdag.com:8443`, protocol 19,
database `mt2-public-progress-v19-20260908`, release `20260908T121524155504Z`.
This supersedes the older public protocol-4 deployment. The user explicitly
requested this update. Existing auth accounts, issuer keys and prior databases
were retained; the new world has a separate character roster.
Artifacts and hashed acceptance are under `.local/public-progress-r1`: frozen
`module.wasm`, matched `web/` and `linux/` exports, export audits, `deploy.log`
and `acceptance.json`. The module was built with the public auth issuer and guests
disabled. Both exports use the explicitly authorized development test probe;
editor MCP bridges, private state and source archives remain excluded.
`browser-qa/report.json` passes 114 actual public Chrome/Linux checks using two
independent accounts: registration/login, private roster, replicated movement,
21 entry NPCs and City Guard, independent dialogue, dummy selection/damage,
skill-panel input, character switching, disconnect/reentry, reload and logout.
Browser engine errors are empty. The browser world and guard-dialogue captures
were reviewed. Chrome MCP new_page timed out; the separate automated Chrome
runner completed. Windows execution and full original-client parity are not
qualified. All 44 candidate mobs and the remaining abilities are still not live.
The localhost area endpoint remains separate and was not replaced by this rollout.

`mob_threat.rs` now implements the original damage-type/current-victim threat
multipliers as separately truncated f32 stages, negative-total clamping, checked
overflow, leader/member party sharing, SPECIAL exclusion from party sharing,
and the exact three-second victim-change gate. It is a calculation component,
not yet connected to persisted AI or the damage ledger. The XP ledger must retain
actual damage; never replace its values with boosted threat.
152 library tests and strict all-target/all-feature Clippy pass; source-bound
evidence is `.local/mobs/threat-core-r1`. No database or deployment changed.
The reviewed original `StateIdle` only proximity-acquires for AGGR, while existing
victims persist; 41 selected species have no AGGR flag and three do. Integrating
passive retaliation requires a separate persisted current victim/threat state,
including source/target lifecycle cleanup and original ChangeVictimByAggro
arbitration. Do not implement passivity by simply disabling attacks, or retarget
by the nearest player on every tick. The current authored dog AI is unchanged.

### Persistent mob victims — protocol 20

Protocol 20 now adds private `monster_threat` and `monster_victim` tables.
The actual simulation retains a valid victim instead of choosing the nearest
player each tick. Validated damage updates separate threat with an explicit
damage kind; normal combos and Sword Spin retain distinct dispatch for future
extension. Switching follows the three-second gate and strict higher-score rules.
Source/target life checks, existing chase/path bounds, death/reset and character
leave cleanup apply. XP attribution continues to store unboosted damage.
The species compiler preserves AGGR (three of 44 species); passive definitions
skip proximity acquisition but can retaliate through damage-created victim state.
The existing authored dog remains aggressive. Full passive-population play,
party threat propagation, original wandering/group AI, persistence across a
server-process restart and the remaining world installation are not qualified.
The imported candidate still is not installed.
Bindings were generated from a fresh protocol-20 training database: 88 files,
schema SHA-256 `9a03bdaffe22413dee3e511f6e668214f1a84da66b5513c35c2aab9194b86858`.
The schema marks both new tables Private. A direct unsigned CLI SQL inspection
was rejected (403/sign-in required), so it does not establish private row counts.
The public endpoint remains the verified protocol-19 release; do not point the
worktree client at it. Use the new disposable protocol-20 database for QA.

Final evidence: `.local/mobs/aggro-runtime-r2/acceptance.json`, frozen module and
`multiplayer.json`, database `mt2-p2-aggro-runtime-r2-20260908`. All 108 two-account
checks pass, including a closer nonattacking observer not stealing the next attack
in either subscription, XP rewards, death/respawn and disconnect/reconnect.
All-target Rust tests (152 library tests) and full `tools/dev.py lint` pass.
The r1 protocol fixture passes six checks rejecting 19 and accepting 20; candidate
Rust table fixture passes 11 checks including three aggressive species out of 44.
Dedicated live passive retaliation and higher-threat switching now pass 42
checks in `.local/mobs/passive-runtime-r1/acceptance.json`, database
`mt2-p2-passive-runtime-r1-20260908`. Two real accounts use ordinary unarmed
attacks: the passive dog ignores proximity, retaliates, switches to the higher
threat while both players live, and stops attacking after that victim disconnects.
This training-only fixture is explicitly selected at build time and rejected for
Yongan builds. It does not install the original population or qualify restart,
party behavior or wandering. See `docs/development.md` for the replay command.

## Shared population catalog — 2026-09-08

`server/src/population_catalog.rs` now validates typed group membership and leader
ordering, equal-weight selector references, and regeneration entries (source line,
rectangle, interval, capacity and forced aggression). The real-map
`population_placement` tool consumes it instead of maintaining its own partial
JSON interpretation. Hash/provenance validation remains the caller’s obligation.
The current parser explicitly supports the selected group families g/ga/r;
additional families require implementation, not silent fallback.

Evidence: `.local/mobs/population-catalog-r1/acceptance.json`. Two targeted Rust
tests cover preserved data and 15 malformed cases; strict Clippy passes for the
changed example/test. Seed 42 reproduces all previous positions/headings exactly:
945 groups, 2,853 members, zero failed units/followers. The report now also records
forced aggression for every member. No protocol, database or deployment changed.
This prepares shared data for live integration; persistent dynamic spawn origins,
regeneration owners and surviving group members are still to be integrated.

The regeneration stress command now consumes the same typed population catalog as
placement. It rejects invalid group slots/leader flags, selector references,
rectangles and aggression flags before counting or restoring owners. Previously
its independent JSON interpretation omitted these checks. Evidence:
`.local/mobs/regeneration-catalog-r1/acceptance.json`; fresh checkpoint plus a
separate-process resume refill all 945 units, with 2,018 counted surviving
followers (4,981 upper-bound members after refill). Five malformed but correctly
rehashed inventories reject, and strict targeted example Clippy passes. This
remains an offline upper-bound simulation, not database persistence or map
placement evidence. No protocol, database or public deployment changed.

## Persisted spawn origins — 2026-09-08

Protocol 21 adds the private `monster_origin` table, initialized from the installed
spawn registry. Mutable monster positions and AI clocks no longer provide the
origin used by simulation/respawn: every actor (including dead mobs and the dummy)
must resolve its private origin before simulation. Missing origins, mismatched
IDs/definitions, changed homes and nonfinite coordinates reject. Current origins
remain bound to the authored registry; dynamic allocation and regeneration owner
records are not implemented by this change. No client reducer can create origins.
Existing databases require a deliberate migration before this module can be used;
QA uses a new database and preserves all existing worlds.

Bindings were regenerated from `mt2-p2-spawn-origin-r1-20260908`: 89 files,
schema SHA-256 `bb9896b98ac5b4a075065f770446093e7d2c7c740a67ef001b655492f3dd11d4`.
The public endpoint remains protocol 19. Do not aim the worktree client at it.

Qualification: `.local/mobs/spawn-origin-r1/acceptance.json` records 108 passed
real two-account combat checks (including death/respawn and disconnect/reconnect),
six protocol-gate checks rejecting 20/accepting 21, the focused origin validation
test and strict library Clippy. GDScript format/lint and generated-binding Godot
parsing pass. The schema explicitly marks the origin table Private. The first
protocol import hit a sandbox local-listener failure; its isolated rerun with
socket access passed. Server-process restart is not yet qualified.

## Combat validation through private origins — 2026-09-08

Target selection, physical attacker/victim snapshots, skill-area candidates,
knockback/reactions, rewards and AI definition lookups now resolve a monster’s
private origin before trusting its public state. The pure identity/stat check
receives the resolved spawn; the previous independent fixed-spawn lookup in
combat was removed. Simulation reuses the returned origin rather than querying
it again. The origin resolver still accepts only the installed authored registry;
this refactor prepares dynamic allocation without accepting arbitrary mob IDs.
Application protocol remains 21 and no binding/schema changed.

Evidence: `.local/mobs/combat-origin-r1/acceptance.json`, database
`mt2-p2-combat-origin-r1-20260908`. All 108 two-account melee/lifecycle checks
pass. The touched Rust areas pass 37 targeted checks (identity/presentation 2,
physical damage 21, special area 8, knockback 6), plus strict library Clippy.
No full-suite rerun was used. Dynamic population spawning and a live multi-target
finisher replay are not established by these checks. Public protocol 19 is unchanged.

## Group member ID allocation — 2026-09-08

`monster_allocation.rs` reserves an entire successfully placed group’s u32 IDs
with checked arithmetic before any rows are inserted. The first ID is its owner
token; followers receive distinct IDs. The persistent cursor must include every
previously issued member ID, even after destruction, and must initially exceed
all authored/reserved IDs. Exhaustion rejects the reservation without wraparound.
The caller must commit the cursor and member rows in one database transaction;
that database adapter is still pending.

The offline regeneration stress command now consumes this allocator instead of
incrementing one token per group. Its checkpoint format is version 2: version-1
owner-only counters reject because they do not reserve member IDs. Commands are
unchanged; create a fresh checkpoint. `.local/mobs/group-allocation-r2/acceptance.json`
records a separate-process resume across 945 units: the first population consumes
IDs through 2,963, replacement groups advance through 5,926, and counted surviving
followers remain. Two focused allocator tests cover non-reuse, partial placement,
invalid counts and exact u32 exhaustion. Strict example/test Clippy passes and a
legacy checkpoint rejects. This is offline evidence, not live group spawning.
Protocol 21 and the public protocol-19 build remain unchanged.

## Database-backed group allocation — 2026-09-08

Protocol 22 adds private `monster_allocation_cursor` and `monster_spawn_group`
tables plus `monster_origin.group_owner`. Initialization seeds the cursor above
all authored mob/dummy IDs. Trusted placement can reserve 1..256 member IDs,
insert their origins/group and advance the cursor; the caller inserts public
monsters and AI clocks in that same reducer transaction. Failed initialization
aborts the transaction. No client reducer exposes allocation. Authored origins
still match compiled records; allocated origins must belong to a persisted group
range, fit the cursor and resolve an installed species before combat accepts them.

The explicit `MT2_COMBAT_TEST_FIXTURE=allocated-wild-dog-v1` training fixture
uses the allocator during initialization. It is rejected for Yongan or combined
population overrides. Its one dog should receive ID 900002, above dummy 900001,
instead of authored ID 1. This proves allocation independently of fixed IDs; it
does not yet implement regeneration deadlines, release a group slot on leader
destruction or replace a killed group. The allocated dog currently follows the
existing life-sequence respawn policy. Original 44-species population remains
uninstalled. Existing databases are preserved; this schema uses fresh QA databases.

Generated protocol-22 bindings contain 91 files, schema SHA-256
`c05813aaab5aeae2820e665339403ec4779aa538113443b433d5bf5b8d55dd85`.
The public endpoint remains protocol 19, separate from worktree protocol 22.

Evidence: `.local/mobs/allocated-runtime-r1/acceptance.json`, fresh database
`mt2-p2-allocated-runtime-r1-20260908`. All 108 real two-account combat/lifecycle
checks pass; both final subscriptions contain allocated dog ID 900002, health 100,
life sequence 1 after respawn/reentry. Six protocol checks reject 21 and accept 22.
Focused origin tests, strict library Clippy, GDScript lint/format and generated
binding parsing pass. This one-member fixture does not prove multi-member
replacement, database restart, or regeneration leader-release behavior.

## Live regeneration adapter — 2026-09-08

Protocol 23 adds private `monster_regeneration` snapshots and a regeneration-entry
reference on private spawn groups. The existing regeneration state machine now
runs inside the server transaction: it restores the deadline/owner set, allocates
replacement member IDs and writes members plus updated state atomically. Corpse
destruction removes a member’s origin, clock, threat/damage and public row. Only
leader destruction releases unit capacity; surviving followers retain their group
membership. The group record is removed after its last member is destroyed.

The explicit `regenerating-wild-dog-v1` fixture installs one two-member training
group with a five-second regeneration interval, capacity one and startup jitter
zero. It uses the existing development corpse lifetime, not a claim of original
corpse timing. It is training-only and incompatible with population overrides.
Ordinary authored mobs and the allocation-only fixture retain existing respawn
behavior. This adapter is still bound to the selected fixture; the complete
original catalog/configuration, random group placement, party AI and original
population installation remain next work. Server-process restart is unqualified.

Bindings contain 92 files, schema SHA-256
`0fe5832ab4b175ae90c5df5564d075e5822e21a091373f7690b583068f8b7a64`.
Public protocol 19 remains separate from worktree protocol 23.

Evidence: `.local/mobs/regenerating-runtime-r2/acceptance.json`, database
`mt2-p2-regenerating-runtime-r2-20260908`, frozen module retained under r1.
All 66 real two-account checks pass: ordinary sword damage kills leader 900002,
its corpse retains capacity until destruction, follower 900003 remains, and
replacement members 900004/900005 appear in both subscriptions. Stale leader
targeting rejects; disconnect/reconnect preserves the same three IDs. Six protocol
checks reject 22/accept 23. Seven targeted allocator/scheduler tests and strict
library Clippy pass, along with touched Python/GDScript checks. The initial r1
scenario passed 64 checks before reconnect coverage was added; r2 is final evidence.

## Compiled regeneration settings — 2026-09-08

The live adapter now resolves `REGENERATION_DEFINITIONS` by entry ID for restore,
initialization and spawning. It no longer hardcodes entry 1, a five-second interval,
capacity one or the global mob-template list. Each compiled definition owns its
interval, capacity, startup jitter and template slice. The selected fixture’s
`regeneration` object supplies these values; the build rejects invalid IDs,
intervals above one day, capacities above 1,000 and jitter above 16 seconds.
Zero interval/capacity retain the scheduler’s disabled/no-capacity behavior.
The currently selected content still emits one two-member training entry. Other
builds emit an empty regeneration registry. This is not an installed original
population; source selector/rectangle compilation and randomized placement remain
pending. Protocol 23 and bindings are unchanged.

Evidence: `.local/mobs/regeneration-definitions-r1/acceptance.json`, database
`mt2-p2-regeneration-definitions-r1-20260908`. All 66 focused live regeneration
checks pass, including leader replacement, surviving follower, stale-target
rejection and reconnect. Two settings tests cover the checked-in/disabled values
and ten malformed cases; strict targeted Clippy passes. The first replay received
auth signup HTTP 429 before gameplay; the retry completed after the requested
300-second cooldown. The final compiler validation refinement produced a module
byte-identical to the frozen tested module. Unknown/missing setting fields reject.

## Group-area regeneration placement — 2026-09-08

Compiled regeneration definitions now optionally contain a rectangle in centimeters
and equal-weight group choices. The build validates ordered bounds, nonempty
bounded groups and installed species references. The server selects a group and
calls the same `npc_placement::sample_group` used by the world placement tool,
validating sampled positions against terrain/collision. It preserves sampled
headings, allocates only successfully placed members and returns a failed attempt
without consuming capacity when leader placement fails. Followers may partially
fail placement according to the shared source-backed sampler.

The selected training fixture now places its passive two-dog group in the
[750,750,850,850] cm area, instead of using fixed member homes. Its explicit marker
is `training-v7-regenerating-area-wild-dog-v1`. JSON `group_area` supplies
`bounds_cm` and `groups`; omitting it retains authored templates. This uses one
selected group choice; the compiler/runtime support for choices does not establish
that the original 945 entries/54 groups/44 species are installed. Source catalog
compilation, forced-aggression propagation, original party AI and startup random
jitter remain pending. Protocol 23 and bindings are unchanged.

Evidence: `.local/mobs/regeneration-area-r1/acceptance.json`, database
`mt2-p2-regeneration-area-r1-20260908`. All 67 live two-account checks pass,
including initial leader placement within the compiled rectangle, normal sword
combat, corpse destruction/replacement, follower survival, stale-target rejection
and reconnect. Three focused compiler tests cover settings, valid choices and
malformed bounds/unknown species; strict targeted Clippy passes. This is training
map runtime evidence, not a rendered original-world population qualification.

## Original regeneration compiler and entry policy — 2026-09-08

`server/examples/regeneration_compile.rs` verifies the original inventory hash,
map and selected regeneration-policy assumptions, then uses the shared catalog
parser to emit candidate `ORIGINAL_REGENERATION_DEFINITIONS`. It preserves source
line IDs, intervals, capacity, rectangles, equal-weight group choices and forced
aggression. Current Yongan output has 945 entries covering 44 species; its input
contains no forced-aggressive entries. The candidate is not automatically linked
into a server build.

Definitions now use `startup_jitter_max_seconds`: the server samples one integer
in 0..=maximum at initial enabled scheduling, then persists the resulting deadline.
Restoring a started entry uses its saved deadline and never resamples startup
jitter. Disabled entries consume no startup draw. Optional boolean
`force_aggressive` defaults false; entry aggression applies to retained followers
as well as leaders through their private group/entry membership. Protocol 23 and
bindings are unchanged. The training fixture retains maximum zero/false; live
nonzero-jitter and forced-aggression behavior remains separately unqualified.

Evidence: `.local/mobs/regeneration-policy-r1/acceptance.json`. Candidate emission
is byte-identical on repeat; its 945 entries compile against the actual generated
server structures and reference 44 species. The typed harness passes its registry
check plus seven included damage checks. Four focused settings tests and strict
Clippy pass. The fresh training database `mt2-p2-regeneration-policy-r1-20260908`
passes all 67 real two-account regeneration checks, including replacement and
reconnect, with its existing zero-jitter/passive policy. Public protocol 19 remains
unchanged; candidate installation and nonzero entry-policy live tests are pending.

## Assembled mob registry — 2026-09-08

The mob compiler now emits `MOBS`, assembling species, physical-table identity,
damage kinds and weighted actions into the actual `MobDefinition` shape. Original
`aggressive_sight` supplies acquisition distance. Candidate definitions select a
4,000-cm target-relative pursuit limit and normal ten-second NPC corpse lifetime,
based on the pinned source `char_state.cpp` combat-distance check and
`char_battle.cpp` dead-event scheduling. Revival-party/immediate-death exceptions
remain unsupported; this is the ordinary selected-population policy.

`target_chase_limit_cm: Some(...)` uses the original integer approximate distance
for pursuit, acquisition and nearest-victim ordering. Existing authored definitions
use `None` and retain their home-relative development limit. Original protection/
party following, idle wandering and health regeneration remain pending; these
policies alone do not establish full original AI. The full registry is still a
candidate, not installed with the original population or client content.

Evidence: `.local/mobs/complete-registry-r1/acceptance.json`. All 44 definitions
compile against current generated server types; the typed harness passes 11
checks, including all 4,400 weighted rolls across 78 actions and physical-table
linkage. Three focused Python tests, a pursuit-policy Rust test and strict library
Clippy pass. No new live replay was run: existing live content still selects the
authored policy, while the new candidate policy has only unit/type evidence.
No protocol, database or public deployment changed.

## Installed client mob catalog loader — 2026-09-08

`ActorCatalog.load_required` now optionally reads
`assets/imported/mobs/presentation.v1.json`. The normal catalog indexes its mob
actors/artifacts alongside the unchanged base character/item manifest, replacing
matching mob entries. Mob manifests cannot replace player actor IDs or introduce
artifacts outside their mob registry. Existing catalog validation still checks
model/motion links and duplicate definitions. `mob_gameplay_hash` is retained
separately; world compatibility rejects a missing/different `mob_catalog_hash`
when an installed manifest is present. Without a manifest, the existing empty-hash
path is retained. The server does not advertise that new field yet: a matching
server/package installation remains pending, and no manifest was installed into
the working client or public endpoint by this change.

The `test_actors.py --scenario mobs` staging workflow now installs the separate
manifest instead of rewriting the base profile. Evidence:
`.local/mobs/installed-loader-r1/acceptance.json` and `report.json`; all 1,446 native
Godot checks pass across 44 mobs, including matching/missing/wrong hash behavior
and a player-ID replacement rejection. Root reviewed captures for vnums 301 and
397 (models/materials visible through the normal loader). This remains controlled
actor-state rendering, not original-world multiplayer/export qualification. No
connected editor was inspected, and protocol/database/public deployment are unchanged.

## Selected server mob package and public hash — 2026-09-08

`MT2_MOB_CONTENT=/absolute/catalog-directory` selects a locally compiled package
containing `receipt.json`, `gameplay.v1.json`, `presentation.v1.json` and
`combat-registry.rs`. The build checks all three artifact hashes and matching
gameplay identities, then links its assembled `MOBS` and `PHYSICAL` registries.
Without the option, authored definitions remain selected. These are trusted local
compiler outputs; receipt hashes establish package consistency, not signatures.
Protocol 24 adds public `world_info.mob_catalog_hash` for the installed client
catalog gate. Bindings contain 92 files, schema SHA-256
`d39af557ae04d54d77a794d432b36a7fd07225eeb1db19b06bb54fc571fc2c1a`.

The mob generator emits exact f32 bit patterns for converted movement speeds,
preserving Rust’s previous rounded values while satisfying strict precision lint.
Selected builds retain displaced authored constants for independent fixtures;
only those generated constants receive a documented dead-code exception. The
whole generated module/lint configuration remains checked.

The full 44-definition registry is now linked in disposable training database
`mt2-p2-server-package-r1-20260908`. Its selected area fixture still spawns only
Wild Dogs (original 126 HP) and the dummy. This does not install original population
entries, copy the mob assets into the working client, or qualify every species in
live combat. Public protocol 19 remains unchanged.

Evidence: `.local/mobs/server-package-r1/acceptance.json`. All 74 real two-account
regeneration/combat checks pass, with the expected public mob hash and 126-HP dogs
in initial subscriptions. Six protocol checks reject 23/accept 24. The package
integrity test rejects changed catalog/presentation/registry bytes and mismatched
identities; three Python registry checks and selected-package strict library
Clippy pass. The normal rendered client’s matching-package qualification is next;
this run exercises the gameplay connection fixture, not exported Main rendering.
