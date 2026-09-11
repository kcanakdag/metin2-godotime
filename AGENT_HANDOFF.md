# Agent handoff - Metin2 rebuilt on Godot + SpacetimeDB

- Written: 2026-09-11 ~15:45 CEST (Europe/Berlin) by the outgoing Codex session.
- Audience: the next coding agent or human taking over `/home/kcan/projects/mt2spacetime`.
- Read first: `AGENTS.md` (project rules and authorization model), then this file,
  then the newest entries at the top of `docs/rebuild/implementation-status.md`.

This document records observed state. Revalidate processes, endpoints and hashes
before restarting, publishing or claiming status.

## 1. State in one paragraph

The public playtest endpoint is live and freshly verified: release
`20260911T123640567701Z` on database `mt2-public-quests-v32-20260910` serves the
945-group Yongan world-population module and its matching Web export. The
repository is clean and pushed at `9af9b96`. All local services are stopped on
purpose (SpacetimeDB 3210, auth 3219, dev proxy 8184, Godot MCP 6505). The active
implementation slice is **combat polish** - held-space combo continuation, two
handed warrior weapons and skill learning. That slice has been investigated in
detail (section 5) but **no code has been changed yet**; the worktree is clean.

## 2. Repository and workstation state

| Fact | Value |
| --- | --- |
| Root | `/home/kcan/projects/mt2spacetime` |
| Branch / HEAD | `main` @ `9af9b96` "Record the public 945-group world-population deployment" |
| Remote | pushed to `origin/main` (`b4c86e0..9af9b96`); no unpushed commits |
| Worktree | clean, 0 modified/untracked tracked files |
| Disk | ~299 GB free of 915 GB (`/dev/nvme0n1p2`, 66% used) |
| Local stack | stopped - nothing listening on 3210 / 3219 / 6505 / 8184 |
| Chrome | CDP 9222 may still be running from earlier browser QA |
| Python tooling | `.local/venv-dev/bin/python` (activate with `. .local/venv-dev/bin/activate`) |
| Ignored state | `.local/`, `.cache/`, `dist/`, `assets/source/`, `client/assets/imported/`, `server/content/` |

Harness permission notes for this workstation: the sandbox is workspace-write.
`git add/commit/push`, `ssh`, `curl` and anything that binds a port require an
escalated command. The SSH prefix in use is
`ssh -o BatchMode=yes -o ConnectTimeout=10 root@159.195.213.9`; `curl` and
`git push` are also pre-approved prefixes. Nothing under
`/opt/metin2-godotime/backups` may be touched.

## 3. Public deployment (verified live during this handoff)

| Fact | Value |
| --- | --- |
| Client URL | `https://kcanakdag.com:8443/` |
| Health | `/health` -> `{"service":"metin2-godotime"}` |
| Release | `20260911T123640567701Z`, `phase: ready` |
| Database | `mt2-public-quests-v32-20260910`, `delete_data: never` |
| Module | `/opt/metin2-godotime/mt2_server.wasm` sha256 `ba665d3f7507f1f343183093ab35269fd359b9f765e0fb3b1ebe9cc32075051a` (3,720,905 B) |
| Module candidate | `.local/world-population-r1/mt2_server.maintain-r1.wasm` (same hash) |
| Web pack | `/opt/metin2-godotime/web/current` -> `releases/20260911T123640567701Z`; served `index.pck` sha256 `4db41122b687608511a634e0011a9a76ffcf257b8231497019a9d090b3840ab5` |
| Web candidate | `.local/world-population-r1/export/web-r8` (byte-identical pack) |
| Compiled issuer | `https://kcanakdag.com:8443/auth` (see `.local/world-population-r1/build-variants.json`) |
| Guests | disabled unless built with `MT2_ALLOW_GUESTS=1` (`server/build.rs:1614`) |
| Previous baseline | release `20260910T132257494611Z`, module `3f96b25aea5563059b1c6cc80966ae234ace7a1dd99effa49c2f088c47f26f9d` |

The deploy added the private `monster_regeneration_registry` table with 945
entries (a hot-swap top-up of `monster_regeneration`) while retaining the
protocol-32 quest catalog and account rows. This build is the user-authorized
**instrumented QA probe export**, not a friend/release package; normal builds
must strip probes, MCP bridges and evaluators.

Two inconsistencies to leave alone: `.local/world-population-r1/maintain-r1-receipt.json`
still says `published: false` because it was written before the publish step
(the release supersedes that field), and README line 49 still says two-handed
weapons are pending, which is still true.

## 4. What is implemented and evidenced today

- **Accounts and entry flow**: Better Auth service in `auth/` (Node/TypeScript)
  issues signed game sessions over HTTPS; the client implements the original
  login, server selection, character creation and character selection screens
  (`client/scripts/ui/classic_intro*.gd`, `account_flow.gd`). One account owns
  four character slots; only one controlling connection at a time.
- **Classes and appearances**: all four classic classes are playable with both
  male and female appearances converted offline from the pinned source archive.
- **Movement**: clients send bounded intents; the server owns position, speed,
  collision clamp and tick integration at 20 Hz (`TICK_MS = 50`,
  `server/src/lib.rs:67`), clients smooth toward authoritative state.
- **Combat**: per-class basic attacks, the warrior one-hand four-step combo,
  monster damage/threat/aggro/knockback, skill reactions and selected skills.
  All 44 classic class skills have definitions, formulas and imported motions
  prepared, but only a subset is installed and playable - do not describe all 44
  as playable.
- **World population**: Yongan map baked with 945 monster spawn/regeneration
  groups, town NPCs with dialogue, server-side drop tables and ground items.
- **Quests**: a real protocol-32 server-authoritative runtime
  (`server/src/quest.rs`) with a compiled classic catalog limited to four quests
  (`main_quest_lv1`, `main_quest_lv2`, `main_quest_lv3`, `find_squareguard`);
  content breadth is future work.
- **Tooling**: map/UI/character/skill/particle importers under `tools/`,
  the world-content pipeline (`docs/world-content.md`), Godot scenario runners,
  two-client authenticated harnesses and `tools/deploy.py` with the
  regeneration-registry hot-swap guard.
- **Exports**: Web (Emscripten) and native Linux playable exports, both exercised
  with two authenticated clients; the newest acceptance run
  (`.local/world-population-r1/acceptance/browser-r27/report.json`) passes
  124 checks with 0 failures and 0 browser engine errors.

Scope accounting: `docs/rebuild/plan.json` holds 194 catalogued features -
47 `partial`, 117 `planned`, 21 `reference-only`, 9 `decision`. Treat the ledger
entries, not the counts, as the evidence of record.

## 5. Work in flight: combat polish (investigated, no code changed)

User request: "combat feels a bit weird, like pressing down space should do the
combo fully with or without a target", plus skill learning, missing scenery and
two-handed warrior weapons. Findings from reading the current implementation:

1. **Dead targets abort held chains.** `server/src/combat.rs:844` `kill_monster`
   calls `combo::clear_chains_targeting` (`server/src/combo.rs:133`), which
   clears held-chain state for every controller chaining at that monster. Held
   presses after the kill re-plan from scratch, which reads as "combo stopped
   working".
2. **The terminal step rejects instead of continuing.** In
   `server/src/combo.rs:295` `handle_follow_up`, `COMBO_STEP_FOUR` returns
   `BOUNDED_ERROR` ("This combo is complete.") until
   `now >= combo_action_ends_at_us`, then clears the chain and returns
   `Ok(false)`. A held input during the fourth action gets a rejection
   round-trip instead of silently starting a fresh chain.
3. **Expiry path.** `server/src/combo.rs:348` `resolve_due_transitions` clears
   any chain whose action end has passed. There is no server-side "held input
   starts the next chain in the same tick" path; the client is expected to send
   a fresh attack.
4. **One-hand assumption in the cooldown rule.**
   `server/src/combat.rs:583` `fresh_action_not_before` applies
   `max(cooldown, action_end)` only when the definition is in
   `definitions::PLAYER_ONEHAND_COMBO` (`server/src/combat.rs:587`). This must
   be generalized for two-hand and other class chains.
5. **Hardcoded one-hand chain.** `server/src/characters.rs:73` `requires_weapon`,
   `:85` `combo_start`, `:94` `combo_step` and `root_actions` special-case
   `PLAYER_ONEHAND_COMBO` for `actor.player.warrior-male` with weapon vnum 10
   (see `characters.rs:99`).
6. **Client drops presses.** `client/scripts/actors/attack_input.gd` blocks while
   a `perform_attack` reducer is in flight (`_pending`), throttles sends by
  150 ms, and applies a client-only `+30000` us fudge in `_in_combo_window`
   that the server does not share - with RTT the two windows disagree and the
   client can drop a press instead of re-queuing it. Driver hooks:
   `client/scripts/main.gd:150` `_request_attack`, `:156` `_update_held_attack`,
   `:103` `reducer_completed`; chain lifecycle in
   `client/scripts/actors/attack_input.gd:33` `reset`, `:42` `release`, `:54`
   the 150 ms throttle and `:94` the client-only window fudge.
7. **Original behavior for reference.** In the pinned historical server the
   combo was a client-driven animation index only (`char.cpp`
   `m_bComboSequence`; no combo logic in `battle.cpp`). Our server-side per-step
   validation is deliberate; polish should improve acceptance and queueing, not
   move combo timing to the client.
8. **Source timings** (`server/content/p0-warrior-dog/actions.v1.json`,
   cooldown 850 ms for every step): combo_1 1,000,000 us
   (pre/direct/limit/link 167094/533333/602564/58889); combo_2 933,333 us
   (100513/543248/636581/19658); combo_3 1,066,667 us
   (84786/418462/664615/60171); combo_4 1,266,667 us terminal with no
   combo/input block.

Suggested change order (one coherent slice, preserve authority):

- Server: when a chain would end because its action expired and the controller
  still holds the attack intent, start the next chain in the same tick instead
  of returning `BOUNDED_ERROR` for the terminal step.
- Server: on `kill_monster`, keep the chain alive (re-target or continue in
  place) when the input is still held; otherwise clear as today.
- Server: generalize `fresh_action_not_before`, `characters::combo_*` and
  `root_actions` to data-driven per-mode chains keyed by (actor, weapon mode) so
  two-hand and other classes work without new special cases.
- Client: share the server combo-window constant and re-queue rather than drop a
  press that arrives while a reducer is in flight; keep the 150 ms throttle.
- Tests: `server/src/combo.rs` unit tests (~398-808), `server/src/combat.rs`
  deadline tests, `server/tests/build_combo.rs`, `tests/test_combo_content.py`,
  `client/tests/held_attack_smoke.gd` (currently passes a `null` catalog - it
  should use the real one), `client/tests/combo_smoke.gd`, and the two-client
  authenticated `tools/test_combos.py`
  (`--server http://127.0.0.1:8184 --database <db> --report <path>`).

## 6. Next milestones in order

1. **Finish combat polish** (section 5) including two-handed warrior weapons.
2. **Skill learning and upgrading**: `server/src/skills.rs` already has
   `learn_skill` plumbing used by `client/scripts/net/game_connection.gd:978`;
   add upgrade/level reducers, the classic skill window UI, and developer
   `/commands` to grant level/skill points, then wire the full per-class trees.
3. **Two-hand warrior weapons**: the pinned archive revision
   `bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7` contains `twohand_sword/`
   (male+female `pc2`, plus horse) that is not yet local - fetch it with the
   escalated `curl`. Add `"twohand": "TWOHAND_SWORD"` to
   `tools/character_definitions.py::registered_combo_chains`, extend
   `content/profiles/p0-warrior-dog.json` modes and
   `equipped_item_models.equipment_modes`, pin the GR2/MSA inputs in
   `server/build_combo.rs`, and attach to `equip_right_hand`. Original chains:
   TYPE_1 01-04; TYPE_2 01,02,03,05,07; TYPE_3 01,02,03,05,06,04.
4. **Missing scenery (trees)**: 368 SpeedTree placements in Yongan are currently
   unsupported by `tools/import_metin_map.py` (Tree/Effect marked unsupported
   around lines 79-86). Inputs live under
   `assets/source/maps/bb19e9ab.../bin/pack/Tree/ymir work/tree/*.spt`. Planned
   route: Wine plus `i686-w64-mingw32-gcc` for `tools/speedtree_probe.c`
   executed under `bwrap --unshare-net`; a direct `.exe` run was already
   auto-review-rejected, so do not retry that form.
5. **Item coverage audit** against the pinned item data, continuing the
   duplication/exploit hardening that `server/src/item_security.rs` starts.
6. **Documentation refresh**: `docs/characters.md` (still says advanced combos
   are imported but not enabled), `docs/skills.md`, and `README.md:49`.
7. **Quest content expansion**: the runtime is done; only four classic quests are
   compiled. The user deferred more quests until gameplay and world population
   landed, which has now happened, so this follows the items above.

## 7. Authority and security model (answer to the user's open question)

The user proposed a Godot/SpacetimeDB split and asked whether it is correct and
whether server authorization is safe. The split is right; the mapping against
the actual code:

| User's diagram | Reality |
| --- | --- |
| Godot: Input / character controller / animation tree / camera | Local presentation: `client/scripts/main.gd`, `client/scripts/actors/attack_input.gd`, `client/scripts/actors/player_actor.gd`, `client/scripts/actors/pve_actor.gd`, per-actor animation trees, `client/scripts/camera/orbit_camera.gd` |
| Godot: Local prediction | Intents only (`set_move_input`, `move_to`, `perform_attack`) plus immediate local motion, then exponential smoothing toward the authoritative position (`1 - exp(-delta * k)`) in `client/scripts/actors/player_actor.gd` / `pve_actor.gd`. No rollback or reconciliation |
| Godot: Interpolation | Smoothing of replicated state; server tick is 20 Hz (`TICK_MS = 50`, `server/src/lib.rs:67`) |
| Godot: VFX / UI | Converted original particles and projectiles; classic UI in `client/scripts/ui/classic_*.gd` |
| SpacetimeDB: authoritative position, velocity/state | `server/src/movement.rs` - clients never write positions for themselves or others |
| SpacetimeDB: combat state, stats, cooldowns | `server/src/combat.rs`, `server/src/combo.rs`, `server/src/skill_*.rs`, `server/src/physical_damage.rs`, `server/src/attack_timing.rs`, `server/src/progression.rs` |
| SpacetimeDB: inventory, equipment | `server/src/inventory.rs` plus appearance/equipment tables, account-filtered |
| SpacetimeDB: NPC state, spawn state, drops | `server/src/npcs.rs`, `server/src/npc_spawns.rs`, `server/src/npc_placement.rs`, `server/src/monster_spawns.rs`, `server/src/population_catalog.rs`, `server/src/monster_allocation.rs`, `server/src/drops.rs` |
| SpacetimeDB: guilds, parties | **Not implemented.** Only damage-formula hooks (`party_attack_bonus`, `party_defender_bonus` in `server/src/physical_damage.rs`), threat-table party staging in `server/src/mob_threat.rs`, and "No Guild" / "-" UI placeholders |
| SpacetimeDB: quests | Real runtime (`server/src/quest.rs`, protocol 32), four compiled classic quests |
| SpacetimeDB: persistence | SpacetimeDB tables plus admin rate-limit, receipt, collision and audit tables (`server/src/admin.rs`) |

Why the server is safe to expose (all verified in source):

- **Identity**: Better Auth issues signed sessions; the module pins the issuer
  and audience and requires `Identity::from_claims(issuer, subject) ==
  ctx.sender()`, rejecting untrusted issuer/audience/identity/subject on every
  credential path (`server/src/accounts.rs:75`, `:89`, `:112`, `:433`).
- **Private reads**: `client_visibility_filter` with `:sender` scoping covers
  account list/state, inventory (items and access), progression, skills, buffs,
  quest state/objectives/selections, NPC interaction, combat target view and
  admin command feedback.
- **Reducers**: validate finite values and ranges, clamp movement to the map
  limits and speed budget (`movement.rs`), enforce cooldowns and action
  deadlines, and check target life sequences/generations before committing
  damage, rewards or items.
- **Simulation**: the tick reducer rejects any sender that is not the database
  identity (`server/src/lib.rs:597`) - clients cannot drive ticks.
- **Admin**: progression commands require a server-side capability
  (`has_progression_capability`, `server/src/admin.rs:1191`), are rate-limited
  per account, deduplicated with request receipts and collision detection, and
  recorded in immutable audit rows.
- **Guests**: off by default at build time (`MT2_ALLOW_GUESTS`, `build.rs:1614`).

Honest caveats to state to the user:

- Visibility filters are replication read-filtering, not encryption. Security
  lives in the reducers, because any authenticated client may call a public
  reducer; that is exactly how this project is built, and it is why reducer
  validation and the two-client rejection tests matter.
- The client is untrusted by design: editing the Godot build cannot grant items,
  XP, position, damage or privileges.
- There is no rollback netcode; "local prediction" is intent plus smoothing.
- Guilds and parties are the main missing social systems.
- Legacy-server security findings are logged with rebuild responses as
  OSS-001..OSS-010 in `docs/rebuild/original-security-notes.md`.

## 8. Constraints, preferences and landmines

- **Solo implementation is the user's explicit preference**: do not spawn
  subagents unless the user changes that instruction.
- **Testing**: run focused checks for the touched behavior while iterating; run
  the full gate (`make check`) only at milestone boundaries or on evidenced
  broad impact. The user asked for this to keep turnaround fast.
- **Never publish a local-issuer module.** Local QA compiles
  `http://127.0.0.1:8184/auth`; production is
  `https://kcanakdag.com:8443/auth`. `AUTH_ISSUER` (service) and
  `MT2_AUTH_ISSUER` (module) must match exactly, including `/auth`.
- **Never print credentials.** Private account fixtures live in
  `.local/p6-charge-r2/private.json`; keep them out of logs and reports.
- **Replica storage**: never hand-delete `<data-dir>/replicas/`. Use
  `make storage-report`, `make storage-sweep` (scheduled Mondays 04:17) and the
  reviewed `make storage-clean`. Do not wipe a data directory to free space.
- **Remote backups**: `/opt/metin2-godotime/backups` (~23 GB) is off limits.
- **Probes** (`window.mt2ProbeEnabled`, `--probe-report`, `--probe-commands`)
  belong only in explicitly authorized QA builds; ordinary launches must not
  install callbacks. See `docs/distribution.md#browser-test-builds`.
- **Hot-swaps**: read
  `docs/development.md#regeneration-registry-hot-swap-hazard` before publishing
  a module over an existing database. `tools/deploy.py` refuses a swap whose
  regeneration-registry receipt is empty unless `--allow-empty-regeneration` or
  `--reset-database` is passed. Use a fresh, explicitly named database for
  incompatible schemas.
- **Assets**: the user wants the original assets and a UI indistinguishable from
  classic Metin2, with provenance tracked in `docs/third-party.md`. Extend only
  the selected fixtures needed by a feature; fix generators instead of editing
  generated output, `.godot`, or downloaded sources.
- **Ledger discipline**: append new entries at the top of
  `docs/rebuild/implementation-status.md` with actual commands, hashes, report
  paths and remaining limits; update README/architecture docs when contracts,
  commands, controls or exports change.
- **Preserve others' work**: the worktree may contain other agents' uncommitted
  files; stage only intended changes and never reset the tree.

## 9. Restart and verification cheat sheet

```sh
cd /home/kcan/projects/mt2spacetime
python3 tools/dev.py setup                 # fresh checkout only
. .local/venv-dev/bin/activate

make server-start                          # SpacetimeDB on 3210
AUTH_ISSUER=http://127.0.0.1:8184/auth make auth-start   # auth on 3219
MT2_AUTH_ISSUER=http://127.0.0.1:8184/auth make server-publish
make bindings
node tools/serve_local.mjs                 # dev proxy on 8184

make client SERVER_URL=http://127.0.0.1:8184 PROFILE=alice
make client SERVER_URL=http://127.0.0.1:8184 PROFILE=bob
```

Godot MCP bridge: `npm --prefix tools/godot-mcp-server run start` (127.0.0.1:6505)
with the project open in the editor; setup and troubleshooting in
`docs/godot-mcp.md`. No other server may own port 6505.

Focused checks: `python3 tools/dev.py lint --only rust|gdscript|python|typescript`,
`make server-test`, `make test-tools`, `make test-map`, `make test-actors`,
`make test-classes`, `make test-ui`, `tools/test_browser_accounts.py` for the
exported browser route. Resolve tool paths from `Makefile` and
`docs/development.md`; `GODOT`, `BLENDER`, `SPACETIME`, `SERVER_URL`, `DB`
overrides are documented there.

Public verification (needs escalated network access):

```sh
curl -sS https://kcanakdag.com:8443/health
ssh -o BatchMode=yes root@159.195.213.9 \
  'cat /opt/metin2-godotime/deployment-status.json; sha256sum /opt/metin2-godotime/mt2_server.wasm'
```

## 10. Open risks and known inconsistencies

- Combat polish has **no code changes yet**; the worktree is clean and the slice
  starts from the findings in section 5.
- `.local/world-population-r1/maintain-r1-receipt.json` reports
  `published: false`; the live release supersedes it. Do not redeploy to "fix".
- `README.md:49` and `docs/characters.md` contain stale two-handed/advanced-combo
  wording; update them when that work lands.
- Only a subset of the 44 prepared skills is live; never claim all are playable.
  The six-skill Yongan candidate and the protocol-31 self-buffs are qualified
  candidates, not necessarily what the public module installs.
- The Web export runs at a few frames per second under software rendering
  (llvmpipe), so timing checks must read subscribed server state rather than
  expecting an animation frame to still be playing.
- Quests: the runtime is production-grade, the content is not; four classic
  quests are compiled today.
