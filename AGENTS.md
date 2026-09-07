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

Working alone is valid. If the harness supports subagents, use them for independent
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
