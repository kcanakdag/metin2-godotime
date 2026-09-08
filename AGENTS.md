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
4. Run focused checks while implementing. Review and integrate the complete slice,
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

Read each tool's `--help` and the development guide for required arguments.
Legacy guest smoke commands are not substitutes for authenticated multiplayer.
Raw Cargo defaults to the training world; Make normally enables Yongan, which
requires its baked content. A training-only result does not qualify Yongan.

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

Next connect those signals to flight creation and authoritative magic/projectile
combat so the prepared mobs
can become playable. `MonsterClock.pending_target` is private and the current
public Monster row has no target; introduce synchronized authoritative target
state with protocol/two-client QA rather than client-side nearest-player guesses.
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
