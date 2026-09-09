# Rebuild implementation status

This execution ledger begins the implementation phase after the source-backed
planning deliverable. It complements the [full rebuild plan](../full-rebuild-plan.md)
and its canonical [feature catalog](plan.json); it does not replace, collapse,
or reclassify that scope.

## Player cooldown source rounding corrected — 2026-09-09

The full-class linker now truncates player cooldown formula results to seconds
before converting to microseconds, matching pinned `char_skill.cpp::UseSkill`.
It validates finite bounds before truncation; negative fractions cannot become
accepted zeroes. The Rust compiler independently rejects fractional-second base
cooldown tables. This is specifically player behavior: `UseMobSkill` uses a
different conversion and was not changed.

Three focused Python tests and nine Rust example/compiler tests pass. The rebuilt
44-skill/88-appearance candidate at `.local/p6-buffs-r1/catalog.v2.json` has SHA
`381206c5edffd7ab2fa26c7bc05d1d4188b6a762e1ce9916cc39e70d80d8fe21`.
Its `qualification-r2/report.json` passes 21,120 formula evaluations, 309 metadata,
88 motion-window and 88 geometry comparisons, plus six Three-Way Cut replays.
`cooldown-comparison.json` checks all 924 values against truncation of the prior
candidate: seven skills change, while the five installed abilities' cooldowns
are unaffected. Scoped format/lint and diff checks pass.

The first rebuild attempt supplied the stripped runtime character catalog and
failed for missing `unsupported_motion_metadata`; the successful build uses
`.local/p6-class-skills/characters-r4/normalized.v1.json`. The previous candidate
and installed content are preserved. No server/client publication occurred.
Next integrate trusted Berserk value capture with the timed-buff core, followed
by authorized persistence and stat/damage adapters; Berserk is still not playable.

## Shared timed-buff lifecycle started — 2026-09-09

The next gameplay slice is Berserk with reusable multi-point timed buffs. Source
review confirmed its attack/movement speed pair, incoming-normal-damage penalty,
replacement semantics and persisted remaining duration. It also identified a
fractional-cooldown discrepancy in the prepared full-class compiler; see
`docs/skills.md` for the pinned reference and exact integration requirements.

`server/src/buff_lifecycle.rs` now provides atomic validated per-skill replacement,
independent point expiry, remaining online ticks and bounded derived bonuses.
All **four focused Rust tests pass** both standalone and through the actual Cargo
library (`--lib buff_lifecycle`, 184 unrelated tests filtered). Rust formatting
and diff checks pass. Cargo reports the existing unused `MONSTER_HOME` warning
in the default training build. No server publication or asset installation took
place. This core is not a playable buff: trusted value compilation, persistent
authorized activation, stat/damage integration, visuals and multiplayer QA are
the next work; five abilities remain playable locally.

## Probe batching removes reproduced first-cast stall — 2026-09-09

The fixed runtime from `c7c79fa` is exported at `.local/p6-probe-batch-web-r1/web`,
served locally on 8186 with manifest hash
`e805011c444c82911869d7d46bbf7514f8c16c25bf2c0e5f9c4afb0ae3158e1d`.
The module/database/auth services are unchanged; public deployment is unchanged.
All **25 populated two-browser checks pass** in `browser/report.json`, with no
browser engine errors. The same dummy life loses 142 HP at rank 12 and both
clients spawn the original effect. Core/map export checks completed.

The first-cast acknowledgement falls from **4,419 ms to 121 ms** versus the
profiled pre-fix build. Its monster dispatch falls from **4,385,700 us to 60,500 us**
on the caster and from **4,148,200 us to 50,200 us** on the peer. Initial monster
dispatch is also below 42 ms on each client. This verifies the reproduced
multi-second dispatch stall was caused by repeated QA history publication.
It is a test-probe fix, not proof of a corresponding improvement in ordinary
exports that exclude the probe.

Caster input-to-action/damage observation is **943 ms** including automatic
approach and snapshot cadence. The peer first publishes action/damage after
**1,987 ms**, together with its effect; caster effect observation is at 2,109 ms.
That remaining observer/publication delay is not claimed fixed. These are single
casts in successive fresh browser sessions; setup increased skill rank between
runs. The 45-check native batching regression and this exported replay qualify
the focused fix, not full population scalability or original visual parity.

## First-cast stall traced to monster dispatch; probe batching fix prepared — 2026-09-09

Profiled export `.local/p6-profile-web-r1/web` has served manifest hash
`643662dca3eef9b2b7420b6396cd0089622394f67b51ce0e079d00101f448356`.
All **25 populated two-browser checks pass** in its `browser/report.json`.
The caster's cast acknowledgement takes 4,419 ms. The immediately preceding
monster flush spends only **4,100 us converting rows but 4,385,700 us in
synchronous dispatch**. The peer records 3,300 us conversion / 4,148,200 us
dispatch for the corresponding update. This rules out row conversion as the
dominant cost in that run. The existing QA database/module and public release
were preserved; local proxy 8186 serves this profiling export.

Inspection then found an export-probe inefficiency: `_capture_monster_action`
serialized and published its entire bounded history once for every changed row.
The connection-state callback clears comparison caches, so the first subsequent
monster update can repeat this thousands of times. The probe now captures each
record but publishes once after the complete monster update. Ordering and the
256-record bound are preserved; unchanged updates do not republish. No gameplay
or SDK callback ordering changes were made.

The fixed probe passes **45 actual Godot checks** at
`.local/p6-probe-batch-r1/report.json`, including a 2,800-row publication-count,
retention/order and unchanged/single-change regression. Scoped checks pass.
An exported before/after replay is still required to establish that this removes
the first-cast stall; the native fixture alone does not prove browser latency.

## Per-table snapshot profiler prepared — 2026-09-09

`GameConnection` now optionally measures conversion and synchronous dispatch
separately for each flushed table. Ordinary clients have no profile listener and
do not sample clocks. The activated export probe retains at most 64 records of
50 ms or longer, containing only table/count/timings, and the browser skill runner
saves both clients' traces. Decode, deferred rendering and server time are not
included in these phases. This is diagnostic work, not a claimed latency fix.

The actual-engine run `.local/p6-snapshot-profile-r2/report.json` passes **12
snapshot/cache checks and 41 probe checks**. The first fixture attempt used the
wrong SDK schema constructor; its preserved failure is corrected in r2. Scoped
Python/GDScript checks pass. Browser export/measurement is the next qualification.

## Same-session repeat points to first-use cast cost — 2026-09-09

The browser runner now supports one to three same-rank Dash casts without
relearning, restarting clients or bypassing cooldown. It reuses the unchanged
timing export above (manifest `fdf15d0bd1c7f076f3f4aab69f1c7a3dfca0478a79f0700f3bd751afb56ce810`).
The three-cast attempt is retained at `.local/p6-request-web-r1/repeated/report.json`.
It is **not a passing full replay**: 41 checks completed before the caster entered
`loading` during the third sample and dummy lookup raised `StopIteration`.
The runner now reports that lost fixture/loading state explicitly; this diagnostic
wording change was made after the attempt. Scoped Python lint/format checks pass.

Both completed rank-10 samples retain separate acknowledgements and matching
dummy-life damage/effects on both clients. The first cast acknowledgement takes
**4,349 ms**, while the second takes **94 ms**. Caster input-to-action/damage falls
from **5,064 ms to 881 ms**; peer observation falls from **5,207 ms to 866 ms**.
This strongly suggests a first-use cost rather than a persistent multi-second
approach delay. It does not identify the expensive function or prove all repeat
casts are fast. Inspection confirms the pinned SDK applies transaction updates
and invokes their listeners before emitting its reducer response, so that measured
duration includes synchronous client subscription handling. Next profile that
handling around the first cast; do not choose a renderer/server fix from timing
alone. Auth refresh/loading behavior in the longer replay remains unqualified.

## Populated-browser request timing: delay concentrated at cast — 2026-09-09

Source `e1d0b25` was exported to `.local/p6-request-web-r1/web`; its served
manifest hash is `fdf15d0bd1c7f076f3f4aab69f1c7a3dfca0478a79f0700f3bd751afb56ce810`.
Local proxy 8186 now serves this package against the unchanged protocol-29
original-population QA database. Auth and database services were preserved;
the public release is unchanged. Export/package checks completed.

All **25 two-browser checks pass** in `browser/report.json` with no browser
engine errors. Rank-9 Dash changes the same dummy life from 29,215 to 29,089 HP,
with one effect on each client. The ordinary stop baseline takes 307 ms from
send to callback. Dash's begin takes 287 ms, move 33 ms and stop 50 ms, but its
final cast takes **4,547 ms**. Cast and stop were sent in the same local
millisecond (receipt minus elapsed duration); their server timestamps differ
by 14,571 us. Those timestamps do not measure reducer completion time.

The caster sees action/damage 5,299 ms after browser keydown and the peer sees
them after 4,875 ms. This localizes the dominant observed delay to the final
cast/response path, not the brief automatic approach. It does not yet separate
server execution, transport, callback processing or first-use rendering work.
The standalone server's `/metrics` route returned HTTP 404; no execution-time
measurement was obtained there. Next compare repeated casts in the same browser
session at the same rank to test first-use costs before selecting an optimization.

## Per-request charge timing prepared — 2026-09-09

The explicitly activated export probe now retains 64 typed acknowledgements for
charge begin, move, stop and cast, with local receipt time and that request's
send-to-callback duration. Local send failures record null rather than a stale
previous duration. No gameplay, server, protocol or permission changes are made.
`test_browser_skills.py --request-timing` requires an ordinary stop baseline and
the final cast acknowledgement, and saves the intervening request records.

The actual Godot probe regression passes **39 checks** at
`.local/p6-request-timing-r2/report.json`; touched GDScript/Python lint and format
checks pass. The first run exposed stale protocol-15 and implicit-activation
assumptions in the fixture; both are corrected and its failure log is preserved
under `p6-request-timing-r1`. The probe still requires explicit activation in
ordinary launches. These are component checks; the new timing fields have not
yet been exported or measured in the populated browser replay. Local/public
served packages are unchanged. Next export this probe and replay with
`--skills 5 --original-world --request-timing` against the existing QA database.

## Browser snapshot-cache comparison: delay not resolved — 2026-09-09

The optimized source `94dc6c2` was exported to `.local/p6-snapshot-web-r1/web`;
served manifest SHA-256 is
`a921493cd496f7ca20b98f6f09298789a8e2cad6bd6db250af1e73d5fa63af16`.
Local proxy 8186 now serves it on the unchanged original-population QA database.
The baseline served manifest was verified against the previous r4 export before
switching. Core and map export audits completed. Public deployment is unchanged.

Added browser-side keydown and first snapshot-observation timing to the existing
skill replay. The Node-backed helper test passes, as do touched Python checks.
Both baseline and optimized full-map runs pass all 23 checks, including Dash
damage/effect replication, with no browser engine errors. Reports are
`baseline/report.json` and `optimized/report.json` in that evidence directory.

| Input to published observation | Baseline caster / peer | Optimized caster / peer |
| --- | --- | --- |
| New action and matching-life damage | 4,823 / 4,954 ms | 4,992 / 4,776 ms |
| New effect instance | 6,076 / 6,237 ms | 6,331 / 6,090 ms |

This single cast per build does **not** show an end-to-end latency improvement.
The native conversion microbenchmark below remains valid but is not the dominant
explanation established by these observations. Timings include automatic charge
approach, browser work and the 200 ms test snapshot cadence; successive replays
also spend another skill point. They are not reducer RTT or a controlled broad
performance benchmark. Next distinguish ordinary request latency from charge's
begin/move/finish timing using existing validated intents and acknowledgements.

## Reuse unchanged monster snapshot conversions — 2026-09-09

Inspection found the facade reflected every field of every subscribed monster on
each monster-table update. It now reuses read-only converted dictionaries for
unchanged SDK row Resources, invalidates replacements/updates, prunes removed
resources at each flush and clears on world exit/client retirement. The pinned
SDK replaces row Resources on update; no vendored SDK changes or protocol changes
were needed. Full subscriptions, signals and authoritative validation remain.

The isolated real-Godot cache fixture passes 9 checks and the Main content fixture
passes 42 at `.local/p6-snapshot-cache-r1/report.json`. In the accompanying native
microbenchmark, 20 snapshots of 2,800 unchanged rows take 352,275 us through the
uncached conversion path versus 27,835 us through the warm cache (about 12.7x).
This measures only conversion work, not full-world FPS or command delay.
All **84 live account/multiplayer checks pass** at `network.json`, using two new
unprivileged authenticated accounts on the existing full-population QA database,
including movement/action updates, disconnect and reconnect. Touched Python and
GDScript lint/format checks pass. Browser latency improvement remains unmeasured;
the served local and public exports do not yet contain this optimization.

## Full-population Dash effect failure resolved in browser replay — 2026-09-09

Source `6bfff67` was exported to `.local/p6-dash-world-r4/web` and exercised against
the unchanged full-population QA database/module recorded below. The new manifest
SHA-256 is `1a9b570e4b1728f2b02f0fe1860c3d9e390c328341e4ef1277cf1b6739ed6d8b`.
The 1,555-file core audit, 243-image UI pixel audit and all 20 isolated map-section
dependency audits pass. Local proxy 8186 now serves this export; its previous
configuration and PID are retained in this evidence directory.

**All 23 focused two-browser checks pass** in `browser/report.json`, including
the shared original population, learning/dragging/hotbar input, action and damage
replication, and one new effect instance on each client. Rank-6 Dash reduced the
same dummy life from 29,551 to 29,444 HP in both subscriptions. Both clients loaded
the expected effect hash, and no browser engine errors were reported. This
resolves the reproduced zero-spawn failure without changing the server module.

Reviewed cast frames `browser/cast-peak-0.png` and `cast-peak-1.png` show the
blue-white original burst in both views (video positions about 89.46 and 104.21 s).
The observer's effect is partially clipped by the bottom viewport edge; the
caster's view shows it clearly. The closing 20-second contact sheets missed the
earlier burst, so they were not treated as visual acceptance. Source videos remain
in `browser/videos`. This qualifies a male Warrior town/dummy cast with the full
population loaded, not every map section, moving-target browser behavior, female
browser casting, precise original visual parity, or resolution of the previously
observed multi-second reducer delay. Public protocol-26 deployment is unchanged.

## Attack-observation trace and clock-driven effect flush — 2026-09-09

Added a bounded read-only `last_action_observation` to player presentation
snapshots. The diagnostic Web export at `.local/p6-dash-world-r3/web` has manifest
SHA-256 `65c1e56f71193f2472a46ef2eba1848cf4060546c2120fd3580db5dfdb3094ef`.
Its browser replay reproduces the failure, but **rules out initial expired-action
rejection in that run**: both clients first observe sequence 5 as activity 2,
same life, `live_attack=true`, with 848,613 us remaining. The observed simulation
clock is 48,613 us before the action starts. Both still spawn zero effects.
Evidence: `.local/p6-dash-world-r3/browser/report.json`. The diagnostic change
passes 42 Main content checks in `.local/p6-action-observation-r1`.

Inspection confirms the transport drains queued packets within a frame and Main
defers/coalesces player reconciliation. A motion can consequently be replaced
before animation polling emits its early effect. The next implementation retains
the motion's authoritative start and flushes due visual events through the
observed server clock before applying another same-life player state. It clamps
to the motion duration and reuses event consumption to prevent duplicates.
Different lives, first clock initialization, frozen poses and action reset do not
flush old events. Projectile policy and gameplay damage remain unchanged.

The focused real-Godot playback fixture passes 35 checks at
`.local/p6-live-effect-r3/report.json`, including multiple state updates without
a render frame, repeated flushes, pre-start clocks, final events and reset.
Touched GDScript lint/format checks pass. **The clock-flush change has not yet been
exported or browser-qualified.** Local proxy 8186 still serves the earlier
diagnostic export on the existing full-population QA database; public deployment
is unchanged. Next export the clock-flush change and rerun the focused Dash case.

## Delayed live-effect handling: component pass, world failure persists — 2026-09-09

`PlayerActor` now identifies an increasing attack sequence on an already observed
life. While that server action is still active, it requests one-time catch-up of
elapsed visual events from `ActorPresentation`. Initial subscriptions, replaced
lives, clock initialization and forced resyncs retain historical-event suppression.
Projectile launch scheduling is unchanged. The focused real-Godot fixture passes
30 checks in `.local/p6-live-effect-r1/report.json`; touched GDScript lint and
formatting pass. This fixes the isolated early-event suppression path.

The actual updated full-map Web export is `.local/p6-dash-world-r2/web`, manifest
SHA-256 `366ba0906c4b5e62cff07de230ceac065f25b5a85bb12374037501f1615e09da`.
It uses the unchanged QA database/module recorded below. The local proxy now
serves this export; previous proxy configuration and current PID are recorded in
the new evidence directory. Its core/map export audits pass.

The browser replay **still fails** effect spawning after passing 21 checks through
replicated damage. Evidence: `browser/report.json`, `browser.log` and captures.
Both clients report zero effect spawns, no renderer error, correct effect hash,
and failure-time 41/43 FPS. The caster's last reducer RTT is 4,686 ms. This does
not qualify the fix in the live world or establish the remaining root cause.
Next capture attack rows at arrival and at PlayerActor reconciliation: Main defers
and coalesces player synchronization, and PlayerActor only starts motions whose
server action end is still in the future. A transition may therefore be lost
before the new catch-up path is reached. Preserve reconnect/life semantics while
investigating that path and the observed delay. Public deployment is unchanged.

## Full-population Dash export: effect failure reproduced — 2026-09-09

Current source `3060fca` was exported for Web with all 20 Yongan map sections;
isolated map dependency audits pass, as do the core 1,555-file/243-UI-image audit.
The matching protocol-29 module is `.local/p6-dash-world-r1/module.wasm`, SHA-256
`0948e5a1be599f41586f97e2cad3ccd57c96c0223c2d4c819b9138ed12063ce2`.
It uses the selected 44-mob registry, original runtime-policy-r2 regeneration
inventory, and first-account-only QA bootstrap authorization. Do not deploy this
local-issuer privileged QA artifact publicly. Database:
`mt2-p2-dash-world-v29-20260909-26d05e87`. The live input-adapter replay passes 33
checks on this world (`input.json`).

The first browser process was interrupted without a report. After verifying the
runner and local service listeners were absent, the preserved `.local/p1/server`
and `.local/p1/auth` services were restored on 13223/13224, with proxy 8186 serving
the new Web export/database. No databases or credentials were reset. Service
handles/logs are recorded in this evidence directory; revalidate liveness before
further operations. Public endpoint was not changed.

Both completed browser attempts (`browser-r2` and `browser-r3`) pass 21 checks
through replicated Dash damage, then **fail effect creation on both clients**.
The new `--original-world` check verifies matching ID/definition subscriptions for
2,837 instances (44 ordinary definitions plus dummy), unique IDs and nine loaded
nearby sections per browser. Reviewed town capture shows terrain textures, the
skill panel, players and dummy. No browser engine errors are reported.

The diagnostic replay reports zero effect spawns on both clients despite matching
package hash `79ae990543872fcb698781883a62bdd12069e090a0d3a3129938c312793c0111`
and two actor bindings each. Failure-time FPS is 35/43, snapshot age 11/19 ms, and
last reducer RTT 4,322/228 ms. These are post-failure samples, not per-cast timing
histories. The actor playback currently suppresses effects before the initial
server-synchronized pose; Dash's source event starts at 48,662 us. That is a
plausible loss path, not yet a proven root cause. Investigate server/update delay
and capture action-arrival timing before changing resync/reconnect semantics.
Full-map effect acceptance and public rollout remain incomplete.

## Live moving-target Dash acceptance — 2026-09-09

The reusable `charge_moving` phase passes **28 live two-account checks** at
`.local/p6-charge-moving-r1/moving.json`, using fresh database
`mt2-p2-charge-moving-v29-20260909-bd886b01`. It stages the real current
`ChargeSkillInput` adapter. The unprivileged second player approaches the original
Brown Bear, provokes it with an ordinary unarmed attack, then retreats. The caster
selects that life and requests Dash while the bear is chasing the other player.

The bear moves more than 0.3 m during approach before strike damage, both clients
receive matching damage and stun, the target life remains unchanged, SP is paid
once, and exactly one successful begin and finish occur. A subsequent observation
finds no delayed damage and the local reservation is cleared. Movement and damage
come from normal server AI/reducers; no test action relocates or damages the bear.

The module in that evidence directory was built from current protocol-29 code,
installed five-skill content, the selected 44-mob registry, and the earlier
authored Brown Bear training placement. Only the first retained QA account has
bootstrap authorization; do not deploy this module publicly. Module SHA-256:
`40384aaa9fd55926519fdc2d3ddc37d6db76e94b5450cfc0f779d60f2f2c954e`.
Touched Python and
GDScript lint/format checks pass. This is live headless acceptance, not rendered
moving-mob or streamed-map/browser qualification. Local served/public exports
remain unchanged; full-map export testing is next.

## Charge terrain-readiness guard — 2026-09-09

Inspection found that automatic Dash movement bypassed Main's loaded-terrain
check used for keyboard movement. Main now supplies the stream readiness callback
to `ChargeSkillInput`. Before activation and during approach, the adapter checks
owner position, target position and a two-metre lookahead. Unavailable terrain
prevents activation, or stops an existing chase and clears its reservation. A
later retry may reuse the remaining server-owned charge. Invalid coordinates
continue through the approach's existing rejection path, never the stream indexer.
This does not provide pathfinding or guarantee every intervening section is loaded.

The new captured-intent adapter fixture passes 13 checks at
`.local/p6-charge-stream-r3/report.json`, including destination updates for a
moving row, stream cancellation without a delayed strike, paid-charge retry,
unloaded lookahead and invalid coordinates. Existing approach (15) and Main
content-gate (42) checks pass in `.local/p6-charge-stream-r2/report.json`.
Touched GDScript formatting/lint and Python lint pass. The first isolated import
was stopped by sandbox socket restrictions; the permitted isolated rerun passed.
NPC approach setup was moved unchanged to its own `attach` helper to keep Main's
composition concise. No protocol or server change was needed.

These are real Godot component checks using controlled rows, not live moving-mob
or exported-map acceptance. Godot MCP is unavailable. Local served and public
exports still predate this guard; full-map/browser qualification remains next.

## Exported Dash hotbar and effects — 2026-09-09

The matching protocol-29 Web training-map export passes its package audit:
1,555 files checked, 243 UI images with verified pixels, and the installed
five-skill catalog hash recorded below. The matching frozen server module is
`.local/p6-dash-web-r1/module.wasm`, SHA-256
`12a680f5932cd349aa4798efb8c51ec7ea5529a61658660e5d71421fce2247b2`.
It uses the selected 44-mob registry and a single retained QA account's privileged
bootstrap identity; **this is not a public-deployment module**.

The live input-adapter replay passes 33 checks on fresh database
`mt2-p2-dash-web-v29-20260909-50f6055c`. The actual Web export then passes
**22 two-browser checks**: existing-account entry, peer rendering, authorized
level setup, learning Dash, dragging its icon to the quickslot, pointer target
selection, hotbar number-key casting, replicated action/damage and new effect
instances on both clients. The learned rank-2 strike reduced the same dummy life
from 29,921 to 29,831 HP in both subscriptions. Both browsers loaded effect hash
`79ae990543872fcb698781883a62bdd12069e090a0d3a3129938c312793c0111`
and reported no engine errors.

Evidence is under `.local/p6-dash-web-r1`: `export.log`, `input.json`, and
`browser/report.json`. Reviewed video contact sheets `browser/contact-0.png` and
`contact-1.png` show the blue/white Dash floor burst appearing and disappearing
in both views. The post-damage still misses that short burst, so spawn counters
alone were not used as visual evidence. This qualifies the male Warrior on the
training map; exact original visual parity, female browser playback, moving
targets and full-map charge behavior remain unqualified. Godot MCP was unavailable;
no connected-editor inspection is claimed.

Local proxy port 8186 now serves this export/database; its previous configuration
is retained in `previous-proxy.json`. Port 8187 and the public endpoint were not
changed. Public protocol 26 remains separate from this local protocol-29 build.

## Installed five-skill original motion effects — 2026-09-09

The effect packager assembled all ten selected skill/appearance links from the
source-resolved inventory, the existing particle/Bash packages, and the previously
converted original Dash mesh/particle package. Selection provenance is in
`.local/p6-dash-effects-r1/selection-receipt.json`; packaging provenance remains
outside runtime in `package/receipt.json`. The new package has 23 runtime resources
and content hash `79ae990543872fcb698781883a62bdd12069e090a0d3a3129938c312793c0111`.

All 153 native equipped actor checks pass at `.local/p6-dash-effects-r1/actors`.
Reviewed captures show the original Dash effect on male and female Warriors.
The generated `package/runtime` directory is now installed at
`client/assets/imported/motion_effects`; the previous runtime is preserved at
`.local/p6-dash-effects-r1/previous-runtime`. No source archives or receipts were
installed in the client. This qualifies packaged ResourceLoader/actor behavior,
not live-world or browser appearance. The local skill/effect hashes now match;
use a newly built matching server for world QA. Public export remains unchanged.

## Live automatic charge-input acceptance — 2026-09-09

The `charge_input` phase stages the real owned client scripts and installed skill
catalog, then instantiates `ChargeSkillInput` on one of two authenticated clients.
All **33 checks pass**: automatic approach is visible to the observer, damage
matches both subscriptions, SP is paid once, charge is consumed, repeated request
calls produce exactly one successful begin and finish, and cancellation of a
later approach produces no strike/damage and clears the reservation.

Evidence: `.local/p6-charge-input-r1/input.json`; fresh database
`mt2-p2-charge-input-v29-20260909-485d10ac`, using the frozen module from
`.local/p6-charge-begin-r1/module.wasm` (hash recorded below). Native Godot runtime
and touched Python/GDScript lint pass. No test-specific movement/damage logic
replaces the normal adapter. This is live headless input-adapter acceptance,
not a rendered Main/hotbar keypress or moving-target test. Original Dash effect
installation and exported gameplay remain next; public deployment is unchanged.

## Installed Dash catalog and original icon — 2026-09-09

The tracked `classic-skills.json` profile now selects Dash alongside the previous
four Warrior skills. `build_skill_catalog.py --offline` regenerates the installed
five-skill catalog at the already server-tested SHA-256
`68011294d772fdbf1722c2162f59141c58c5d88915f29f614d67647643e5ed2a`.
Both installed Warrior actors already contain their converted `skill_5` motions.
The original UI importer rebuilt selected UI assets including `tanhwan_01`.

The native rendered skills-panel suite passes 25 checks at
`.local/p6-dash-installed-r1/ui-r2/report.json`. The reviewed capture shows Dash's
original icon and the scrolled Spirit Strike/Bash rows. Learning, right-click and
real drag-to-hotbar checks pass. The first run exposed positional fixture
assumptions (fourth row was assumed to be Bash); the fixture now locates controls
by vnum and checks all selected rows. Strict Rust lint and touched GDScript lint
pass. Godot MCP was unavailable; this was an isolated rendered fixture.

This installs local capability/icon content, not a public release. The original
Dash effect package and live automatic approach still need installation/acceptance.
Use matching protocol-29/five-skill servers for this client; public protocol-26
exports remain unchanged.

## Main charge-input adapter — 2026-09-09

`ChargeSkillInput` now connects normal HUD skill requests to `ChargeApproach`.
It reads subscribed owner/target/charge rows, sends the explicit begin action,
updates ordinary movement, stops approach movement before one finishing cast,
and reuses an existing paid charge after a cancelled approach. Repeated requests
while a reservation is active do not send another activation. Manual movement,
world clicks, attack input, logout/character changes, connection transitions and
reducer rejection cancel the reservation. Ordinary skills retain direct casting.

The isolated native Godot approach (15) and content-gate (42) checks pass at
`.local/p6-charge-client-r2/integration/report.json`; touched GDScript lint passes.
This verifies parsing/component behavior, **not rendered hotbar or live automatic
approach acceptance**. Installed client content still selects four skills, so
normal Dash input is not yet exposed. Next install/qualify the five-skill candidate
and original presentation, then test automatic approach, cancellation and moving
targets through the normal client. Godot MCP remains unavailable; no editor
inspection is claimed. Public deployment is unchanged.

## Client charge approach state machine — 2026-09-09

Added `ChargeApproach`, a reservation state machine that emits begin, ordinary
move, finish and stop intents from subscribed owner/target/charge state. It
captures exact lives and selected target, waits for charge before moving, limits
movement refresh to 200 ms, and emits completion once. Death/life replacement,
selection loss, charge disappearance and a bounded local timeout cancel the
reservation; no local position or speed is granted.

The isolated native Godot `charge_approach` suite passes 15 transition checks;
evidence: `.local/p6-charge-client-r1/approach/report.json`. Touched GDScript lint
passes. This class is **not yet connected to Main or the hotbar**. Integration must
route manual movement/world exit/rejections to cancellation, stop approach motion
before completion, and avoid restarting a pending reservation on repeated hotbar
input. It also needs actual moving-target/multiplayer and rendered acceptance.
No installed content or public export changed.

## Explicit charge-begin intent and protocol 29 — 2026-09-09

`begin_charge(skill_vnum, expected_revision)` reuses the skill-cast authorization,
learning, resource, cooldown, alive/weapon and ownership gates, then activates
charge without clearing or striking the selected target. Noncharge skills reject.
`cast_skill` still validates the exact selected target life/range for completion.
This matches the original zero-victim approach activation while retaining modern
explicit intents. The Godot facade exposes the reducer; automatic UI approach is
not yet connected.

The extended two-client strike replay passes 43 checks, including a far selected
target preserved through activation, no activation damage, duplicate/noncharge
rejection, subsequent approach and one paid strike during the existing cooldown.
Evidence: `.local/p6-charge-begin-r1/begin.json`; fresh local database
`mt2-p2-charge-begin-v29-20260909-f9778dd2`. Frozen QA module SHA-256:
`a5b4db33eacb587e5ee18838ffdab940c669c534f9267c5f793f18cd2b24b063`.
102 Godot binding files were generated; schema SHA-256:
`d8b354c578fd64b0d0016548100c9862d4899d7831e7b918c335f287bfe86629`.
Strict Rust and touched GDScript lint pass. Public protocol 26/export is unchanged.

## Client charge capability gate — 2026-09-09

`SkillCatalog` now accepts `physical_charge_v1` with bounded typed timing, speed,
push and stun metadata, positive target range, explicit target requirement,
one hit per life and the sword/two-handed content category. Existing splash/area
handlers reject misplaced charge policy. Reload starts by clearing the previous
document/hash so a failed load cannot retain an old capability set.

The isolated native Godot `skill_charge_catalog` suite passes 41 checks covering
typed/JSON policy, missing fields, malformed/nonfinite values, wrong target/weapon/
hit capabilities and ordinary handlers. Evidence:
`.local/p6-charge-client-r1/catalog/report.json`. Touched GDScript/Python lint passes.
Godot MCP was unavailable; no connected editor was inspected. This is a content
gate change, not installed Dash UI or approach automation. The installed four-skill
catalog and public export are unchanged. Next: explicit charge-begin intent that
preserves selected target, then client approach/finish and cooldown presentation.

## Stun and queued reaction interaction — 2026-09-09

The original client routes stun insertion/removal through `SetSleep` → `Stop`,
which clears queued motion. Our adapter reset visible action timing but left
`monster_reaction` alive, allowing a later stand-up transition to restart it.
Stun insertion and matching-life timed expiry now clear the reaction queue while
preserving independent physical force state. The seven focused knockback tests
and strict Rust lint pass.

The new `crush_overlap` replay passes **29 two-client checks**. It casts an
ordinary GREAT-reaction skill during Dash stun, verifies the authored reaction
chain extends beyond the stun deadline, observes reaction cancellation at shared
expiry, checks three seconds without queued reaction restart, and observes AI
recovery. Evidence: `.local/p6-crush-overlap-r1/overlap.json`; fresh local database
`mt2-p2-crush-overlap-v28-20260909-d8b24848`. Frozen QA module SHA-256:
`361a2ad746069a47466bb91c1cfededb41a2a7f66e39a22dfaa78019d2b4dfdb`.
Native Godot parsing and touched Python/GDScript lint pass. This covers reaction
arrival during stun and expiry; the reverse ordering and rendered playback are
not separately qualified. Protocol remains 28; no public deployment changed.

## Live CRUSH adapter and protocol 28 candidate — 2026-09-09

The `crush_death` phase now passes **29 checks** on fresh local database
`mt2-p2-crush-death-v28-20260909-d97e2756`, using the same frozen Brown Bear module
as the expiry replay. Evidence:
`.local/p6-crush-death-r5/crush-death-r2.json`. Normal Dash leaves the bear alive;
normal Sword Spin kills it before the server-authored stun deadline. Both clients
remove the stun and observe a respawned life with original full health and no
restored effect. Setup uses authorized level 99 and rank-20 Sword Spin; source
mob stats and server damage rules are unchanged. Godot parsing and touched
Python/GDScript lint pass. The preceding HTTP 429 pause was respected; its
database was untouched before the accepted retry.

The missing-hit investigation established a fixture facing error: after a single
reposition, Sword Spin's untargeted root motion carried the caster away from the
bear. A two-leg approach establishes forward facing (trace in
`.local/p6-crush-death-r4/crush-death.log`), after which health falls 661→288.
Level-50 finishing damage was insufficient; authorized level-99 setup completes
the kill. No gameplay code was changed to force the result. The retained geometry
trace makes future facing failures diagnosable. Earlier failed evidence follows.

Death-during-stun acceptance initially failed via the new `crush_death` runner phase.
Two fresh databases using the same frozen Brown Bear module reached a shared
stun and accepted the normal Sword Spin follow-up, but neither observed death.
The second run records 661 HP both after Dash and after the follow-up, so this
is a missing-hit investigation, not evidence of insufficient finishing damage
or working death cleanup. Evidence: `.local/p6-crush-death-r2/crush-death.log`;
database `mt2-p2-crush-death-v28-20260909-63c6e624`. The fixture uses authorized
level-50/rank-20 setup, preserves original mob stats, and requires a death
timestamp earlier than the stun deadline before checking removal/respawn.
Both attempts used fresh databases; no gameplay data was reset. Native parsing
and touched lint pass, but **the death replay fails and is not accepted**.
The later geometry trace and accepted retry above resolve this fixture failure.
The previous 27-check expiry replay remains valid for its narrower behavior.

The live ordinary-monster replay now passes **27 checks** using the original
Brown Bear (113, 845 HP), unchanged imported stats, and two authenticated clients.
Both receive the two-metre displacement and matching four-second exact-life stun.
The target survives, remains still with no attack progression or player damage
during the observed stun interval, loses the stun on both subscriptions, and
resumes AI after expiry. Evidence: `.local/p6-crush-live-r1/crush.json`.
Fresh database: `mt2-p2-crush-live-v28-20260909-ab736c84`. Frozen module SHA-256:
`4d382c6a8dfa8df3b5aa1d886ac730487978725a5d18f1f99289ad73df95bb65`.
The imported mob package was rebuilt through `build_mob_catalog.py` into
`.local/p6-crush-r1/mob-catalog`; the generated immunity fields compile in the
selected WASM build. The fixture passes isolated native Godot parsing and
touched Python/GDScript lint. This does not establish kill-during-stun cleanup,
stun-immune targets, overlapping GREAT reactions, Yongan collision or rendered
presentation. Those remain explicit follow-up gates. No public deployment changed.

Dash now invokes the CRUSH policy for surviving ordinary monsters, applies the
collision-limited position change, and stores public `monster_stun` timing tied
to the exact monster life. Stun cancels pending melee hits, gates ordinary AI,
does not refresh an active stun, and clears on expiry/death/changed life. Authored
stationary training targets remain unaffected. Ordinary NOMOVE imports remain
unsupported. The adapter currently supports the selected Dash PC/short-CRUSH
policy; this does not implement every skill's displacement behavior.

The working client expects protocol 28 and subscribes/clears `monster_stun` state.
102 bindings were generated from fresh local database
`mt2-p2-crush-v28-20260909-205f246b`, schema SHA-256
`65ba529d39815d40a49d0201a57854e3d013c80bf1a20a455164e6b5429fae6e`.
Frozen local QA module `.local/p6-crush-r1/module.wasm` SHA-256:
`f7a53c2b6d0f60a4ec2d5240cd8e286a1260407ee98cc9c8d8431ead2aa295a9`.
It contains QA bootstrap authorization; do not deploy it publicly.

Strict Rust lint, touched GDScript lint, the native protocol gate and the 39-check
two-client dummy strike replay pass (`.local/p6-crush-r1/strike.json` and
`protocol-gate`). The dummy replay qualifies matching subscriptions and existing
charge strikes, **not live stun/push**: the dummy intentionally bypasses CRUSH.
The subsequent ordinary-monster evidence above qualifies push, stun and expiry;
death/life cleanup, knockback interaction and rendered presentation remain open.
Source fidelity for concurrent reactions remains open.
Public protocol 26 and its deployment are unchanged.

## CRUSH eligibility policy — 2026-09-09

`crush::displace` now computes a radial endpoint truncated to centimetres and
passes the displacement through the existing authoritative map collision sweep.
Six focused CRUSH tests pass, including a thin-wall obstruction at maximum push
distance, diagonal rounding and invalid coordinates/distances. Strict Rust lint
passes. This is not yet dispatched by live damage. The tested collision fixture
is the training world, not Yongan terrain. Coincident actors currently omit push
because no radial direction is defined; original zero-distance angle behavior
and exact floating-point parity remain unqualified.

The mob registry compiler now emits `MobSpeciesDefinition.immunity_flags` using
the seven-bit original ProtoReader order: STUN, SLOW, FALL, CURSE, POISON, TERROR,
REFLECT. Missing, duplicate or unknown immunity metadata rejects compilation;
no absent-field fallback invents a nonimmune species. Four registry tests cover
individual/combined bits and malformed metadata as well as existing combat
generation. Normal Rust lint passes with the typed field and runtime reserved-bit
validation. Previously generated selected mob registries need regeneration for
this Rust definition change; no selected package or public module was replaced.
The field is not yet an active stun handler. NOMOVE still rejects in the compiler
until ordinary AI movement and displacement both honor it.

Added `crush.rs` with source-backed attacker-dependent push distances, CRUSH_LONG,
NOMOVE exclusion, main-target-only stun, no refresh of an existing stun and the
original 90% stun-immunity roll. Four focused Rust tests and strict Rust lint
pass. This is a pure policy checkpoint, not installed monster displacement or
stun. Source findings and metadata integration gaps are recorded in
`charge-skill-contract.md`. Next: emit mob control flags from imported definitions
and connect exact-life affect state, collision-limited push and AI gating. Public
deployment and database schema are unchanged.

## Charge strike implementation checkpoint — 2026-09-09

The working server now routes a targeted charge cast through exact-life and
strict target-range validation, target-centered splash admission, damage and
charge consumption in the reducer transaction. Immediate use composes activation
and consumption; an existing active charge can finish during its original
cooldown. Payment is stored before kill rewards so a later progression update
cannot overwrite earned XP or a level-up SP refill. The adapter passes the two-client replay described below.

The splash helper uses the original integer approximate-distance expression
`(246 * max(dx, dz) + 102 * min(dx, dz)) >> 8`, with inclusive radius admission.
World coordinates truncate after f32 metre-to-centimetre conversion: `2.10f32`
projects to 209 cm, so a decimal literal cannot stand in for the exact 210-cm
integer edge. Separate integer-edge and float-projection checks make this
explicit. Radius validation accepts bounded whole centimetres despite f32
representation error, including the one-centimetre lower limit.

Ten focused charge geometry/lifecycle tests pass, and `tools/dev.py lint --only
rust` passes formatting and strict all-target/all-feature Clippy. These checks
do not establish transactional damage, subscription or rendered behavior. The
strike currently prioritizes the selected victim and then stable monster IDs;
this deterministic budget policy is not verified original sectree ordering.
CRUSH, stun, two-handed weapon support and normal client approach/presentation
remain outstanding. No public deployment was changed.

The new `charge_strike` retained-account phase passes 39 checks on fresh local
`mt2-p2-charge-strike-v27-20260909-0f61bace`, including immediate and active-charge
strikes, both damage subscriptions, single payment, charge removal, retained
cooldown, out-of-range rejection and stale/current-revision replay rejection
without delayed extra damage. Evidence:
`.local/p6-charge-strike-r1/strike-r4.json`. Frozen QA module SHA-256:
`38216f5cd918d19b9b419541a1299c9ff7403427e7012cefbb94fa60ba0aa6c0`.
It contains local auth/QA bootstrap authorization and must not be deployed publicly.
Two preceding attempts failed on fixture callback parsing before gameplay; named
callbacks pass isolated Godot import/check-only and the actual replay. An auth
429 retry interval was respected. Touched Python/GDScript lint also passes.
This dummy replay does not qualify splash victim ordering, kill/level-up rewards,
CC, target death during approach or rendered/browser behavior. Next is the
reusable original CRUSH/stun policy and client approach/presentation acceptance.

## Persisted charge activation and protocol 27 — 2026-09-09

`charges.rs` persists private ownership/rank/life and a minimal public timing/speed
projection. Untargeted candidate casts validate learning, revision, cooldown,
health, equipped sword and controller lease, then write SP, cooldown and charge
in one transaction. Movement reads the valid owner effect before maintenance
removes expired/disconnected/dead/changed ownership. Expiry advances skill revision
and preserves SP/cooldown; revision exhaustion cannot stall global cleanup.
Godot now expects protocol 27, subscribes to `charge_status` and clears it on exit.

The original five-skill candidate builds as an actual WASM module using the new
`MT2_SKILL_CATALOG` selector, with QA-only authorization for the first retained
fixture account. It was published only to fresh local database
`mt2-p2-charge-v27-20260909-04f474f5`. Artifact:
`.local/p6-charge-r2/module.wasm`, SHA-256
`dba765119df4e3e1d0a34b111f5652b79a6b925eba02cd66263274bca051d913`.
The generator produced/instantiated 99 Godot binding files from its schema, hash
`e6c2eaf9139ab22ba47c90bc14586675ea465303e9a3e2977adfbb74803575c8`.
The schema explicitly marks `active_charge` private and `charge_status` public.

The real two-client charge replay passes 34 checks, including single payment,
matching minimal public projections, observed boosted travel, three-second expiry,
twelve-second cooldown, stale/duplicate/unlearned rejection and disconnect/
reconnect without restoring charge or resources. Evidence:
`.local/p6-charge-r2/charge-r2.json`. The first run's `charge.log` records a fixture
lambda parser failure before gameplay; the bound-callable fix passes actual Godot.
The separate protocol-27 account/movement/attack replay passes 84 checks in
`accounts.json`. Six lifecycle and fifteen movement unit tests, strict Rust lint,
and touched Python/GDScript checks pass.
The isolated Godot protocol gate passes six checks at
`.local/p6-charge-r2/protocol-gate`, accepting 27 and rejecting the old 26 contract.

This does not qualify charge-specific death/switch behavior, private subscription
rejection, precise speed benchmarking, target-strike consumption/damage, CRUSH/stun,
two-handed weapons, normal UI or exported playback. Target strikes explicitly
reject. Installed client skills and the public protocol-26 release are unchanged.
Do not deploy this QA-bootstrap artifact publicly. Next is the target-centered
strike and its transactional consumption/reaction acceptance.

## Movement accounting before attack replacement — 2026-09-09

Accepted action replacement now advances outgoing root motion and ordinary
movement through the reducer timestamp before installing the new attack lock.
The simulation and replacement path share the same movement function. This
prevents the new lock from discarding movement earned since the previous tick,
and provides the boundary needed before consuming a charge. Replacement validates
the living player's controller lease. Queue-only and animation-event sampling
do not use this ordinary movement path.

Fifteen focused movement tests and strict Rust lint pass. A fresh local module
was published only to `mt2-p2-movement-boundary-v26-20260909-8342fbf9`, with no
existing database reset. The original network-only replay passes 74 checks.
The new `tools/test_accounts.py --network-only --movement-attacks` replay passes
84 checks: both authenticated clients enter movement, accept an attack, observe
matching action clocks, recover and move again, alongside rejection/disconnect/
reconnect checks. Evidence is `.local/p6-charge-r1/movement-boundary/`; its frozen
module hash is `c9910d20a817ecef46a9c027e52a52b6e88f9b37a6d88cb4fc7a9facbd6f5ede`.

The replay exercises actual reducer/subscription behavior but does not measure
the exact sub-tick displacement or prove rendered animation/damage fidelity.
Godot MCP is not exposed in this session; the replay uses isolated headless Godot
clients, not the user's editor. Touched GDScript/Python lint passes. Protocol 26
and public deployment are unchanged. Charge persistence, authoritative affect
projection and the target-centered strike remain pending.

## Timed movement allowance — 2026-09-09

Both held and click movement now consume `movement::Travel`, calculated from the
trusted previous/current tick and attack-recovery timestamps. It integrates a
validated timed speed effect only over the overlapping interval. The most recent
100 ms is the maximum movement window, so a stalled tick cannot reuse an older,
expired boost. Direction normalization, target stopping and swept collision still
apply to the resulting allowance. The live simulation calls this path with normal
100 speed points and no effect; charge persistence remains pending.

Fifteen focused Rust movement tests pass, including mixed boosted/normal time,
attack recovery inside an effect, expiry boundaries, split-tick equivalence,
stalled ticks, collision and clock extremes. Strict Rust formatting/Clippy checks
pass for all targets/features. No client, schema, database or public rollout
changed. These are server component checks, not multiplayer charge acceptance.
The persisted adapter must validate owner leases and account for an interval
before discarding its consumed/expired affect; see the charge contract.

## Selected Dash catalog and typed charge policy — 2026-09-09

The selected-skill importer supports `physical_charge_v1`, preserving original
Dash speed/duration, cost, coefficients, both source weapon types, target range,
push and main-target stun policy. Original motion collision events are retained
as inspection data rather than scheduled damage. Rust generation emits a typed
`charge_lifecycle::Definition` and animation with no damage windows; it rejects
ordinary window metadata on charge dispatch, unbounded policies and multi-hit
charge configuration. The current reducer explicitly rejects charge gameplay
until its persistence/immediate strike adapter exists.

An offline five-skill candidate is at `.local/p6-charge-r1/live-candidate/`, hash
`68011294d772fdbf1722c2162f59141c58c5d88915f29f614d67647643e5ed2a`.
Both Dash appearances retain two authored collision events. Rust code generation
passes; this is not a server module build using the candidate. Rebuilding the
normal four-skill profile is byte-identical to the installed catalog. Seven Python
tests, eleven live-catalog compiler tests, seventeen generated-definition tests
(including six charge lifecycle tests), strict Rust lint and touched Python checks
pass. The initial charge test fixture inherited Three-Way Cut's repeat count and
correctly rejected; explicitly selecting one hit per life fixes the fixture.

`tools/build_skill_catalog.py --output` now stages candidates without installing
them. See `docs/development.md` for the selected charge profile contract. No
schema, client assets, database or public release changed. Next is the persisted
charge adapter, authoritative movement interval and target-centered strike.

## Charge lifecycle component — 2026-09-09

`server/src/charge_lifecycle.rs` implements pure bounded activation, consumption
and invalidation transitions. Activation returns SP/state changes together;
consumption preserves cooldown, captures rank and removes the charge. Revision
checks reject stale proposals, and owner matching binds the charge to character,
connection and life. Invalidated/expired records are cleared without refunding
resources or resetting cooldown. Six focused Rust tests pass, including immediate
and delayed strikes, replay rejection, ownership changes and numeric overflow.
Rustfmt and strict Clippy across all targets/features pass.

This component is not yet wired into reducers, persistence, movement or client
subscriptions. These tests do not prove transaction rollback, network security or
playable Dash. The [charge contract](charge-skill-contract.md) records adapter
requirements and remaining two-client acceptance. No protocol or public build
changed.

## Charge approach range and source lifecycle — 2026-09-09

The full-class Rust compiler now applies the original 170 cm melee/charge range
override rather than treating raw table zero as unlimited. This affects Dash,
Ambush and Finger Strike. Raw source fields remain intact; malformed/duplicate
client flags and invalid raw ranges reject even when an override would apply.
Eleven focused compiler/interpreter tests pass. The full 44-skill candidate replay
passes 309 metadata checks including every effective range, 21,120 formula checks,
88 motion-window and 88 geometry checks at
`.local/p6-charge-r1/compiler-target-range/report.json`. Strict Rust lint and
touched Python lint/format checks pass.

The [charge contract](charge-skill-contract.md) records the original two-stage
approach, immediate target-centered strike, CRUSH/stun rules and required lifecycle
acceptance. This changes the implementation path: Dash cannot reuse the current
animation-window `PendingSkill` damage scheduler as-is. Its state, live reducers,
client approach and multiplayer behavior are still pending. No public/schema
change was made.

## Server-owned movement speed calculation — 2026-09-09

Directional and click movement now take a server-owned speed-point total, using
the original PC 0–200 cap and integer duration-percentage calculation. This
provides the movement calculation needed for Dash's +150-point charge without
accepting a speed value from client intents. Normal simulation explicitly uses
100 points; charge activation/expiry/consumption is still pending. No schema,
reducer arguments, bindings or public deployment changed.

Eleven focused Rust movement tests pass, including speed caps, source duration
quantization, boosted diagonal and elapsed-time limits, collision, target stopping
and the movement remainder after an attack. The existing 5 m/s base remains;
these tests do not establish original animation-dependent speeds or multiplayer
charge behavior. Source evidence is the pinned server's `char.cpp::GetLimitPoint`
and `utils.cpp::CalculateDuration` (see the movement contract in `docs/skills.md`).
`python3 tools/dev.py lint --only rust` now passes (rustfmt and strict Clippy,
all targets/features). Its first run exposed a missing `combat_geometry` module
in the generated-definition integration harness. Importing the existing shared
module fixes compilation; all 11 tests in that harness also pass. No generated
files or lint exceptions were changed.

## Dash charge content contract — 2026-09-09

The full-class compiler no longer classifies Dash as ordinary damage. It selects a
`charge` handler from the source-backed skill-5 contract and rejects changed
attack/secondary MOV_SPEED metadata. The Rust generator preserves this as
`SkillHandler::Charge`, alongside the existing damage/buff/healing/periodic types.
No live reducer or protocol/schema changed; this is the candidate content contract
needed before charge-state and movement integration.

Four skill-definition tests pass. A fresh candidate built from the preserved full
44-skill definitions uses the new classifier at `.local/p6-charge-r1/catalog.v2.json`.
The actual Rust compiler/interpreter replay passes 21,120 formula checks, 265
metadata checks (now explicitly including handler mapping), all 88 motion-window
and geometry checks and existing Three-Way Cut replays. Evidence:
`.local/p6-charge-r1/compiler-handlers/report.json` and `compiler-handlers.log`.
Touched Ruff and rustfmt checks pass. The live four-skill catalog and public build
remain unchanged. Next is server-owned charge duration/consumption and movement
validation, then normal client targeting and two-client lifecycle coverage.

## Equipped Dash effect and reusable actor selection — 2026-09-09

The skill-effect actor fixture now validates any selected skill set against installed
motions and both appearances of its class, rejecting duplicates/incomplete pairs
instead of requiring exactly six/eight Warrior rows. Captures use quarter/half/
three-quarter clip times so short clips retain three meaningful captures. Existing
Bash burst capture remains separate.

Dash passes 23 native equipped checks on both Warrior appearances, with six
captures at `.local/p6-all-skill-effects-r1/dash-actors-timed/`. Both frame-12
captures were reviewed: the original effect surrounds the equipped animated actor.
The initial `dash-actors/` run passed its actor assertions but failed the runner's
capture requirement because the 0.8-second clip ended before frame 80. It remains
separate; duration-relative captures fix that fixture limitation. Touched lint passes.

Gameplay remains pending. Source `skill.h::IsChargeSkill` and
`char_skill.cpp::UseSkill` identify Dash as a two-stage charge: a targeted use
establishes charge if needed, computes the target strike and removes the skill
affect. Selected skill-table metadata gives MOV_SPEED +150 for three seconds,
cooldown 12 seconds and cost `60+120*k`. These must be modeled as server-owned
charge state and validated target intents, not an ordinary extra damage skill.
No installed skill catalog, server state or public build changed.

## Full Dash multi-surface runtime — 2026-09-09

The shared mesh renderer now instantiates one converted scene, assigns one material
per ordered surface, and advances all surfaces with one morph-frame clock. Mixed
effects resolve every geometry texture and preserve source element draw priorities.
Single-surface callers retain their existing texture argument and material access.
Dash's 24 elements no longer require separate scene copies.

The first complete-render attempt rejected Dash's alpha-bearing texture. Its
supported SRC_COLOR blend uses RGB independently of texture alpha, so that unused
opacity restriction was removed while keeping opaque-viewport and existing blend
validation. The ramp test now varies alpha across all byte values without changing
the expected RGB result. Diagnostic failure evidence remains separate.

Native Dash qualification passes 61 checks at
`.local/p6-all-skill-effects-r1/dash-render-materials/report.json`: complete particles,
24 ordered surface materials/factors, simulation, natural completion and missing
resource rejection. The frame-14 capture from `dash-render-r2/` was reviewed.
The alpha-varying material regression passes 6,182 checks at `mesh-alpha-colors/`.
The existing complete Bash effect passes 21 checks at `bash-multi-regression/`.
Touched Godot format/parser/lint checks pass. This is isolated native rendering;
Dash gameplay, equipped playback, browser effects and public rollout remain pending.
No installed package or server change is included.

## Packed mesh color factors — 2026-09-09

The mesh renderer now accepts finite RGB factors in [0,1] while retaining its
opaque alpha requirement. It rounds source factors to bytes as the original
D3DXCOLOR conversion does, supplies encoded RGB to the shader, and applies the
factor for modulation/fourfold modulation. Select-argument-2 ignores it, matching
the original texture-stage arguments. Invalid factors reject before construction.

Native skill-mesh QA passes 6,182 checks over 256 RGB entries, two framebuffer
backgrounds, three operations and four factors (white, both Dash gray bytes and
an asymmetric colored factor), plus original geometry/animation checks. An actual
animated mesh uses Dash's 0.686275 factor; its saved capture was reviewed.
Evidence: `.local/p6-all-skill-effects-r1/mesh-factors/report.json`. Godot parser
and touched GDScript lint pass. This is native rendering qualification, not a
browser or complete Dash effect claim. Multi-element scene/material handling is
still needed; installed content and the public build are unchanged.

## Complete Dash multi-element conversion — 2026-09-09

The selected original `gitu.mde` is 23,155 bytes, 24 geometries and six frames,
SHA-256 `8e4ba4132215fa9c0af18de148ad515d47dc6da26b37c725f4873ec96094ddc8`.
The parser geometry bound is now 32, retaining its 8 MiB byte limit, per-geometry
vertex/index/frame limits and complete payload checks. Sixteen mesh-format tests
pass, including a complete 24-element payload, truncated last geometry and
out-of-bound geometry counts. Touched Ruff checks pass.

Pinned Blender conversion of the complete `tanhwan.mse` succeeded at
`.local/p6-all-skill-effects-r1/dash-mixed/`: one GLB containing all 24 geometries,
six source frames, three particle systems and original material recipes. The
existing conversion audit checks positions, UVs, morph frames and timing against
all original geometry. `receipt.json` records sources and audit results. The
initial mesh-only invocation rejected mixed content and remains at `dash-mesh/`;
the successful mixed invocation did not discard particles.

All 59 selected effect definitions now parse in
`.local/p6-all-skill-effects-r1/resource-audit-multi-mesh.json`. This closes the
known parser gaps, not full rendering: Dash requires multi-element scene/material
handling and nonwhite color factors in the runtime, which still rejects it.
Other effects also need conversion and runtime qualification; public unchanged.

## Stationary movement-facing mesh case — 2026-09-09

The source audit found that Shaman `yongpa_a` uses MOVE billboard type 3, not
camera-facing billboarding, with one fixed position key. The original renderer's
successive position samples coincide, so it retains identity orientation. The
MSE parser now preserves type 3; the Godot renderer accepts only its singleton
DIRECT track case. Multiple-key movement tracks still reject rather than rendering
with an invented orientation. Other material restrictions remain unchanged.

Fifteen Python mesh tests pass. Native skill-mesh QA passes 1,571 checks,
including stationary acceptance, multiple-key rejection, actual stationary-MOVE
mesh construction and the existing color/animation checks. Evidence:
`.local/p6-all-skill-effects-r1/stationary-mesh-billboard/report.json`.
The resource audit now parses 58/59 selected definitions at
`resource-audit-billboard.json`. Warrior `tanhwan`'s 24 mesh elements remain the
last known parser gap. The complete Shaman effect's colored materials and asset
conversion are still unqualified; this result does not make that ability playable.
Public and installed assets unchanged. Touched lint passes.

## Selected mesh color operations — 2026-09-09

The MSE parser now preserves ColorOperationType 3/4/6. The source-color Godot mesh
renderer accepts these under its existing white-factor, opaque-texture and blend
restrictions; operation 6 clamps the fourfold texture product before source-color
blending. Other factor/alpha/material combinations are still rejected. Source
argument order and Microsoft operation definitions are recorded in third-party notes.

Fourteen Python mesh-format tests pass. The native `skill_mesh` fixture passes
1,569 checks with all 256 RGB ramp entries for each operation against two measured
framebuffer backgrounds, plus existing Bash mesh animation/geometry checks.
Evidence: `.local/p6-all-skill-effects-r1/mesh-color-modes/report.json`; the retained
Bash mesh capture was reviewed. This is native Compatibility evidence, not browser
qualification of newly imported full effects. Godot MCP was unavailable.

The updated offline audit parses 57/59 selected effect definitions. Sura
`muyeong_make` and `yonggwonpa` now pass syntax validation; their resource conversion
and complete rendering remain pending. The remaining parser gaps are Shaman mesh
BillboardType 3 and Warrior `tanhwan`'s 24 mesh elements. Report:
`.local/p6-all-skill-effects-r1/resource-audit-color-modes.json`. Public unchanged.

## Signed scalar particle times — 2026-09-09

Original `EffectLib/Type.cpp` retains signed scalar times and `Type.h` samples
between their neighbors. The Python parser and Godot emitter validator now accept
bounded negative scalar keys, preserving cross-zero interpolation; scalar values,
ordering, effect delays and position curves keep their existing validation.
No time is clamped to zero. The existing sampler already performs the required
interpolation, so its calculation did not change.

Seven Python particle tests and 88 headless Godot emission checks pass, including
negative-key interpolation, singleton behavior, descending/out-of-range rejection
and actual emission. Evidence:
`.local/p6-all-skill-effects-r1/negative-key-emission/`. The updated offline resource
audit accepts 55 of 59 effects: Ninja `gyeonggong_start` and Sura
`pabeopsul_making` now parse. Sura `yonggwonpa` advances past its negative key to
an unsupported mesh ColorOperationType 6. Mesh BillboardType 3, ColorOperationType
3 and the 24-element `tanhwan` mesh also remain outstanding. Report:
`resource-audit-negative-keys.json` in the same evidence root.

This changes parser/runtime validation, not installed assets or public builds.
Rendering of the newly accepted effects remains unqualified; headless curve
checks do not establish visual fidelity.

## All-class effect resource coverage — 2026-09-09

`audit_skill_effect_resources.py` checks every distinct MSE referenced by the
resolved class-skill inventory, recording source hashes, layer kinds, references
and exact parser rejections. Selected definition files were fetched from the pinned
archive; textures/models were not fetched. Final offline evidence:
`.local/p6-all-skill-effects-r1/resource-audit-final.json`.

Of 59 MSEs, 53 parse (50 particle-only, three mixed); six remain unsupported:
Ninja `gyeonggong_start`, Sura `pabeopsul_making` and `yonggwonpa` contain a
-0.005714 particle time; Shaman `yongpa_a` uses mesh BillboardType 3; Sura
`muyeong_make` uses mesh ColorOperationType 3; Warrior `tanhwan` declares 24 mesh
elements. Numeric particle errors now include the actual value and bounds.
Parser acceptance is not conversion/runtime qualification. These are the next
explicit adapter gaps; no layers are silently removed.

Two focused resource-audit tests and six existing particle parser tests pass;
Ruff checks pass. The earlier offline-missing and fetched reports are preserved.
No gameplay, installed runtime package or public deployment changed.

## All-class effect attachment resolution — 2026-09-09

`resolve_skill_effects.py` joins the discovered events to pinned original GR2
skeletons and installed hash-verified GLB skin joints. Decorative model node names
cannot satisfy a bone reference. Missing converted bones reject rather than hiding
conversion loss; source-missing bones retain the original follow/capture behavior.
The output keeps source/model/catalog hashes and all other metadata for later work.

The actual offline run resolved all 136 events across eight actors, with no lost
referenced bones and no disabled events. Six original-missing `Bip01 Footsteps`
references use root following: Warrior female skills 2/17/18, Ninja male 48, and
Shaman male 96/109. Evidence: `.local/p6-all-skill-effects-r1/resolved.json`.
Two focused tests cover GLB joint-only matching, invalid/duplicate joints,
source fallback versus conversion loss, copy preservation and rejected-event
refusal. Ruff passes. This verifies attachment names and fallback selection,
not animated transform parity for every class or rendered effect resources.
No installed content, server behavior or public build changed.

## All-class motion-effect discovery — 2026-09-09

`tools/discover_skill_effects.py` now batches effect extraction across the pinned
skill inventory and character import profile. It resolves race/MSA paths through
original archive precedence, records input/source hashes and groups shared MSE
references. Unsupported type-1 records are retained with failure reasons; other
metadata is preserved. It does not install content, resolve bones, fetch MSE
resources or claim unsupported mechanics work.

Actual offline run: `.local/p6-all-skill-effects-r1/inventory.json`, all 44 skills
and 88 appearance motions, 136 extracted events, 59 distinct MSE references,
zero rejected type-1 events and 54 remaining metadata records. The latter include
28 type-6, eight type-2, four type-10, two each type-7/8/9, and eight non-event
records. Three focused tests pass using the real MSA parser: supported extraction,
lossless rejection/other-event retention and source-pin rejection. Touched Ruff
checks pass. Existing installed content and public deployment are unchanged.

Next: resolve these events against original/converted skeletons and batch their
resource requirements, alongside implementing the remaining class-specific
combat/status contracts. An extracted event is not a playable ability.

## Original Warrior effects deployed publicly — 2026-09-09

Release `20260908T233819834672Z` serves the full-map skill-effect build at
https://kcanakdag.com:8443/. Actual Web and Linux exports passed package audits;
deployment verified the served manifest. Protocol 26 and database
`mt2-public-skills-v26-20260908` remain unchanged. The frozen module SHA-256 is
`750f0c44bb4784dcc6d53eb35387ff07b8efe0932fc0907bc5bd12676f00279e`, identical to
the previous public module. Publication used no reset and retained accounts/keys.

Public hardware Chrome/Linux qualification passes all 76 checks: matching
2,860-mob/44-species subscriptions, mutual rendered players, skill-panel input,
movement and rejection, disconnect removal, character switching with saved
position, reconnect, reload and logout/login. Browser engine errors are empty.
The public world capture was reviewed. Evidence and frozen builds:
`.local/public-world-effects-r1/acceptance.json`, `browser-qa/report.json`,
`deploy.log`, `web/` and `linux/`. The one-mob census change from the earlier
release is live regeneration; both clients agree on the current population.

Skill casting/effect appearance was qualified separately on the local two-Chrome
fixture below. Public QA does not claim public skill-casting coverage or original
pixel parity. All four Warrior effects are now deployed; other classes' skill
systems, missing scenery/maps, original UI fidelity and remaining full-rebuild
milestones are still outstanding.

## Exported two-client skill effects — 2026-09-09

The web export at `.local/p6-world-effects-r1/web` completed its existing actor,
NPC, mob and target-effect pack audits. The package inventory includes the motion
effect catalog/resource remaps. The local QA proxy on 8187 now serves this build,
using the existing `mt2-p2-skill-reaction-16-v26-r1-20260908` database and unchanged
auth routing. No database was reset and the public endpoint is unchanged.

Two independent hardware Chrome clients passed 34 focused checks at
`.local/p6-world-effects-r1/browser/report.json`: Spirit Strike and Bash cooldowns,
new action sequences, matching dummy damage and effect creation on both clients,
with no browser engine errors. Read-only world snapshots now expose package hash,
cumulative spawn count, active instances, bindings and renderer errors.

Post-cast screenshots missed Bash's brief burst. A video replay exposed an
unnecessary QA scroll reset that reused stale slot coordinates; the helper now
keeps an already-visible control in place. The failed recording remains at
`browser-video/`. The focused corrected Bash replay passed 22 checks at
`browser-video-r2/report.json`; both browser recordings and extracted burst grids
are retained. The caster grid visibly shows the burst extending through/beyond the
dummy and then fading. This is exported rendering evidence, not an original-client
pixel comparison. Public full-map export/deployment remains next.

## World skill-effect wiring and lifecycle — 2026-09-09

Main now prepares the installed motion-effect package against character/skill hashes
before entering the world, advances its effects while connected, and clears them
on connection/lobby transitions. PlayerActor announces each created presentation
before applying its first subscribed action; WorldSkillEffects attaches the package
and binds its effect signals. ActorPresentation joins effects during normal
`play_action` playback without changing immutable motion definitions. A new prepare
rebinds any surviving presentation after cleanup. No server authority changed.

The verified 18-resource package is installed at
`client/assets/imported/motion_effects/`; source receipts remain outside the client.
Native normal-playback checks passed 115 assertions at
`.local/p6-skill-effects-r19/world-playback/report.json`; the final package prepare,
cleanup and surviving-presentation rebind run passed 123 at
`.local/p6-skill-effects-r20/world-lifecycle/report.json`, with 26 captures.
Full-project Godot headless import completed with no reported script errors at
`.local/p6-skill-effects-r19/import.log`. Touched format/lint checks pass.
The identical progression/skills HUD callbacks were consolidated, and projectile
node creation moved into the scene while adding the skill-effect world node.

These checks exercise native actors and the world controller, not actual network
subscriptions. Export validation, two-client browser casting and public deployment
are still pending; the public endpoint remains unchanged. Connected-editor MCP
inspection remains unavailable.

## Packaged Godot motion-effect loader — 2026-09-09

The Godot loader checks the installed character/skill hashes, resolves only hashed
PNG/GLB resource paths through ResourceLoader, and rejects missing or ambiguous
effect references. Failed loads expose no usable document/resources. Motion events
are joined onto private presentation copies; the frozen actor catalog and packaged
event arrays remain unchanged.

The actor runner now accepts `--effect-package` and stages only catalog-declared,
hash-verified runtime resources and import settings. The latest native run passes
99 checks across four skills and both Warrior appearances, with 26 captures:
`.local/p6-skill-effects-r18/packaged-actors/report.json`. This includes mismatched
catalog rejection, immutable/copy-safe joins and equipped rendering through the
packaged resource loader. The preceding loader-only run passed 83 checks at
`.local/p6-skill-effects-r17/packaged-actors/report.json`. Touched lint passes.

This remains isolated native evidence. Main does not yet load/bind this package;
normal multiplayer casts, browser exports and public deployment remain pending.
Godot MCP was unavailable in this session; no connected-editor inspection is claimed.

## Portable motion-effect runtime package — 2026-09-09

`build_motion_effect_catalog.py` packages particle and mixed resources, rewrites
mesh/texture paths to hashed runtime assets, and validates complete coverage of
every currently enabled skill appearance against installed character motions.
Duplicate/missing links, unresolved effects, bad event times/offsets and asset hash
mismatches reject. The catalog records character/skill catalog hashes and its own
content hash; the provenance receipt is outside the `runtime/` directory.

The two converters produced different PNG encodings for an identical referenced
texture. Canonical PNG encoding now deduplicates equal decoded RGBA pixels while
retaining input-byte hashes and rejecting different content. Three focused Python
tests cover complete/copy-safe links, rejection paths, canonical deduplication and
changed asset bytes. Touched Ruff/format checks pass.

Actual package: `.local/p6-skill-effects-r16/package-r2/runtime`, eight motion links,
18 resources, hash `9302c44b19bf51c2d44703c24a6d70a6daeebde7cc00f77961176482e07abd5c`.
The failed pre-canonicalization candidate remains separate. No package is installed
yet: Godot resource loading, actor binding in Main, exported two-client replay and
public deployment remain next. This is packaging evidence, not runtime acceptance.

## All four equipped Warrior effects through shared manager — 2026-09-09

`WorldMotionEffects.configure` accepts separate mixed definitions and loaded mesh
scenes alongside particle-only recipes/textures. Source-effect paths choose the
renderer; duplicate paths reject. Both types share event dispatch, transform updates,
actor-exit behavior and completion cleanup. Existing particle-only callers retain
their default signature. The particle gallery stages the additional dependencies.

The equipped actor runner accepts `--mixed-effect-catalog`, hash-checks and stages
its assets, and exercises eight complete skill/sex combinations. The final run
passes 73 native checks with all 16 source events emitted once, bounded original
models/swords and no renderer errors. Evidence:
`.local/p6-skill-effects-r15/actors-burst/report.json`, 26 captures and `../links.json`.
Dedicated frame-65 captures show the full Bash burst extending ahead of both
Warrior variants; male bone-following and original female root fallback both work.
Earlier fixed snapshots fell after Bash's short visible burst and did not prove its
appearance; the targeted captures correct that evidence gap. Touched lint passes.

This is native staged content with original animations and real effect-manager
instances. Main still lacks installed effect package loading/binding. Browser,
two-client synchronization and public effect qualification remain pending; original
pixel/color parity has not been established. No server/database/deployment changed.

## Complete mixed Bash renderer and original angular orbit — 2026-09-09

`mixed_effect.gd` creates all particle and mesh layers, advances their common clock,
and completes only when every layer finishes. Missing resources or rejected layers
reject the whole effect; partial children are cleaned up. Material priorities
preserve the original render grouping (particle systems first, mesh layers second),
which differs from interleaved textual MSE declarations.

The first combined run rejected three particle systems with nonzero angular orbit.
The shared simulation now rotates existing particles clockwise around their spawn
center after translation. Attached particles use the source horizontal plane;
detached particles use the current emitter's transformed source Z axis. The source
angle is applied per update, without delta scaling. Two axis-direction checks plus
existing motion regression pass (104 checks). Render/update cadence parity with
the original client remains unqualified.

The complete Bash gallery passes 12 checks with all 12 systems/three meshes present,
visible particle emission, natural combined completion and rejection of missing
mesh resources. Evidence: `.local/p6-skill-effects-r14/mixed-r2/report.json` and
captures; `motion/report.json` contains motion regression. The combined three-column
burst was visually reviewed (the tallest flare clips the gallery's upper frame).
The failed pre-orbit run is retained. Touched Python/GDScript lint passes.

This remains an isolated native Compatibility effect, not an equipped Bash or
networked world test. World manager support for mixed resources, package installation,
all-four-skill equipped replay and two-browser/public qualification remain next.

## Bash finite mesh rendering and additive material — 2026-09-09

The shared mesh renderer now accepts the selected source-color/additive (3/2)
recipe alongside opaque arrow (3/8), using the shared imported frame interval,
start delay and finite/infinite loop clock. Completed effects hide. The selected
materials remain white-modulated, single-texture and opaque-destination only;
unsupported color/texture animation modes still reject. Source visibility/alpha
does not multiply RGB for these source-color blend factors.

Native Bash mesh QA passes 545 checks: a 256-byte RGB ramp on two measured
backgrounds agrees with the independent clamped `source² + destination` reference
(maximum error 1.118 byte values), all 31 original frames appear on each of three
layers, and finite completion hides each mesh. Captured frame 10 of the first mesh
was visually reviewed. Evidence: `.local/p6-skill-effects-r13/bash-render-r2/report.json`
and captures. The initial run failed a Godot external constant lookup; the final
shader variant uses a static method. Arrow native regression passes 527 checks at
`r13/arrow-regression/report.json`. Touched lint/format checks pass.

This qualifies individual mesh layers in Linux Compatibility/llvmpipe, not the
complete mixed Bash effect or original-client/browser pixel parity. Combining all
particle/mesh layers, equipped Bash playback, world packaging and two-client
exported verification remain next. No deployment or installed content changed.

## Shared original mesh frame clock — 2026-09-09

`mesh_frame_clock.gd` implements the original effect-frame deadlines, finite/infinite
loop counts, frame-zero reset at completion and 20-advance catch-up bound with
retained backlog. Delayed activation displays frame zero without consuming the
activation update's overshoot or advancing local time. The clock is rendering-free;
its snapshot exposes frame, visibility, completion and local time.

The existing arrow mesh renderer now uses this shared clock, preserving its infinite
50 FPS behavior. The isolated clock runner passes 31 checks, and native arrow
render/material regression passes 527 checks. Evidence:
`.local/p6-skill-effects-r12/clock/report.json` and `arrow-render/report.json`.
Touched Python/GDScript lint and format checks pass. Bash can use the same finite
clock with its imported 7 ms interval and staggered layer delays; its mesh material
and mixed-renderer integration remain next. No installed content or public build
changed, and no original-client pixel-parity claim is made.

## Complete Bash effect conversion candidate — 2026-09-09

`import_projectile_mesh.py --mixed` now converts the full parsed effect: mesh GLBs,
particle recipes/textures and original layer ordering. Bash's candidate contains
three 31-frame meshes, 12 particle systems and four decoded PNGs (three particle
textures and one mesh texture). All geometry, UV, morph-weight and boundary audits
pass. All 96 exported frame timestamps were checked against the original 0.007 s
spacing. Evidence: `.local/p6-skill-effects-r11/bash-r2/receipt.json`,
`mesh-effects.v1.json`, and `timeline-check.json`.

The first conversion failed its animation audit: the pinned glTF exporter
multiplies `fps_base` when deriving timestamps. The converter now represents delays
as bounded rational intervals, with integer key spacing and `fps_base=1`. Bash uses
seven timeline steps at 1000 FPS and ends at 0.217 seconds; the existing arrow uses
one step at 50 FPS. The offline arrow reconversion passes unchanged geometry/timing
contracts in `r11/arrow-regression/receipt.json`. Touched Python lint/format pass.
The failed candidate is retained separately; no imported source or vendor code changed.

This is complete conversion, not complete rendering. Bash's source-color/additive
mesh blend, finite 7 ms frame playback and mixed renderer integration are next.
No installed gameplay content, server or public release changed.

## Complete Bash effect parsing and quadratic position curves — 2026-09-09

`mixed_effects.parse_mixed_effect` validates both particle and mesh subtrees and
retains every layer in source order. Unknown layer kinds or malformed content in
either half reject the whole effect. Existing particle-only/mesh-only readers keep
their strict entry points and share subtree validation with the mixed adapter.
The original Bash script now parses as 12 particle systems plus three mesh layers;
no layer is dropped. Candidate metadata: `.local/p6-skill-effects-r10/bash-mixed.json`.

The script exposed original `MOVING_TYPE_BEZIER_CURVE` position records. The importer
now preserves optional relative control points and Godot evaluates the original
quadratic segments, including direct segments in the same track. Single-key curves
remain constant as in the original client. Existing direct-only recipe output stays
unchanged. Six particle, 13 mesh and two mixed-reader Python tests pass; the Godot
motion scenario passes 102 checks, including control offsets, endpoints, following
direct segments, clamping and singleton behavior. Evidence: `r10/motion/report.json`.
Touched Python/GDScript lint and formatting pass.

The selected pinned `gyeoksantau.mde` parses with the existing binary reader:
31 frames, one 24-vertex geometry, referenced JPEG texture. Its SHA/source details
are in `r10/mesh-inspection.json`. The mesh script uses 0.007-second frames and
source-color/additive blending, which still need converter/runtime support; this is
not a converted or rendered complete Bash effect. No runtime content was installed.

## Equipped original Warrior effect playback gallery — 2026-09-09

The new `test_actors.py --scenario skill_effects` stages explicit particle resources
and motion links without modifying installed catalogs. The actual male/female
Warrior models, original swords and original Three-Way Cut/Sword Spin/Spirit Strike
clips drive event dispatch and attached renderers. All 55 checks pass, with 18
captures, source events emitted once, bounded deformation/equipment and no attachment
simulation errors. Evidence: `.local/p6-skill-effects-r9/actors-r2/report.json` and
captures; input links are `../links.json`. The first fixture run used float-formatted
JSON skill IDs in action names; the corrected fixture explicitly casts IDs to ints.

Reviewed captures show the male Sword Spin effect aligned along the equipped blade
and the female Spirit Strike charge at the body. This is Linux native Compatibility
rendering, not pixel comparison against the original client or browser multiplayer.
The fixture intentionally uses local PNG decoding; shipping resource loading is still
required. No connected editor was inspected. Touched Python/GDScript lint passes.

Bash is excluded as a whole until its mixed particle/mesh effect is converted.
No partial Bash effect was installed, and installed/live catalogs remain unchanged.
Next: complete mixed effects and package/link these resources for actual world loading,
then run two-client/exported acceptance and update the public development build.

## Actor-triggered effect renderer lifecycle — 2026-09-09

`world_motion_effects.gd` binds actor effect signals to the existing particle
renderer using injected trusted recipes/textures and explicit source yaw. Following
instances refresh root/bone transforms; captured instances retain their spawn
transform. Actor tree exit removes following effects and bindings while captured
effects continue to natural completion, matching the original untracked capture
branches. Completed instances release their scene nodes. Unknown resources, invalid
placements and renderer failures are reported; repeated actor binding rejects.
The world must supply the simulation/render clock; Main is not wired yet.

The isolated Warrior gallery/lifecycle test passes 67 checks, including changing
bone poses, owner movement, capture stability, actor removal and finite drain.
Evidence: `.local/p6-skill-effects-r8/render-exit/report.json`. The earlier root-only
run passed 64 checks; a later test inspected queued removal before actual tree exit.
The final test waits for `tree_exited`; no production workaround was added.
Existing projectile gallery/lifecycle replay passed 83 checks at
`render-projectiles/report.json`. Touched Python/GDScript lint and format pass.

The lifecycle fixture uses real renderer instances and synthetic actor/skeleton
poses. It does not yet demonstrate effects on exported Warrior animations or in two
networked clients. Complete Bash mesh resources, installed motion/resource links,
Main wiring and public qualification remain unfinished. No deployment changed.

## Effect attachment transform conventions — 2026-09-09

`ActorPresentation.motion_effect_transform` resolves explicit root/bone modes into
world transforms. The caller supplies the catalog's source-to-actor yaw. Source
metre offsets rotate with the actor source frame, not the animated bone; bone
orientation receives the inverse source-to-Godot axis mapping on the right
(a local X quarter-turn). Missing resolved bones and nonfinite inputs reject.
The method does not choose a fallback at runtime; the source-aware linker does.

The original `GetBoneMatrix` uses Granny world pose, distinct from the skinning
composite. An independent rest-frame comparison of pinned GR2 model placement and
bone hierarchy with installed GLB node transforms found position errors below
0.000001 m on both Warrior hand/spine attachments and male Footsteps. All five
basis comparisons yield the same local-axis correction within export roundoff.
Evidence: `.local/p6-skill-effects-r7/inspect_frames.py` and `frame-comparison.txt`.
This comparison used system NumPy for local inspection, adding no runtime dependency.

The actual Godot playback fixture now passes 24 checks including root yaw, actor-space
bone offset, converted bone basis and missing/nonfinite rejection:
`.local/p6-skill-effects-r7/playback-final/report.json`. Touched GDScript lint passes.
This establishes rest-frame conventions and synthetic animated-pose resolution,
not visual animated attachment parity. Renderer lifecycle, complete Bash effects,
installed catalog links and two-client rendered acceptance remain unfinished.
No imported models, server/database or public deployment changed.

## Shared actor motion-effect event playback — 2026-09-09

`ActorPresentation` now dispatches optional typed `effects` from the actual
AnimationPlayer source clock through `motion_effect_requested`. Event identities
are consumed once per action/sequence; forced resync preserves consumption, a new
action/reset clears it, and late entry suppresses past events while retaining an
exact-boundary event. Completion drains events missed by a long frame, disabled
source attachments do not dispatch, and signal payloads are copied. Existing
projectile dispatch and catalogs without effects remain supported.

The reusable isolated `tools/test_motion_effect_playback.py` runner passes 19
headless Godot checks using real AnimationPlayer advancement, seek, speed scaling,
finish signals, freeze/reset and projectile regression. Evidence:
`.local/p6-skill-effects-r6/playback-regression/report.json`. Touched Python and
GDScript lint/format checks pass. The first manual test had userdata-directory
errors; the accepted runner isolates userdata and rejects engine errors.

This is event-clock integration, not visible skill effect integration. Installed
catalogs still contain no effect records. Resource linking, transforms, renderer
lifecycle, Bash's complete mesh effects and rendered two-client QA remain required.
No live content/server/public release changed.

## Original female Warrior missing-bone behavior — 2026-09-09

The effect skeleton audit found `Bip01 Footsteps` absent from the female converted
model. Reading the pinned original GR2 with the existing Carbon/legacy-header
adapter confirms it is also absent from the original 84-bone skeleton. The male
model contains the bone. Source `ActorInstanceAttach.cpp:AttachEffectByID` falls
back to root for missing follow-bone attachments; the capture-bone branch in
`ActorInstanceMotionEvent.cpp` skips the effect instead.

`motion_effects.resolve_attachment` now encodes those distinct source behaviors.
It rejects a bone lost during conversion or added only in conversion, so legacy
fallback cannot hide conversion damage. Five focused Python tests pass, including
follow/capture fallback and conversion-loss rejection. All 16 selected events
resolve against original GR2 and converted GLB skeletons: two root fallbacks
(female Sword Spin and Bash), zero lost effect bones. Source/model hashes and
resolved records: `.local/p6-skill-effects-r5/attachments.json`. Touched lint passes.
This is offline attachment qualification; animated runtime dispatch and complete
Bash resources remain unfinished. No models, live catalogs or deployment changed.

## Typed original motion-effect extraction — 2026-09-09

`tools/motion_effects.py` adds a reusable, explicit local-MSA extraction command.
It adapts original effect type 1 into source identity/time, normalized MSE reference,
metre offset, and root/bone follow or capture semantics. IndependentFlag overrides
attachment; notably AttachingEnable=0 follows the actor root in the original client.
Required fields, flag values, finite bounded offsets and timestamp consistency are
validated. Unknown fields reject; unrelated unsupported metadata remains reported.
No live catalog/actor dispatch was changed and no events were silently installed.

Three focused unit tests cover all eight flag combinations, source preservation,
coordinate conversion and malformed metadata rejection. Actual pinned source extraction
and CLI replay match 16 events from eight motions (four skills, both Warrior sexes),
referencing six MSE effects. The male/female effect declarations match. Evidence:
`.local/p6-skill-effects-r4/motion-effects.json` and `compiled.json`. Python lint and
format checks pass for both new files. Next: link these event records to converted
skeletons and complete effect resources, then exercise timed runtime attachment.

## Warrior ground-plane particle rendering — 2026-09-09

The shared renderer now handles original billboard type 3 (ground-plane quads)
and color operation 5 (clamped doubled RGB modulation; alpha unchanged). Ground
rotation captures the emitter heading at birth for attached and detached particles;
subsequent emitter rotation does not rewrite existing particle headings. Stretch
continues to take precedence over billboard orientation, as in the pinned client.
Unsupported other render modes still reject configuration.

All five particle-only Warrior candidates now pass the isolated native gallery:
51 checks in `.local/p6-skill-effects-r3/render-final/report.json`. Geometry checks
cover source-axis corners, camera independence, quarter turns and attached centers.
97 motion checks cover birth heading, retained heading and later births; the existing
projectile gallery passes 67 checks. Reports/captures are under the same evidence
root. Sword Spin's ground swirl was visually reviewed. Touched GDScript lint and
format checks pass; Godot 4.7.2 parsed and ran the components. Rendering used Linux
Xvfb/llvmpipe, not Chrome or the connected editor. No pixel comparison with an
original-client capture was performed.

These remain isolated effects, not installed skill presentation. Motion-event
attachment dispatch, Bash's mixed mesh/particle effect and live/browser qualification
remain next. No server, database or public build changed.

## Warrior particle candidates and duplicate scalar keys — 2026-09-09

The scalar MSE importer and Godot emitter now accept nondecreasing timestamps,
retaining descending/nonfinite/bounds rejection. Source-backed sampling preserves
first-key selection at an exact duplicate timestamp and interpolation from the last
duplicate afterward. This unblocks Sword Spin's original lifetime curve without
rewriting its keys. Five Python tests and 108 Godot regression checks pass, including
discontinuities at the beginning, middle and end and the existing projectile fixture.
The emission runner accepts `--expected-systems` for other selected catalogs.

Five original Warrior MSE effects convert to 13 systems and 12 textures; decoded
RGBA pixels are verified. All 81 selected Godot emission checks pass. Evidence is
under `.local/p6-skill-effects-r2/`: `particles/receipt.json`,
`emission-skills/report.json`, and `emission-regression-final/report.json`.
The rendered gallery fails 9 of 46 checks: three recipes are rejected because
billboard mode 3 and color operation 5 are unsupported. Its failed `render/run.log`
is retained. This is conversion/emission evidence, not rendered parity or live
integration. Bash's mixed particle/mesh MSE remains outside this candidate catalog.
Next: source-backed billboard/color rendering, mixed mesh effects, and motion-event
attachment dispatch. No server, installed content or public release was changed.

Touched Python and GDScript lint/format checks pass. Repository Python lint finds
pre-existing format differences in `tests/test_mob_server_registry.py` and
`tools/build_npc_catalog.py`; they remain outside this change. Connected editor MCP
inspection was unavailable; the gallery used isolated native Godot/Xvfb.

## Expanded world actors deployed without a world reset — 2026-09-09

Public release `20260908T220207351930Z` deploys the corrected world actor loading
and scroll-aware skill inspection. Existing protocol-26 database
`mt2-public-skills-v26-20260908`, character roster, auth accounts and issuer keys
are preserved. The public module is byte-identical to the preceding release
(SHA-256 `750f0c44bb4784dcc6d53eb35387ff07b8efe0932fc0907bc5bd12676f00279e`).
Both public exports pass package audits and deployment verified its served manifest.

Public Chrome/Linux QA passes 76 checks: account entry, matching 2,859-mob/
44-species subscriptions, mutual rendering, skill-panel input, movement, rejected
invalid actions, character switching, saved position, reconnect, reload and
logout/login. Browser engine errors are empty. Evidence:
`.local/public-skill-actors-r1/acceptance.json` and `browser-qa/report.json`.
The two-Chrome skill-casting qualification below is local evidence, separate from
this public account/world replay. Exact original skill effects, specialization
selection and broader combat balance remain incomplete.

## Exported skill replay exposed and fixed world actor selection — 2026-09-09

Added `tools/test_browser_skills.py`, a focused two-Chrome replay using existing
private development accounts. Actual panel clicks spend skill points, mouse drags
bind quickslots, pointer input selects the dummy and number keys cast. Authorized
level setup uses the existing chat command. The final replay requires fresh attack
sequences on both clients, subscribed cooldown, matching damage and no browser
engine errors. No privileged probe command or direct database mutation was added.

The first export demonstrated learning/binding and replicated damage, but failed
on missing male Warrior skill motions in both clients. `Main` loaded the legacy
base Warrior while intro/equipped QA loaded the expanded character package.
Both world catalog load sites now explicitly choose the installed expanded models.
The corrected export passes 32 checks with two hardware-rendered Chrome clients:
Spirit Strike rank 3 advances sequence 3→4 on both, health 29783→29656; Bash rank 2
advances 4→5 on both, health 29656→29536. Target life remains 0. Browser engine
errors are empty, and both cast captures were reviewed with attached swords.
The initial failed run observed first learning of Bash; the final accepted run
upgraded the preserved skills instead of resetting the database.

Evidence: `.local/p6-browser-skills-r2/acceptance.json` and `replay/report.json`;
failed predecessor retained in `.local/p6-browser-skills-r1/replay/`. Actual Web
export/package audits and targeted Python/GDScript lint pass. No claim of original
skill effect/physics parity or native/exported all-rank balance. Public Web/Linux
exports for the existing protocol-26 world are being prepared in
`.local/public-skill-actors-r1/`; public rollout and endpoint qualification are recorded above.

## Scroll-aware skill control inspection and real mouse QA — 2026-09-08

Added read-only per-vnum slot/learn-button centers and visibility to the existing
skill-panel snapshot, plus scroll position/center. Browser automation can discover
controls without hardcoding row positions; no privileged action or gameplay rule
changed. Native UI acceptance now passes 24 checks: original icons, projected ranks
and cooldowns, actual learn-button input, complete wheel events, scrolled Bash
right-click intent and actual drag/drop into the second quickslot. The resulting
rendered panel and Bash quickslot capture were reviewed.

The first runs failed on the right-click after scrolling. Hover inspection reached
the correct skill slot; the fixture had sent wheel presses without releases.
Completing wheel press/release pairs fixed event delivery. No production input
workaround was introduced. Final evidence: `.local/p6-skill-controls-r7/`; earlier
failed runs remain in r1–r5. r6 passed 22 checks before adding learn/drag coverage.
Targeted GDScript lint and actual native Godot execution pass.

This fixture supplies learned rows and wires the component drop signal; it does
not establish server-side learning, the complete HUD quickslot path or browser
casting. No new public export/deployment or connected-editor MCP inspection.
Next: use these coordinates in a focused exported skill-learning/casting replay.

## Spirit Strike and Bash ordinary-mob reactions — 2026-09-08

The shared `skill_reactions` replay now accepts `--reaction-skill 1|16|17`, with
Three-Way Cut as the default. Expected hit counts, GOOD flinch and force endpoints
are explicit scenario data. The approach uses two normal movement destinations
so self-targeted Bash faces the defender without granting a heading or position.
Nondefault skills are learned at level 6 using authorized setup and normal skill
reducers; setup retains the operator mutation limit. The option rejects use with
unrelated phases. No production combat handler, asset or public deployment changed.

Fresh selected-registry training databases for 16 and 17 each pass 30 checks with
two independent authenticated Godot clients. Original Grey Wolf 106 retains 412 HP
and original stats/AI. Spirit Strike: both observe health 412→359 and a
3.67500019073486 m push. Bash: both observe health 412→360 and exactly zero push.
Both observe original front knockdown and standup, recovery and a surviving exact
life. Evidence: `.local/p6-batch-reactions-r1/acceptance.json`, `skill-16.json` and
`skill-17.json`. Targeted Ruff/GDScript lint and the actual Godot runs pass.

These are rank-1 male-Warrior, single-species network replays, not rendered/browser
casting, all-species/rank balance or exact original physics qualification. The
frozen local module has QA bootstrap authorization and must not be deployed.
Next: exercise new-skill learning, quickslots and casting in the exported client.

## Public four-skill rollout accepted — 2026-09-08

Release `20260908T212416762304Z` is live on the public HTTPS endpoint, database
`mt2-public-skills-v26-20260908`. Explicit frozen module SHA-256:
`750f0c44bb4784dcc6d53eb35387ff07b8efe0932fc0907bc5bd12676f00279e`.
The deployed module uses the public auth issuer, guests disabled and no QA
bootstrap identities. Deployment verified the served manifest and retained auth
accounts, issuer keys and prior databases with `delete_data=never`. This fresh
protocol-26 world has a separate character roster.

Actual public Chrome/Linux QA passes 76 checks: independent account entry,
matching 2859-mob/44-species subscriptions, rendered peers, skill-panel input,
bidirectional movement, rejected invalid actions, character switching with saved
position, disconnect/reconnect, reload and logout/login. Browser engine errors
are empty. The public skill-panel capture was reviewed. Evidence and frozen
artifacts: `.local/public-skills-v26-r1/acceptance.json` and `browser-qa/report.json`.

This qualifies exported account/world integration, not browser casting of all four
skills, all-species combat, original specialization/physics parity or software
rendering performance. Next: qualify new-skill casting through exported controls
and ordinary-mob reactions, then continue missing mechanics and world content.

## Full-world skill exports and account lifecycle — 2026-09-08

Both matching Web/Linux exports and their actor/UI/mob/world package audits pass
for fresh local `mt2-p2-world-skills-v26-r1-20260908`. The module uses the original
Yongan population, four selected skills, local issuer, guests disabled and no QA
bootstrap identities. The local proxy on 8186 now serves this matching build.
Hardware-rendered Chrome (AMD Radeon 860M, WebGL2) and the Linux export pass 76
checks: two accounts, matching 2,831-mob/44-species subscriptions, rendered peers,
skill-panel keyboard input, bidirectional movement, invalid actions, character
switching with saved position, reconnect, page reload and logout/login. Browser
engine errors are empty. The browser skill panel and final world capture were reviewed.
This run does not exercise new-skill casting in the browser or all-species combat.

The first software-rendered run passed 46 checks before timing out on second
character entry. Its final snapshot remained loading at 2 FPS and 14.371 seconds
snapshot age, with no browser engine errors. The hardware run completed after
competing exports ended; this does not isolate the root cause or qualify software
rendering performance. Both reports remain under `.local/p6-world-skills-r1/`.

Public-issuer module and matching Web/Linux exports are prepared and audited in
`.local/public-skills-v26-r1/`, targeting `mt2-public-skills-v26-20260908`, with
bootstrap privileges absent. Public rollout and internet endpoint QA remain pending.
Deployment tooling now accepts `--module` to archive an explicit frozen artifact
without replacing the latest local WASM; 10 focused deployment artifact checks pass.

## Four-skill compatible batch — 2026-09-08

Enabled Spirit Strike (16) and Bash (17) through the existing selected-content
profile and physical-area handler, alongside Three-Way Cut (1) and Sword Spin (2).
Original formulas, icons, motions and event geometry compile through the existing
pipeline. Installed catalog SHA-256:
`ccd812f0c4199d90eafac822f07482edb53f21169168385b15b3ba279abca02c`.
No new combat handler or protocol schema was required. Skills needing charge,
status effects, magic or projectiles remain disabled until their mechanics exist.
Specialization selection is still pending; this development profile exposes both
Warrior trees and does not establish original skill-tree/UI parity.

Fresh local database `mt2-p2-skill-batch-v26-r2-20260908` passes 52 checks with two
independent authenticated Godot clients: learn all four, matching per-hit dummy
health histories (3/1/1/1), exact-life preservation and cooldown rejection. The
first attempt hit the operator's one-second mutation limit; test setup now waits
1.1 seconds between level commands, preserving the server limit and both databases.
Native equipped-animation QA passes 132 checks across both Warrior appearances.
Reviewed male Spirit Strike and female Bash samples retain hair, model and sword
attachments. Native UI QA passes 18 checks, including original icons and actual
mouse-wheel input reaching the last skill; the rendered scrolled panel was reviewed.
Nine live compiler checks, strict library Clippy and targeted Python/GDScript lint
pass. Evidence: `.local/p6-skill-batch-r1/acceptance.json`.

The panel now scrolls its content rather than overflowing as skills are added.
This is local native/headless-network evidence: no connected-editor MCP inspection,
new-skill ordinary-mob force replay, exported browser qualification or public update.
The existing Three-Way Cut Grey Wolf replay is separate evidence. Local frozen WASM
contains QA authorization and must not be deployed publicly. Next: matching full-world
browser export and endpoint qualification before the public development rollout.

## Original mob skill reactions and reusable authored layouts — 2026-09-08

Authored population overrides now validate against all vnums in the selected
verified mob package. Default builds retain their single-mob registry, and existing
named combat fixtures retain their exact contracts. Added the explicit training
layout `content/worlds/training.skill-reactions.population.json`, placing original
Grey Wolf 106 without altering its 412 HP, defense, animations or AI. Building this
layout without its selected package correctly rejects the unavailable definition.
Three population-parser checks and strict selected-registry library Clippy pass.

The new `skill_reactions` progression replay runs a specialized script through the
shared authenticated setup. Fresh database `mt2-p2-mob-skill-v26-r2-20260908` passes
28 two-client checks. Both clients observe health 412→411→410→409 on the same
surviving life, original front damage/knockdown/standup actions, a maximum push of
0.3919997215271 m, and return to idle. These are minimum-damage hits against the
higher-level creature, not a broad damage-formula qualification. First replay
observed both reaction phases but ended before recovery: original knockdown is
1.2 s plus standup 2 s, following the third hit. The test now waits for recovery
within an 8-second bound; no gameplay timing was shortened. Both test databases
remain intact. Evidence: `.local/p6-mob-skill-r1/acceptance.json` and `replay-r2.json`.

No public update or exported/browser qualification. Local frozen/default WASM is
QA-authorized and must not be deployed publicly. The negative-build assertion first
looked for the wrong error wording; inspection confirms the expected rejection
`Spawn 1 refers to an unavailable monster definition`. Next: matching browser/full
world export and public development rollout with appropriate endpoint QA.

## Equipped skill animation review — 2026-09-08

Added the focused `equipped_skills` native fixture, selecting Warrior skills
from the live catalog. Both appearances attach Sword+0, resolve
general skills while equipped in onehand mode, settle blending, and freeze four
sampled poses per enabled skill. Skeleton and equipment bounds plus exact action
IDs pass 68 checks. Evidence: `.local/p6-equipped-skills-r1/native-r3/` (reviewed captures in `native-r2`).
The fixture was moved out of the shared test to retain its existing file-size lint
limit; the final dedicated fixture also passes all 68 checks. The first
attempt exposed missing staging of the new fixture; staging now always copies the
selected script. Four Three-Way Cut captures (both appearances at 466666 and 799999
us) were reviewed: attached swords, intact character/hair/textures and bounded poses.
This is sampled native evidence, not complete animation or exported-browser parity.

No live runtime or public deployment changed. The remaining reaction replay needs
an ordinary mob that survives all three hits; original Wild Dog has 126 HP, while
other imported species have higher original health. Inspection found authored
population overrides still restrict the registry to the default mob vnum even
when a selected mob package is supplied (`selected_monster_spawns` in build.rs).
Next: allow authored developer layouts to use their selected validated registry,
then run a surviving ordinary-mob Three-Way Cut reaction/force replay without
changing original creature stats or weakening damage rules.

## Three-Way Cut installed and two-client damage accepted — 2026-09-08

The selected profile now enables original Three-Way Cut alongside Sword Spin.
Installed skill catalog SHA-256:
`a83222d77a4b9742045f835c731db9dcb5a7c70d62c383ebf5de360ecdbfc31d`.
The client accepts the area handler. Original discovered skill icons were imported;
default UI rebuilding now also reads installed skill icons, so future rebuilds
retain the selected abilities without manual importer edits.

Fresh local database `mt2-p2-three-way-v26-r1-20260908` passes 25 real authenticated
two-client checks: learn/equip, missing target rejection preserving SP/revision,
peer-observed approach, stale-life rejection, accepted target/cast, exactly three
matching health transitions on one dummy life, server facing and replay/cooldown
rejection. Initial replay failed at a nested-lambda Godot parser error; extracting
a helper fixed the script before the accepted run. Native skills-panel QA passes
14 checks; reviewed capture shows both original icons and skill names. Eleven
focused Rust skill and nine compiler checks pass, as does strict library Clippy.
The malformed-input compiler fixture now selects Sword Spin by vnum, removing its
old assumption that it was the first installed row. Evidence:
`.local/p6-three-way-r1/` (accepted replay is `replay-r2.json`).

No connected-editor MCP inspection or exported/browser acceptance is claimed.
Training dummies intentionally do not react, so this run does not qualify real-mob
flinches/knockback. Equipped weapon animation review for both Warrior appearances
and real-mob reaction acceptance are next. No public update; frozen/default WASM
contains local QA bootstrap permissions and must not be deployed publicly.

## Required skill targets and normalized area clocks — 2026-09-08

Area skill targeting now compiles from original flags/range data. Three-Way Cut
requires a live selected target but has zero authored cast range; local geometry
still controls damage. Cast acceptance verifies the exact selected monster life,
uses server positions to derive facing, preserves coincident-center heading and
keeps the ordinary-hit action plan disabled. Invalid target transactions roll back
without SP/cooldown changes. Positive authored ranges use exclusive boundaries.

The compiler normalizes area activation to the source next-60-Hz-bucket boundary
and retains duration: Three-Way Cut 166667/450000/850000 us plus 200000 us each.
Raw imported source metadata is preserved; Sword Spin's catalog is byte-identical.
Eleven focused skill checks, nine compiler checks, strict library Clippy and Ruff
pass. The two-skill candidate compiles at `.local/p6-skill-target-r1/`. These are
not real target-reducer or Three-Way Cut multiplayer acceptance. No schema, public
world or installed skill-catalog change. Next: original icon/content installation
and the actual two-client Three-Way Cut target, damage and reaction replay.

## Original GOOD flinch catalog and runtime — 2026-09-08

Verified mob presentation packages now compile front/back weighted damage clips
into a derived server GOOD-reaction table. The small default fixture uses its own
manifest. No source asset or installed package changes were needed. GOOD skill hits
publish original flinches via private reaction phases 5/6, retain attack/knockdown
locks, and allow flinch replacement by a later GOOD/GREAT response. The existing
reaction lifecycle returns completed flinches to idle. No schema columns changed.

Seven knockback tests, two reaction-compiler tests, one package-integrity test,
strict library Clippy for default and selected 44-mob/Yongan configurations pass.
The existing native mob fixture now exercises every front/back damage variant:
1,622 Godot checks pass across 44 mobs. Evidence: `.local/p6-good-reactions-r1/`.
No connected Godot MCP was available; the run used isolated Godot/Xvfb. Controlled
actor-state QA does not establish multiplayer flinch acceptance or exact source
physics. No public update or new ability enabled. Next: target requirements and
source event dispatch, followed by the complete Three-Way Cut live replay.

## Authored skill cooldowns and GREAT response — 2026-09-08

Fixed-area events now compile bounded original reaction metadata. Runtime checks
the shared victim cooldown before damage/receipts, writes the event cooldown on
success, and routes surviving GREAT hits to existing force/knockdown/recovery.
The analytic unit-mass/friction endpoint preserves force-5 (0.392 m), force-15
(3.675 m) and force-17 (4.732 m) values; existing one-second interpolation remains
an approximation of original physics. GOOD flinch presentation remains missing.
Nonzero stiffen, GOOD pushes and unsupported collision/attack policies reject at
compile time instead of being silently discarded.

The original Three-Way Cut candidate compiles with all three reaction records.
Ten focused skill tests and seven compiler tests pass; strict library/example
Clippy passes after removing an unused import. Source behavior was inspected in
the pinned client's GameType, ActorInstanceBattle and PhysicsObject files. Evidence:
`.local/p6-skill-reactions-r1/`. No new database/schema, live cast, export or public
qualification is claimed. Previous 50 client checks apply to the preceding build.
Next: normal-hit flinch definitions, required target acceptance and source dispatch
quantization, then install/qualify the complete Three-Way Cut slice.

## Live compiler and fixed-area resolver — 2026-09-08

The live skill compiler/linker now supports catalog-selected fixed areas and
preserves original ordered geometry per event. A candidate with Three-Way Cut and
Sword Spin compiles without replacing the installed catalog; the legacy catalog
rebuild remains byte-identical. A reusable `compile_live_skills` example validates
candidates without installation. The runtime seeds validated exact-life defending
centers on activation, skips that tick, resolves swept spheres at frozen placement,
and refreshes samples with removed lives discarded. It shares the existing combo
victim-center computation. Per-event receipts remain downstream of geometry.

Nine focused skill tests, eleven area tests (overlapping scope), seven compiler
checks, two Python linker checks, strict library/example Clippy and formatting
pass. Fresh local database `mt2-p2-live-area-v26-r1-20260908` passes 35 skill and
15 combat checks with two authenticated clients for the unchanged installed Sword
Spin catalog. Evidence: `.local/p6-live-area-r1/`. These checks do not exercise
Three-Way Cut on the live server. Its required-target semantics, original reactions/
knockback, dispatch quantization and icon integration remain pending before enabling
it. No schema change or public deployment; local WASM remains QA-authorized only.

## Persisted skill-area placement — 2026-09-08

Protocol 26 stores optional activation origin, heading, tick and exact-life target
samples per skill event. Activation validates the controlling lease/action/life,
advances root motion to the event boundary and captures placement once. Target
sampling and live fixed-area collision dispatch remain pending; Sword Spin still
uses its radial handler. Its regression replay passes 35 skill and 15 combat
checks with two authenticated Godot clients. The separate account/network replay
passes 74 checks, including rejected intents, movement, disconnect and reconnect.
Eight Rust skill tests (including nested placement BSATN round-trip), six protocol
checks, strict library Clippy, formatting and changed-source GDScript lint pass.
Generated 95 bindings from fresh database `mt2-p2-area-state-v26-r1-20260908`.
Evidence: `.local/p6-area-state-r1/`. No browser/exported or connected-editor QA is
claimed. Public protocol 24 is unchanged. The default WASM and frozen local module
contain QA bootstrap permissions and the local auth issuer; do not publish them
publicly. Next: populate target samples and connect original fixed-area geometry.

## Shared fixed-area activation lifecycle — 2026-09-08

Extracted the existing combo fixed-area activation phase rules and introduced
validated placement capture. The combo resolver now uses both shared helpers;
ordinary finite placement remains unchanged. Candidate Three-Way Cut area replays
capture placement on activation, skip that tick, and scan through the same shared
lifecycle before geometry/admission checks. Four candidate replays and ten focused
Rust area checks pass; strict Clippy passes. Evidence:
`.local/p6-area-lifecycle-r1/`. Skill pending state does not yet persist these
placements, so live fixed-area skill dispatch remains pending. No protocol or
public deployment changed in this step.

## Catalog-driven skill repeat limits — 2026-09-08

The live profile/linker/compiler now accept an optional bounded `hits_per_life`,
defaulting to one. Accepted casts capture this generated value into the existing
protocol-25 pending state instead of fixing the value in runtime code. Total hit
budgets and per-event deduplication remain separate. Four live compiler tests and
eight runtime tests pass; the current Sword Spin catalog rebuild is byte-identical.
No schema or live content change is included. Strict library Clippy passes.
This remains local preparation for Three-Way Cut's area handler; no new multiplayer
casting acceptance is claimed for this change.

## Live-catalog event dispatch — 2026-09-08

The live schema-v1 compiler now emits event lists keyed by skill and appearance,
with legacy single-window fallback. Optional multi-window lists must have ordered
unique starts and match the action's overall bounds. The accepted cast path reads
these generated lists rather than constructing a single event from the action.
Eight focused skill tests, three live compiler tests, formatting and strict library
Clippy pass. No new ability/catalog or schema is enabled, and the previous 50 live
Sword Spin checks apply to the preceding runtime. The new local change still needs
casting qualification with the next content integration. Three-Way Cut's area
handler and source-specific reaction/target semantics remain pending.

## Installed full skill motions — 2026-09-08

Rebuilt the verified `.local/p6-class-skills/characters-r4` conversion with the
current catalog generator and installed eight actors with 88 skill motions.
The optional `--preserve-existing-motions` installer guard verifies all 236 prior
motion records plus attachment/mode contracts before swapping, preserving the old
package at `.local/p6-skill-install-r1/runtime-r2-previous-install`. Two targeted
guard tests pass. Native Godot class-skill QA passes 625 checks; male/female
Three-Way Cut captures were reviewed (pose-only, without equipped weapons).
No connected Godot MCP tool was available; QA used isolated Godot/Xvfb.

The live skill linker now prefers installed character definitions over the base
Warrior fallback. An offline compile preserves Sword Spin's exact catalog bytes.
Evidence: `.local/p6-skill-install-r1/acceptance.json`. The new character hash is
not published to running servers; matching module/exports remain required. No
additional live skill is enabled. Next: Three-Way Cut's live content/area dispatch.

## Protocol-25 live Sword Spin acceptance — 2026-09-08

Fresh Yongan database `mt2-p2-skill-cast-v25-r1-20260908` passes 35 real
authenticated skill checks and 15 combat checks on runtime source `32e0109`.
Both headless Godot identities observe casting and damage; learning, stale-rank
rejection, SP spending, operator permission, cooldown persistence, disconnect/
reconnect and private skill state pass. The combat continuation checks movement
in both directions, actual dog damage replicated to both clients, one hit per
monster life and return movement. Evidence: `.local/p6-skill-cast-r1/acceptance.json`.
This is Sword Spin acceptance, not rendered/exported browser QA or Three-Way Cut.

The initial sign-in failed with local HTTP 502. Listener inspection confirmed the
auth process was stopped. Read-only account-presence checks identified the existing
`.local/p1/auth` database; restarting its existing service on loopback 13224 restored
sign-in without resetting accounts or keys. Existing private QA accounts were copied
into an owner-only fixture and reused. The new module authorizes only the previously
configured QA operator identity; it is not a public deployment artifact. The default
WASM build now contains this local-auth Yongan QA module with bootstrap privileges.
Do not publish it publicly. Public protocol-24 release remains unchanged.

Next: install candidate motions and connect Three-Way Cut's compiled events/shapes
to accepted cast state and original reaction/target limits before enabling it.

## Protocol-25 persisted skill events — 2026-09-08

Pending skill state now stores an ordered list of event deadline records plus a
captured per-life hit limit. The simulator visits each active event with its stable
index and retains connection/action/life validation, total budgets and receipt
ordering. Sword Spin still supplies one event and one hit per life; Three-Way Cut
is not yet installed or enabled. Client protocol expectation and gate tests are
updated; all 93 bindings were generated from the actual fresh database and parsed
by Godot. Schema SHA-256:
`0908670e47ef6ebdae5b2482671a3ea19e878147474585f92455ec21a85a425c`.

Evidence: `.local/p6-skill-state-r1/acceptance.json`. Eight focused Rust skill tests
pass, including actual BSATN event-list round-trip; strict Clippy and six Godot
protocol checks pass. Fresh guest-disabled database
`mt2-p2-skill-state-v25-r2-20260908` passes 74 real authenticated account/network
checks, including bidirectional movement, rejected intents and reconnect. The
network-only scope does not exercise actual skill casting. The preceding guest
smoke failed character ownership; the full authenticated replay reached movement
then failed obsolete basic-combat expectations (one-second swing/fixed 35 damage).
Both failure reports are retained; they are not reported as passing combat QA.
The protocol gate's first import was blocked by sandbox sockets; its isolated retry
passed with local socket access. Signup cooldown was respected between account runs.

Existing development/public databases were preserved. The public endpoint still
serves protocol 24; protocol 25 requires a fresh world and matching exports before
any rollout. The default local WASM output is now the guest-disabled protocol-25
Training module; do not deploy it as the public Yongan module. Next: live skill-cast
qualification, candidate motion installation and multi-event area dispatch.

## Compiled skill area resolution — 2026-09-08

Candidate fixed-area geometry now calls the shared server rotation/sphere sweep.
The generated resolver validates placement and rejects weapon-window dispatch
until sampled attachment geometry exists. Four Three-Way Cut replays combine both
appearances/two headings with actual compiled shapes, captured clocks, event masks
and hit receipts. Front targets get three distinct receipts; rear/elevated targets
miss and repeated ticks do not add hits. Six compiler tests and all prior formula/
metadata/geometry checks pass. Evidence: `.local/p6-skill-area-r1/`. This is offline
geometry/admission evidence, not damage or two-client cast acceptance. Persistence,
activation placement and original hit/reaction policies remain pending; public
server and installed content are unchanged.

## Accepted skill event clocks — 2026-09-08

The accepted cast path now captures validated absolute event deadlines before
mutating gameplay state. It rejects overflow, negative clocks and authored offsets
beyond the supported motion lifetime without returning partial capture state.
Seven skill tests pass; both candidate Three-Way Cut appearances pass replays on
a nonzero captured clock. Evidence: `.local/p6-skill-capture-r1/`. The pending table
still stores Sword Spin's original single interval, with no schema/protocol change.
Multi-event persistence and activation placement are not yet integrated. Inspection
also confirmed the installed character package lacks `skill_1`; the existing
candidate package contains both appearances. Their installation and matching
content-hash rollout remain prerequisites. Public deployment is unchanged.

## Shared skill event selection — 2026-09-08

The live single-window resolver now calls the shared event selector in `skill_hits`.
Six focused skill tests pass, including separated/overlapping windows, boundaries,
expired windows, invalid timing and the 32-event bound. The candidate qualification
runs both compiled Three-Way Cut appearances through the actual selector and ledger;
repeated ticks produce exactly three receipts. All existing formula, metadata,
window and geometry checks also pass. Evidence: `.local/p6-skill-events-r1/`.
Strict library Clippy passes. No new ability is enabled: this replay assumes an
eligible target and does not establish shape intersection, damage or two-client
casting. Multi-event capture/state and original area endpoint policy remain pending.
The public server is unchanged.

## Shared runtime collision primitives — 2026-09-08

The existing combo fixed-area resolver now uses shared rotation and full-3D
sphere-sweep functions in `server/src/combat_geometry.rs`. Its existing geometry
is unchanged, with explicit rejection added for nonfinite inputs, invalid radii
and overflowing squared values. Eight area regressions and two focused geometry
tests pass. The first compile found test-only references to the extracted distance
helper; a test-only import fixed those before the successful run. This is a local
runtime refactor, without protocol changes or server deployment. Skill shapes
still need event-state/activation integration; no extra live skill is claimed.

## Candidate skill collision geometry — 2026-09-08

The full-class compiler now emits typed attack-area spheres and weapon-window
bone/length data in source event order alongside the hit intervals. It rejects
unknown coordinate systems, invalid lists, nonfinite/out-of-range positions and
nonpositive sphere radii. Zero-length source weapon windows are preserved.
Six compiler tests and generated-Rust comparisons for all 88 geometry arrays pass,
alongside 88 timing comparisons and existing formula/metadata qualification.
Evidence: `.local/p6-skill-geometry-r3/`. This remains candidate content work;
no additional live skills or protocol changes are included. Runtime shape sampling
and attack/reaction parameters remain necessary for source-faithful resolution.

## Shared skill hit admission — 2026-09-08

`server/src/skill_hits.rs` now separates per-event deduplication, exact monster-life
identity, per-life repeat limits and a total successful-hit budget. The existing
Sword Spin resolver calls it with event zero and one hit per life, retaining the
old persisted receipt format and catalog target budget. Five focused runtime tests
pass (three ledger, two existing skill tests); this is local source work without a
server publication or two-client casting replay. No additional ability is enabled.
The first compile exposed a monster ID width mismatch, corrected to the runtime's
u32 ID before the successful tests. Original source research distinguishes
per-target repeat limits from animation event count; Three-Way Cut allows three
in the pinned server's `CheckSkillHitCount`. Scheduling, collision shapes and
source-specific limits still need integration before enabling multi-hit skills.

## Candidate multi-hit skill timing — 2026-09-08

The full-class compiler previously discarded hit-window end times. It now emits
separate validated intervals on `ClassSkillMotion`, preserving source order and
post-animation attack-area lifetime bounds. Missing intervals, unknown kinds,
reversed/out-of-bounds times and starts without activations reject. All 88 emitted
appearance records match the input catalog in generated Rust; four compiler tests,
21,120 formula evaluations and 221 metadata checks pass. Evidence:
`.local/p6-skill-windows-r1/qualification-r2/`. The first harness run exposed an
incorrect Rust integer cast in the new assertions; the corrected typed binding
passes. No live skill or protocol change is included. Next is consuming the
separate intervals and original collision/hit-limit semantics in cast resolution.

## Streamed-map UID restoration — 2026-09-08

The local streaming loader now registers dependency UIDs from hash-verified mounted
packs before loading a map section. The full export's UID registry is not available
in the separate core client/isolated pack loader; path fallback previously produced
876 warning/location messages during ordinary public play. A clean-loader experiment
registered 169 IDs for entry section 002002 and removed its warnings without
changing the asset packs. The reusable helper validates the graph before writing
IDs and refuses namespace violations, missing resources and existing-ID conflicts.

Evidence: `.local/performance/world-uids-r1/`. All 20 existing public map packs pass
the updated isolated audit, including original terrain data texels and prop textures,
with no invalid-UID warnings. The native focused regression reports ten checks;
GDScript formatting/lint and touched Python Ruff checks pass. These checks exercise
real Godot resource loading, but not a rendered browser export or the connected
editor. The fix is deployed as release `20260908T181619790682Z`, preserving the database
and server module. `.local/public-world-uids-r1/acceptance.json` binds the export
and final 43-check public report. Both clients completed the field route; ordinary
browser reentry/WASD reached the native peer, with zero warnings/errors. Browser
field and ordinary-world captures were reviewed. Short browser cadence was 38.5
with diagnostics and 60.1 without; no FPS improvement from this fix is claimed.
The native peer used the preceding export; native map loading was unchanged.
The first export stopped on sandbox socket restrictions; the isolated retry with
local socket access passed export and all 20 pack audits. Full combat/lifecycle
QA was not repeated. The connected editor was not inspected.

## Opt-in export diagnostics — 2026-09-08

New test exports remove the probe at startup unless browser automation explicitly
sets `window.mt2ProbeEnabled = true` before loading, or a native launch supplies
nonempty probe report/command arguments. The disabled path installs no connection
hooks and produces no snapshots or command bridge. Both standard browser runners
enable it through context init scripts, preserving reload behavior. Normal release
exports still exclude the probe entirely; activation is not server authorization.

Evidence: `.local/performance/probe-opt-in-r1/`. Native activation checks pass 20
cases across disabled/report/commands modes. Actual browser exports pass enabled/
disabled startup and reload checks; the ordinary entry capture was reviewed.
The focused two-client field replay `field-qa-r3/report.json` passes all 45 checks.
It restores the same account using an in-memory IndexedDB-inclusive storage
transfer into a clean browser context without QA scripts, verifies absence of
the probe, and proves reentry and keyboard movement through the independent
native client's rendered subscription. The earlier ordinary-world capture was
reviewed; the final run also retains its screenshot.

Five-second browser animation-frame samples measured 28.9 frames/sec with capture
and 60.1 without it. These are short sequential browser cadence measurements,
not a controlled Godot/release benchmark. Instrumented Godot field median was
29.5 FPS. Original map UID fallback warnings remain (876 warning/location messages
retained); all were checked against the final strict classifier with zero unexpected
errors. A regression test retains these warnings while rejecting engine/script
and unknown console errors. The earlier run was stopped to correct missing
IndexedDB transfer; another completed movement checks but failed the initial
overbroad console-error collector. Those reports are retained.

Public release `20260908T180128789164Z` now includes the optimization (source
`4102a94`). `.local/public-probe-opt-in-r1/acceptance.json` records frozen export
and module hashes. The module and database are unchanged; accounts and characters
were preserved. Public activation startup/reload checks and 52 focused two-client
checks pass, including eight previews, field mobs and ordinary reentry/WASD.
Public browser cadence measured 37.2 with capture and 58.9 without in short
sequential samples; no engine-FPS claim. Browser errors are empty; 876 map UID
warning/location messages remain. This does not repeat the previous 114-check
combat/lifecycle run or establish all-class combat. Character export validation
also accepts only pixel-verified Godot DDS PNG aliases (seven focused tests).
Next: map resource warnings and continued performance/fidelity work.
No connected editor inspection was available.

## Public original-population rollout — 2026-09-08

The public endpoint now serves protocol 24, database
`mt2-public-population-v24-20260908`, release `20260908T170855056942Z`, runtime
source `0b9d0df`. The module was built for the public auth issuer with guests
disabled, the selected mob catalog and original 945-entry regeneration package.
Frozen module/exports, deployment log, served-manifest comparison and hashed
acceptance are in `.local/public-population-r1/`. Existing accounts, keys, previous
databases and unrelated containers were retained; the new world has its own roster.

Actual public Chrome/Linux replay `browser-qa-r3/report.json` passes 114 checks,
including field combat/death and loot, complete outward/return route, bidirectional
movement, reducer rejection, character switching, disconnect/reconnect, browser
reload and logout/login. Browser errors and native engine/script errors are empty.
Both reviewed ground captures show original models and separated item/Yang names;
player-name overlap remains possible because character labels use a separate path.

The first run exposed an invalid census assumption: the 44-species catalog is a
set of possible variants, not a guarantee that all occur simultaneously. Both
clients observed identical 2,812-mob/42-species populations; absent vnums 354/391
share one of ten selector-110 group choices. The test now reports observed and
catalog species separately while preserving duplicate/finite/registered-species,
full-world size and peer equality checks. Four focused evidence tests pass.
The second run reached the fixed local route's endpoint but no mob was in camera
range; the successful third used the existing offline collision-route generator
to reach an observed public group. No server mobs were moved, reset or reseeded.
Completed field evidence now survives a later replay failure.

The public field's instrumented Chrome median was 26.5 FPS; native remained slow.
The earlier local return/resubscription stall was not reproduced here but its cause
is not established. Next performance slice: make expensive export-test snapshots
opt-in for QA, then measure ordinary exported play. All-skills gameplay, scenery,
additional maps and the remaining full-rebuild milestones are still incomplete.

## Shared ground-label layout — 2026-09-08

`WorldDropLabels` now projects nearby ground names into a viewport-local canvas
below the HUD. It uses five-pixel downward collision spacing and a bounded 20-pass
adjustment, informed by the pinned original text-tail contract. The independent
implementation places labels in stable scene order; it does not claim identical
ordering to the original all-pairs arrangement. Extremely crowded piles can still
reach the adjustment bound or extend beyond the viewport. Original font, owner
text, visibility-key and label-click pickup parity remain pending.

Only loot Label3Ds join the shared group; monster names remain unchanged. The
overlay follows camera/viewport changes, ignores hidden/offscreen/behind-camera
drops, removes freed entries and restores fallback labels on teardown. It never
consumes pointer input and does not change server pickup or ownership validation.

Evidence: `.local/items/drop-labels-r1/`. The focused lifecycle/layout scenario
passes 21 checks headless and in native rendered Godot. The real converted-item
fixture passes 30 checks, including separation of three nearby names; its rendered
capture was reviewed. Initial isolated staging omitted the shared art helper's
ItemCatalog dependency; correcting the staged inputs resolved the parser failure.
GDScript lint passes. Actual web/Linux exports completed and the two-client field
combat/drop replay passed 49 checks with no browser engine errors:
`.local/items/labels-live-r1/report.json`. Both post-kill captures were reviewed:
the potion and 21-Yang names are visibly separated on the map. The replay now saves
a fresh native drop capture as well as the browser capture. Three browser predicate
tests pass. The local endpoint serves these exports; public deployment remains
pending. No connected editor was inspected because Godot MCP is not exposed in
this session. Broader performance and the earlier combat-return stall remain open.

## Original ground models installed and exported — 2026-09-08

`tools/install_ground_items.py` validates the normalized source identity and the
converted artifact references, paths, hashes and byte counts, then uses the staged
installer with a ground-content receipt. Matching repeats verify bytes; changed or
unowned destinations reject. The mob installer's existing identity field remains
the default, with an explicit optional field for this presentation package.

The installed shared Godot catalog caches selected PackedScenes. `PveActor` now
uses the original coin pile for Yang and the shared red bottle for the two selected
potion sizes. These stay settled instead of spinning/bobbing. Unsupported item
models retain the catalog-icon fallback; old fixtures without this optional package
retain their fallback presentation. Server quantities/ownership/pickup are unchanged.

Controlled native checks pass 23 cases. Six installer tests and three browser
predicate tests pass. Actual web/Linux exports completed; the focused original
field combat/drop run passed all 48 checks with no engine errors:
`.local/items/ground-live-r1/report.json`. Both probes matched original model paths
and labels for the owned Small Red Potion and 26-Yang drops (separate tables with
matching numeric IDs). The reviewed browser capture shows bottles/coins on-map;
a post-kill native screenshot was not captured. Hashes and scopes: `acceptance.json`.

The package is installed in the working client. Public deployment remains unchanged.
Labels still overlap, and original falling/landing/glow effects remain pending.
Next: screen-space drop labels and the public progress update.

## Original ground-model conversion pipeline — 2026-09-08

The new `tools/import_ground_items.py` resolves an explicit selected item-list set,
deduplicates shared models, fetches their pinned texture dependencies and reuses
our Blender item converter. `--godot` imports/renders an isolated Linux preview;
`--offline` reuses verified cached sources. Defaults are Yang and the two existing
red-potion sizes, resolving to two original models (92,728 bytes total).

Two parser tests pass. Offline normalization exactly matches online normalization.
The complete offline Blender/Godot command passed in `.local/items/ground-pipeline-r2`;
all three preview instances have textured meshes and valid bounds. Reviewed native
capture shows original coins and red bottles. Hash evidence: its `acceptance.json`.
See [ground-item workflow](../ground-items.md). This is conversion/preview only:
models are not yet installed in gameplay; ground placement, original drop animation,
label overlap and exported runtime qualification remain pending. Public is unchanged.

## Item-drop names and icons use the shared catalog — 2026-09-08

`PveActor` no longer presents every item drop as a Small Red Potion. The subscribed
vnum resolves the installed item catalog name and original icon. Repeated state
updates reuse the visual; a changed vnum updates both fields, and an unknown ID
clears the old texture and displays an explicit unknown-item label. The diagnostic
snapshot exposes vnum, label and loaded icon path for reusable tooling.

The native controlled scene passes 15 checks for Small/Medium Red Potions, Sword+0,
changed definitions, unknown-ID clearing and authoritative Yang label amounts.
Reviewed capture: `.local/items/drop-catalog-r1/data/godot/app_userdata/MT2 Actor Test/item-drops.png`.
Evidence/hashes: `.local/items/drop-catalog-r1/acceptance.json`. Original installed
icons were reused; no new source assets or external code were copied.
This corrects item identity, not classic ground rendering: icons still use the
existing billboard presentation, the Yang block remains, and label overlap is
unresolved. No new export, public update or connected editor inspection occurred.

## Held attack acknowledgement gate — 2026-09-08

Main now allows one outstanding attack request and suppresses repeated held input
against the same accepted idle sequence/life. Space and the attack HUD share the
gate. Release stops repeats without discarding an outstanding request; rejection
permits an idle retry; leaving the connection resets it. Local reducer send failure
now emits failed completion as well as the existing notice. Server rules and
rejection notices are preserved, not suppressed.

The real Godot scheduler scenario passes 17 checks, and the converted Shaman fan
fixture passes 87 checks including input windows and duplicate-link prevention.
Actual browser/Linux exports passed packaged mob audits. The separate lifecycle
run `.local/combat/held-gate-lifecycle-r1/report.json` passes all 74 checks, including
movement rejection, character switching, disconnect/reconnect, reload, wrong
password and world re-entry. No engine errors were reported.

The combined field run `.local/combat/held-gate-live-r1/report.json` remains FAILED:
50 checks completed, including equipment, selection and replicated death of Wild
Dog 902837 (vnum 101, life 0, initial 126 HP), then return waypoint 4 timed out while
the browser was subscribing and native remained connected. The exact cause is
unresolved. The reviewed capture shows the corpse and a cooldown notice. Recorded
browser warnings: three late-input, one cooldown and one defeated-player rejection;
no duplicate-queue notice. This is not a warning-free or full-route acceptance.

Scoped evidence/source/export hashes: `.local/combat/held-input-gate-r1/acceptance.json`.
A live disconnect specifically during a pending attack was not injected; that
reset transition is covered by the focused scheduler scenario. Public deployment
is unchanged. Remaining work includes cooldown/late-window pacing, the return
route/resubscription failure and loot presentation.

## Held attack stale-idle request finding — 2026-09-08

A focused headless Godot reproduction confirms that `AttackInput.should_send`
issues repeated intents at 1,150, 1,300, 1,450 and 1,600 ms after a first press at
1,000 ms when the subscribed idle row remains unchanged. This path has no pending
request/acknowledgement gate. It can enqueue redundant requests during the delayed
subscriptions observed in the field replay. This does not establish that every
combo rejection has the same cause.

Evidence/source hashes: `.local/combat/held-input-audit-r1/finding.json` and
`runtime-isolated.log` (replayed with writable isolated userdata after the initial
run reported userdata permission errors). No gameplay change was made in this investigation. The next input
change must coordinate acknowledgements with authoritative action observation and
cover rejection, release and reconnect, rather than merely increasing the 150 ms
delay or hiding server rejection messages. Server queue validation stays intact.

## Original field combat through exported input — 2026-09-08

`--field-combat --field-only --mob-route <route>` now equips the current Warrior
fixture's existing Sword+0 through the inventory UI, confirms both appearances,
clicks a nearby original mob, verifies its exact selected life, and holds Space
through replicated damage/death. No privileged damage or reset is used.
`.local/mobs/field-combat-r3/report.json` passed all 47 exported checks: target
900053, Hungry Stray Dog vnum 171, life 0, went from its full 101 HP to zero.
Both clients recorded fresh health events 61, 41, 23, 3, 0. The reviewed browser
capture shows the corpse and ongoing world rendering. No engine errors occurred.

The first attempt left the starter sword unequipped and the player died before
the mob. The second equipped replay killed the mob, but requiring both current
snapshots to show a temporary corpse simultaneously timed out. The fixed checker
uses each client's fresh exact-ID/life health subscription history, preserving
short-lived observations across delayed clients. Two focused unit tests cover
corpse removal, stale/wrong-life/wrong-ID events and nonlethal damage. Both earlier
failed reports are preserved; they were not relabelled as passed.

Evidence and frozen export/source hashes: `.local/mobs/field-combat-r3/acceptance.json`.
This qualifies the selected encounter, not all species or reward/drop fidelity.
Held attacks still show combo-queue rejection notices; loot visuals/overlapping
labels need work. The run reused the previously audited debug-cost exports; the
latest distance-before-terrain optimization remains separately native-qualified.
Public endpoint and database schema are unchanged. Next: input pacing/presentation
polish and an integrated public progress update.

## Reject distant rows before terrain lookup — 2026-09-08

The shared presentation filter now performs the original distance calculation
before terrain readiness. Main captures the viewer once per pass and constructs
actor keys only for included rows. NPCs no longer query readiness twice. Range,
terrain, server authority and subscription contracts remain unchanged.

The focused native Main fixture passed 43 checks, including 2,800 rows producing
only one terrain lookup when one row is nearby, distance edges, invalid position,
terrain unload and latest-life re-entry. The NPC fixture passed all 56 checks.
Both used isolated copies of already imported assets, avoiding another asset
conversion/import cycle. Evidence: `.local/mobs/visibility-cost-r1/acceptance.json`.
This is work-count evidence, not a measured FPS gain. No export, public deployment
or connected-editor inspection was repeated for this behavior-preserving change.

## Nearby NPCs and measured debug overhead — 2026-09-08

Main now supplies the local player position to the NPC layer, applying the same
original distance policy as mob presentation. Native NPC coverage passes 56 checks,
including range exit/re-entry, missing viewer and the guard. Resources still load
eagerly; only instance/animation work is reduced. Hidden debug HUDs no longer build
full developer snapshots four times per second.

Actual browser/Linux exports passed packaged mob audits and the 42-check focused
field replay in `.local/mobs/debug-cost-field-r1/report.json`. Both clients received
the same 2,835 mobs/44 species and rendered original field mobs; reviewed captures
show terrain/materials and the original dog models. No browser/native engine errors
were reported. This scoped run omits unrelated account lifecycle tests.

The new `--field-only --profile-probe` workflow measures a five-second interval
without periodic full probe snapshots, then resumes them. Chrome measured 18 FPS
with snapshots and 34.1 mean FPS during the pause; Xvfb native measured 7 and 10.3.
These are short sequential samples with the original reference client still
running, not a controlled release benchmark. Event-history callbacks remain active.
Snapshot instrumentation materially affects the observed results; further release
profiling and scene/network work remain. No public deployment or connected editor
inspection occurred. Acceptance and source/artifact hashes:
`.local/mobs/debug-cost-export-r1/acceptance.json`.

## Changed mob writes and complete exported field/lifecycle replay — 2026-09-08

Simulation now compares the complete before/after `Monster` and `MonsterClock`
records and writes only changed values. This preserves publication of action,
target, life and timing changes while avoiding identical writes for idle population.
No database fields, protocol or bindings changed. Strict selected-Yongan library
Clippy passed. The selected two-member regeneration fixture passed all 74 real
combat/reconnect checks in `mt2-p2-changed-writes-r1-20260908`.

The frozen optimized Yongan module was applied without data deletion to existing
`mt2-p2-original-linked-r1-20260908`. Using the same frozen client exports and route,
`.local/mobs/changed-writes-field-r1/report.json` passed all 110 checks with no browser
engine errors. Both exports received the same 2,835 mobs across 44 species, rendered
original field mobs, walked out/back, rejected invalid movement/foreign character
selection, switched characters, disconnected/reconnected, recovered browser reload,
and completed logout/password-login paths. The earlier foreign-selection timeout
did not recur; this is consistent with timing/load sensitivity but does not prove
its exact cause. No permission or auth checks were weakened.

Field medians were Chrome 24 FPS (previous 22) and Xvfb native 7 FPS (previous 7).
That small browser difference does not establish a material rendering improvement;
normal release performance remains unqualified. Server publication work is reduced,
but further profiling, probe overhead and rendering work remain. Existing reviewed
field captures from the baseline and new captures remain in their run directories.
Next: field combat and performance work before the public progress update.
Public endpoint still uses protocol 19. Artifact hashes and scoped acceptance:
`.local/mobs/changed-writes-r1/acceptance.json`.

## Generated field route and exported mob baseline — 2026-09-08

`server/examples/world_route.rs` adds a bounded offline route planner using the
runtime terrain/footprint/clear-path functions. It emits map-hash-bound waypoints
with segments up to 12 m, without changing game state. The selected path from
(660,575) to (788.39,553.6) is in `tests/fixtures/yongan-hunting-route.json`.
Repeated generation was identical; blocked destination (770,552) and out-of-bounds
start were rejected. Focused Rust example Clippy and Python lint passed.

`--mob-route` now walks both real exports out and back, requires common visible
animated original mob IDs, captures both renders and records instrumented FPS.
`.local/mobs/full-world-field-r1/acceptance.json` preserves 64 successful checks,
no browser engine errors and the same frozen client/server builds as the previous
export run. Both exports reached original Hungry Stray Dogs, rendered them, and
returned to town; root reviewed browser/native field captures. The normal movement
and invalid movement rejection checks also passed. The full scenario did not pass:
it timed out at `foreign_character_selection_is_rejected` after native world leave,
with no captured reducer error. Investigation remains required; this is neither
proof of foreign access nor proof that rejection reached the client.

Field samples recorded 40 instantiated mob actors, median Chrome 22 FPS and Xvfb
native 7 FPS. Chrome used the AMD Radeon 860M through ANGLE; native execution uses
its test display configuration. These are instrumented baselines, not release
benchmarks or acceptable performance qualification. Existing debug snapshots are
about 2 MB each, and simulation currently writes every live ordinary mob and clock
unconditionally each tick. Next: suppress unchanged writes and measure their effect,
investigate the lifecycle timeout, then field combat and public deployment. Public
endpoint remains unchanged. The signup cooldown was respected before this run.

## Full-population browser/Linux exports and partial qualification — 2026-09-08

Actual test exports from client source `fd25ed5` are frozen in
`.local/mobs/full-world-export-r1/{web,linux}`. Their normal export audits passed;
additional actual-pack audits loaded all 44 definitions, 19 models with skeletons,
meshes/nonempty animation libraries, and referenced projectile resources on both
targets. `tools/audit_mob_pack.gd` now performs this audit, and future playable exports
include it in their build manifest when mobs are installed. The existing exports
were audited separately; their original manifests were not rewritten.

The local proxy at `http://127.0.0.1:8186` now serves that browser build against
`mt2-p2-original-linked-r1-20260908`; existing auth/game services and prior databases
remain intact. `.local/mobs/full-world-browser-r2/report.json` recorded 50 successful
checks and no browser engine errors, but the overall scenario did not pass. Both
actual exports received identical 2,835 ordinary mob IDs across all 44 species,
rendered each other, walked the guard route, and exercised private dialogue, close,
reopen and WASD cleanup. Reviewed browser town and guard captures. The new optional
`--mob-catalog` assertion rejects duplicate IDs, unknown species and incomplete
population (also replayed against retained exported snapshots).

Preserved failures: r1 stopped on the NPC helper's unrelated six-dog assumption,
now removed. r2 subsequently stopped at the legacy `--actors` test, which expects
a rendered fixture dog from town and its old asset path. Original mobs are outside
town view range; this needs a dedicated field route, not an altered spawn. r3 tried
the account/lifecycle scenario without those fixture flags but registration hit
the normal signup rate limit; no auth limits were changed or bypassed.

One initial instrumented browser snapshot reported 16 FPS. This is not a sustained
performance measurement and the large debug snapshot may contribute; performance
is not qualified. Next: field rendering/combat and performance investigation, then
remaining exported lifecycle checks after cooldown and public deployment. No public
endpoint change. Acceptance scope/artifact hashes:
`.local/mobs/full-world-export-r1/acceptance.json`.

## Nearby PVE presentation for the full population — 2026-09-08

The previous client instantiated every subscribed mob before hiding actors outside
loaded terrain. Main now selects nearby PVE rows before creating actors, using the
original 5,500 cm approximate view distance and loaded-terrain readiness. A periodic
250 ms refresh admits/removes actors as the player moves even without mob updates.
Full subscribed state remains available; this does not reduce network subscription
scope or server simulation cost. Training fixtures retain their existing behavior.

`.local/mobs/visibility-main-r1/report.json`: 41 focused native Main checks pass,
including a 2,800-row controlled population, movement across the view boundary,
terrain unload, current-life re-entry and existing projectile presentation. Reviewed
301 screenshot. Scoped lint and real Godot parsing pass; the test-local preload
variable was subsequently renamed for lint with no runtime logic change. Connected
editor, rendered live Yongan and browser performance qualification remain pending.

## Original Yongan population linked and subscribed — 2026-09-08

`MT2_ORIGINAL_POPULATION` now links the 945 original regeneration entries into a
normal Yongan module using the selected 44-species mob package. The shared offline/
build compiler verifies inventory hash and lifecycle policy, and rejects species
missing from the compiled mob package. Authored ordinary spawns are replaced; the
practice dummy remains independent. Existing allocation and regeneration reducers
own all spawned state. This remains application protocol 24 with unchanged bindings.

Frozen module and evidence: `.local/mobs/original-linked-r1/acceptance.json`.
New database `mt2-p2-original-linked-r1-20260908` initialized 2,835 ordinary mobs
across all 44 species. Both authenticated clients received that population, moved
with remote updates, rejected an unknown target and verified disconnect/reconnect;
22 checks passed. Two focused build-package tests and strict selected Yongan library
Clippy passed. An initial anonymous SQL count was denied by the normal auth boundary;
evidence comes from authenticated client subscriptions, without weakening auth.

No public deployment changed. Full-population rendered Main/browser performance,
long-running population behavior, database restart and all-species combat still
need qualification. The next implementation step is rendered full-world integration
and export, followed by the public update once the integrated slice is qualified.

## Client mob/projectile package installer — 2026-09-08

`tools/install_mob_content.py` now installs hash-verified, allowlisted converted
presentation resources with receipts and preserves existing different/unowned
content. Matching repeated installs validate image/model bytes and required import
settings while tolerating Godot-generated texture metadata. New installations stage
both directories before renaming; an ordinary rename failure rolls back completed
renames. Different-package upgrades still require isolated client staging.

The working client now contains 44 mob definitions sharing 19 GLBs (20 mob files
including the manifest), plus 28 projectile package files. The installed gameplay
hash is `4edc30856279fa12c9d1b723e8557e6140d37600e9a3f2adba9ebbca2d18a78a`.
It requires a matching protocol-24 server. No public deployment changed.

Evidence: `.local/mobs/installed-main-r1/report.json`: 31 controlled Main-scene
checks passed through the actual installer and normal loader. The reviewed archer
capture shows the textured mob, target and in-flight arrow. A post-import repeat
initially rejected Godot-generated sidecar metadata; the installer was corrected,
and repeat installation against that same imported project now passes. Four focused
Python tests and scoped lint pass, including rejection of changed import policy.
This is native controlled-row rendering, not live Main multiplayer, browser export,
connected-editor inspection or full original population acceptance. Next: link the
original Yongan regeneration inventory and qualify the resulting populated world.

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

## Regeneration catalog integration — 2026-09-08

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

## Passive retaliation qualification — 2026-09-08

Dedicated live passive retaliation and higher-threat switching now pass 42
checks in `.local/mobs/passive-runtime-r1/acceptance.json`, database
`mt2-p2-passive-runtime-r1-20260908`. Two real accounts use ordinary unarmed
attacks: the passive dog ignores proximity, retaliates, switches to the higher
threat while both players live, and stops attacking after that victim disconnects.
This training-only fixture is explicitly selected at build time and rejected for
Yongan builds. It does not install the original population or qualify restart,
party behavior or wandering. See `docs/development.md` for the replay command.

## Public progress deployment — 2026-09-08

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

## P6: all-class abilities requested; training target delivered locally

The requested acceptance target remains **all 44 playable abilities**, with
reusable shared handlers and customizable definitions. All four classes have
basic combat, but Sword Spin is still the only live ability. Full skill mechanics,
specialization/equipment prerequisites, UI and multiplayer qualification remain
unfinished; the converted full-class candidate is not a playable release.

The already installed Blender-authored training dummy was rechecked using the
installed package: `dummy-request-recheck-r3` under `.local/p6-class-skills`
passes **16 native Godot checks**, and its rendered model was inspected. The
earlier attempts retain the missing-directory and sandbox socket diagnostics.
See [training dummy](../training-dummy.md) for customization and existing live
evidence. No server or public deployment changed in this recheck.

### Original wildlife definitions in progress

Final evidence: `.local/mobs/aggro-runtime-r2/acceptance.json`, frozen module and
`multiplayer.json`, database `mt2-p2-aggro-runtime-r2-20260908`. All 108 two-account
checks pass, including a closer nonattacking observer not stealing the next attack
in either subscription, XP rewards, death/respawn and disconnect/reconnect.
All-target Rust tests (152 library tests) and full `tools/dev.py lint` pass.
The r1 protocol fixture passes six checks rejecting 19 and accepting 20; candidate
Rust table fixture passes 11 checks including three aggressive species out of 44.
Dedicated live higher-threat switching and passive retaliation tests remain next.

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

NPC ranged/magic scheduling now follows the original synchronous `Attack` ->
`Shoot` call. Trusted ranged/magic actions require zero melee hit-window offsets;
normal melee actions retain their existing bounded window. Simulation publishes
the accepted action and immediately consumes/resolves its captured hit in the
same transaction. Existing target identity/life, health, range and collision
validation still applies. Client projectile events never authorize damage and
flight travel time does not delay this original NPC damage path.
Tests cover both ranged/magic registry dispatch, malformed melee-window rejection
and single consumption at acceptance with no later tick replay. All-target tests
pass (143 library tests plus other suites), as does strict all-feature Clippy;
evidence: `.local/mobs/immediate-dispatch-r1`. No ranged/magic
mob is installed yet, so live multiplayer acceptance for this branch is pending.
Original population registry generation, canonical resistance adapters and original
AI/distance policies still need integration before release qualification.

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
finalizer; the installed policy keeps them at zero. All-target Rust tests and
strict all-feature Clippy pass; evidence is `.local/mobs/damage-dispatch-r1`
(141 library tests plus the builder/generated-definition/example suites).
No server was republished.

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
server or public deployment changed. Full `tools/dev.py lint` passes after a
scoped dead-code allowance on the NPC diagnostic’s shared placement module: this
example uses Area only; the population example exercises the group API. Next: authoritative original magic/ranged
combat and live population integration, followed by exported multiplayer QA.

Portable projectile package checkpoint: `build_projectile_catalog.py` now
assembles the converted dependencies and `projectile_catalog.gd` loads them through
Godot ResourceLoader. `projectile-package-r2/r3` are byte-identical catalogs with
four flights and 14 resource files. The initial import changed one particle
texture; generated import sidecars now preserve exact decoded pixels.
`projectile-package-render-r3` passes 145 native checks, including 12 texture
RGBA hashes, malformed-load rejection and the four flight lifecycles. Three
Python packager tests and scoped lint pass. The package is not installed;
exported/browser QA and live projectile damage remain pending; Main hookup is
covered by the newer checkpoint above.

World projectile lifecycle checkpoint: `world_projectiles.gd` resolves the exact
protocol-19 target identity/life, creates the shared particle/mesh flights and
consumes each source event once. Lost/replaced targets become fixed positions
without reacquisition, following the original target-object lifecycle. Source
removal preserves existing flights; world disconnect removes them all.
`projectile-world-r2` passes 125 native checks with 16 hashed captures; paired-effect
and arrow captures were reviewed. Scoped lint passes. This uses injected resources
and controlled replicas. It does not establish main-scene loading, live launch
signals, exported clients, original target-center parity or server damage.

Protocol 19 attack-target checkpoint: public Monster rows now capture the accepted
character identity and life sequence. That snapshot survives private hit
consumption and clears with idle/movement, death/new life and recovery. Bindings
were generated from the actual new database (schema SHA-256
`0e20635c4f614a884e4d08c2eba09d2f19c6e027d5eb5a96fe5567c1c480234a`).
The server passes 138 Rust tests and strict library Clippy. The isolated
`attack-target-protocol-r1` gate passes six actual Godot checks, including
rejection of protocol 18 and acceptance of 19.

`.local/mobs/attack-target-training-r1/multiplayer.json` passes 104 checks with
two authenticated clients, including target/life values in both subscriptions,
death clearing, movement, damage, stale-target rejection, disconnect and reentry.
The first attempt stopped on test formatting; the next incorrectly used a Yongan
module for the single-dog training scenario. Neither failure is treated as a
gameplay pass. The final run used fresh database
`mt2-p2-attack-target-training-r1-20260908` and frozen training `module.wasm`.
A separate Yongan module remains in `.local/mobs/attack-target-r1/module.wasm`.
These are disposable test deployments; the served local protocol-18 builds and
public endpoint were not replaced. Projectile creation/damage and population
installation remain unfinished.

Current presentation checkpoint (supersedes the pending-rendering statements in
the historical checkpoints below): commit `fcfea47` added the opaque-target arrow
material and connected all four selected flights to particle/mesh attachments,
trails and impacts. `arrow-material-r4` passes 527 native checks and
`projectile-render-r3` passes 61, with reviewed captures. Original-client blend
parity and browser/export qualification are not established.

The next actor integration publishes all 26 original launch declarations on their
motions. Shared actor presentation emits each once at its source timestamp and
resolves the original model-space bone offset; late joins skip old launches and
resync does not duplicate them. The full `population-launch-r2` native gallery
passes 1,440 checks across 44 definitions and 78 attacks. Eleven focused Python
tests and scoped lint pass. This uses controlled rows, not live subscriptions.
See [launch events](../mobs.md#mob-motion-launch-events) for source semantics and
long-frame completion coverage. Next connect effect creation and publish
server-owned target state, then implement original MAGIC/RANGE damage and live
population integration. No additional mob, skill or projectile is deployed.

Projectile arrow checkpoint: the selected original `arrow_01.mse`/MDE/TGA now
convert through a reusable mesh-effect command. Export auditing supports sparse
morph data, source frame/geometry counts and explicit offsets; both existing
click-effect GLBs pass its regression audit. The first arrow audit's sparse-accessor
failure is retained, followed by successful `arrow-mesh-r2` conversion.
`arrow-native-r1` passes its native Godot frame/weight/duration assertions and the
textured model was inspected. Sixteen Python tests and Python lint pass. The
original 3/8 blend mode, flight attachment, seven particle-based effect scripts and
live projectile combat remain pending; the model is not installed or deployed.

Flight metadata checkpoint: `discover_projectiles.py` resolves the exact four MSF
definitions used by the 26 White Oath launches, with five attachments and eight
MSE dependencies. Pinned source hashes and loader defaults are recorded; no MSE
conversion or runtime rendering is claimed. The source's negative trail dimensions
are retained as an issue, with its negative-lifetime immediate-expiry behavior
recorded from `FlyTrace::UpdateNewPosition` rather than repaired with invented values.
Three parser tests and Python lint pass; `projectile-sources-r5/r6` are identical
offline inventories. Evidence: `.local/mobs/projectile-source-acceptance-r1.json`.
Flight/effect rendering and authoritative projectile attacks remain pending.

Full gameplay linker checkpoint: all 44 definitions now compile with 78 attacks
(52 melee, 26 projectile). Type-6 source launch declarations retain identity,
timing, source position, attachment and MSF effect reference separately from melee
windows. Delivery/damage kinds preserve the original MAGIC dispatch; visual launch
time is not treated as damage authorization. Unknown/duplicate events and mismatched
dispatch reject. Runtime requirements remain explicit in the catalog and receipt.

`population-gameplay-r2` binds the full catalog to the converted models. The old
five-species gameplay records compare identically after removing new descriptive
fields. Twenty-eight Python tests and Python lint pass; evidence is
`.local/mobs/projectile-linker-acceptance-r1.json`. The shared projectile renderer,
MSF asset import, original magic/ranged damage and transactional live population
integration remain pending. No new enemy or ability was deployed.

Group placement checkpoint: the shared server range sampler now supports original
leader-first group chains, independent offsets, failed-leader abort and skipped
followers. Derived rectangles may cross map edges while individual positions still
require terrain validation. Existing NPC placement is unchanged; the pure Rust
module is exposed for reuse without introducing a client-callable action.

The `population_placement` developer command samples all original Yongan group
selectors against baked server collision. Seed 42 places 2,853 members, seed 43
places 2,843; both place all 945 units with no failed followers and seed 42 covers
all 44 definitions. Repeated seed 42 output is identical. Seven focused sampler
tests and scoped strict Clippy pass. Evidence:
`.local/mobs/population-placement-acceptance-r1.json`. This uses the current shared
movement footprint, not per-species collision radii. No live spawning, rendered
world inspection, deployment or multiplayer qualification is claimed; transactional
database integration of placement and regeneration remains unfinished.

Regeneration restoration checkpoint: the scheduler now validates and restores
storage-neutral snapshots without resetting deadlines or retired owner counters.
The offline tool adds new-file checkpoint creation and a separate-process resume
path tied to the inventory hash and entry identities. All 945 entries restore to
the same 4,981-member stress result as uninterrupted execution. Five Rust tests,
eight process-level checks and scoped strict Clippy pass. Negative checks cover
overwrite, wrong inventory/entry, invalid deadlines/owners, regressed allocation
counters and cross-entry owner reuse. Evidence:
`.local/mobs/regeneration-restore-acceptance-r1.json`. SpacetimeDB persistence,
transactional spawn/cleanup callbacks and a real server restart test remain pending.

Regeneration core checkpoint: `server/src/regeneration.rs` now implements bounded
entry refill planning, first-tick jitter, fixed subsequent intervals, failed-spawn
retry and exact owner destruction. Monotonically allocated owner tokens reject
reuse; stale destruction cannot release a replacement life. The core preserves
the previous state when planning fails. Storage/spawn callbacks still need to be
integrated transactionally with SpacetimeDB and combat destruction.

The new `regeneration_stress` example exercises all 945 audited entries with
largest-group selection and successful placements. It confirms 2,963 initial
members can become 4,981 after all leaders are replaced while 2,018 followers
survive. Three Rust lifecycle tests and scoped strict Clippy pass; tampered
inventory is rejected. Final evidence is
`.local/mobs/regeneration-core-acceptance-r1.json` and `regeneration-stress-r2.json`.
This is offline lifecycle evidence, not map placement or live multiplayer proof.

Regeneration contract checkpoint: the population compiler now records the
reviewed overworld scheduling, group ownership and chained placement rules in
`runtime_policy`. It fixes zero-interval entries incorrectly contributing to the
initial member bound; they are disabled but retain their dependency metadata.
Source evidence adds `char.cpp` because group capacity is released on destruction
of the owning leader, rather than on follower death or immediately on lethal damage.
The regenerated `yongan-runtime-policy-r1/r2` inventories are identical and retain
945 entries, 54 groups, 44 definitions and the 2,963 initial member upper bound.
Twenty-seven focused Python tests and Python lint pass. This is the input contract
for pending server regeneration integration, not a change to live spawning.

Full selected asset conversion checkpoint: `population-converted-r3` now covers
**44 definitions using 19 GLBs and 271 unique clips** (628 per-definition motion
references). Identical inputs share files with explicit owner and action mappings;
different appearances remain separate. Model bytes fall from 56,133,272 without
sharing to 24,845,328. `population-actors-r1` passes **2,818 native Godot checks**
across all 44 definitions. Eight four-angle White Oath captures were inspected,
covering all seven new model types and the General/Commander alias.

The first conversion failed on unregistered motion names; the second exposed an
unused file-level Archer mesh with no model skeleton binding. The importer now
follows pinned motion registration and model mesh membership instead of assigning
invented actions or bones. Reports retain 40 ignored registrations and 26 deferred
projectile events (type 6). All 19 selected models pass binding validation.
Twenty-four mob, ten NPC and five binding tests pass, as does Python lint.
Evidence: `.local/mobs/population-conversion-acceptance-r1.json`.

This completes conversion of the selected population assets, not their gameplay.
Original group lifecycle, MAGIC/projectile behavior, catalog gates, live spawning
and exported two-client qualification are still required. The served build and
public endpoint are unchanged. Godot QA used isolated processes, not editor MCP.

Map selection and skin-variant checkpoint: `build_population_profile.py` derives
the checked-in `yongan-population.json` from the audited source dependency closure,
preserving existing actor IDs. Discovery resolves **44 definitions, 12 base GR2
models and 19 race scripts**. All **945 original entries** are now covered at the
declared-definition level. Repeated offline inventories in `population-assets-r3`
and `r4` are identical after the selected missing metadata was fetched.

The importer now preserves default ShapeData model/texture substitutions and
applies exact material-bound remaps. Blue Wolf 104, Red Wild Boar 109 and Black
Bear 112 were converted in background Blender; `skin-actors-r2` passes **179
native Godot checks**, and all three four-angle captures were inspected. The
gallery's cropped Bear side views were corrected by fitting the bounds diagonal.
Twenty Python tests and Python/GDScript lint pass. Evidence is in
`.local/mobs/population-profile-acceptance-r1.json`.

This remains source/asset preparation. Fourteen White Oath definitions use the
original `MAGIC` battle type, which is not supported by the physical handler.
Not all 44 appearances are converted or packaged; model reuse, group lifecycle,
combat handlers, live catalog gates and real population/export qualification
remain unfinished. No served endpoint changed.

Original population dependency checkpoint: inspection showed Yongan uses group
selectors rather than direct mob IDs, so compiling species-only respawn defaults
would preserve the wrong world lifecycle. `tools/discover_mob_population.py` now
imports the dependency structure from pinned committed source blobs: **945
entries, 10 selectors, 54 groups and 44 monster definitions** across 12 source
model folders. The five selected definitions cover no complete original entry.
The 39 missing definition IDs and source names/folders are explicit in the output.

The importer preserves leader/member ordering, source rectangles/directions and
per-entry intervals. It distinguishes source-declared selector weights from the
pinned loader's effective unit weights and records the ignored percentage column.
The **2,963 initial member upper bound** is not a live population cap; original
regeneration is attached to group masters. This evidence changes the integration
plan: expand the bounded map dependency set and implement group lifecycle rather
than spawning a subset with species-wide respawn behavior.

`.local/mobs/yongan-population-r3` and `r4` are byte-identical. Five new population
tests plus ten existing mob tests and Python lint pass; evidence is recorded in
`population-discovery-acceptance-r1.json`. No assets were expanded, no population
was installed, and served builds remain unchanged. Full server registry and live
client catalog integration remain unfinished.

Wildlife presentation checkpoint: the candidate builder emits public actor/model
metadata alongside gameplay. The real PvE renderer uses exact action IDs and the
authoritative interval for slow/normal playback and late seeking, holds completed
actions and resets on idle/new life. Player attack-speed validation is unchanged.
Original death registration names map to the renderer's canonical actions without
changing IDs or clips.

`.local/mobs/gameplay-presentation-r3` passes **125 rendered Godot checks** for
five species/nine attacks, recovery, death/respawn and targeting. Five textured
model captures were inspected. `playback-regression-r1` passes **116 existing
headless actor checks**; ten Python tests and Python/GDScript lint pass. The first
two native runs exposed the missing resource-directory entry and death-action
mapping; both were fixed before the third run. `playback-acceptance-r1.json`
records the reports and reviewed images.

The wildlife catalog is merged only in the isolated test fixture, using controlled
state rows. This is not multiplayer subscription, browser or export evidence.
No Godot MCP was exposed, so no connected-editor claim is made. Live catalog
installation/hash gating, full server definitions and original population/AI
remain pending; served builds are unchanged.

Weighted action runtime checkpoint: mob definitions now expose bounded weighted
attack lists. The authoritative start chooses once and retains the chosen ID and
timings; hit resolution looks up that species' accepted action. Invalid totals,
duplicates, unsupported action features and invalid windows reject. The default
dog still has its existing single 100-weight attack, preserving live balance and
RNG behavior until the matching content catalog is installed.

All **164 Rust tests**, strict Rust lint and **113 actual two-client checks** pass.
The Rust selection test covers every roll of a two-variant fixture; the live run
uses the existing single-action dog on `mt2-p2-mob-actions-qa-r1-20260908`.
Reports are `.local/mobs/weighted-actions-live-r1.json` and
`weighted-actions-acceptance-r1.json`. Actual module schema matches the committed
protocol-18 bindings. No client changes, new exports or served endpoint update
occurred. Multi-variant catalog integration and client playback remain next.

The converted wildlife now has an offline gameplay-catalog compiler:
`tools/build_mob_catalog.py` links five species and all nine weighted attack
variants to the exact Blender report, preserving hit samples, distinct defending
spheres, movement accumulation and reaction durations. It separates original
integer-rounded server cadence from precise client playback timestamps. Full
source stats/AI/regen/drop records remain attached, without implying those
mechanics are implemented. The reviewed timing rules and server revision are
recorded in the output.

`.local/mobs/wildlife-gameplay-r3` and `r4` are byte-identical; catalog SHA-256 is
`3e111b2a60a424f18fe35dad60c279375d698b09ef2682b7dbdabeed40dd85dd`.
Six compiler tests, three source-parser tests and Python lint pass. The actual
CLI rejects altered converted metadata before creating an output directory.
Evidence is in `.local/mobs/gameplay-catalog-acceptance-r1.json`. This is an
offline candidate only: weighted runtime selection, client catalog/playback,
original spawns/passive AI and reward tables remain to integrate. No new model,
server publication or exported build is claimed by this checkpoint.

Gameplay registry consumers now use `MobDefinition` for ordinary spawning,
health/level, movement and attack timing, XP/gold, respawn, defending geometry
and GREAT-hit recovery. Simulation no longer rewrites all ordinary levels to the
dog's level; inconsistent persisted stats and presentation reject. The default
registry still contains the existing dog, with the passive dummy separate.
No new wildlife is live, and original passive AI and item drop tables remain
unfinished.

This follow-up passes **162 Rust tests**, strict Rust lint and **113 authenticated
two-client checks** on `mt2-p2-mob-runtime-qa-r1-20260908`. Evidence is in
`.local/mobs/runtime-registry-live-r1.json` and `runtime-registry-acceptance-r1.json`.
The actual published schema matches committed protocol-18 bindings. The first
lint run found an unused import left by the refactor; it was removed and the
module rebuilt before live QA. Local served exports and the public build are
unchanged. Next is compiling the converted species into complete gameplay records
and connecting the matching client catalog and original population metadata.

Physical registry checkpoint: ordinary damage now selects attacker/defender
stats through a trusted vnum/actor registry. The default registry remains the dog;
the candidate compiler emits all five wildlife definitions and preserves the
Boar's five-percent normal critical chance. Unsupported nonzero modifiers reject.
Normal critical doubling is checked for overflow; critical effects and skill
critical rules remain pending. Runtime arithmetic tests exercise distinct Wolf
stats and resistance, while compiler tests cover malformed/unlinked definitions.
The candidate is not installed until actions, AI, health, rewards and client
content checks are integrated together.

The checkpoint passes 161 Rust tests, strict Rust lint and **113 actual two-client
checks** in `.local/mobs/physical-registry-live-r1.json`, using isolated database
`mt2-p2-mob-physical-qa-r1-20260908`. All staged QA sources remained unchanged.
This qualifies regression behavior for existing dogs, not new wildlife gameplay.
The local served area-NPC build and public endpoint remain unchanged.

Spawn identity checkpoint: the shared population parser now takes an explicit
registry and retains each placement's `definition_vnum`. Generated ordinary and
training-target spawn records carry that ID through creation, and physical combat
checks the persisted actor against its compiled spawn. The current build still
registers only the existing ordinary dog and separate dummy; additional wildlife
stats, attacks, AI and rewards remain unintegrated.

`make server-test` passes 157 Rust tests, including mixed-definition parsing and
spawn/actor mismatch rejection. Rust and GDScript lint pass. The isolated module
`.local/mobs/spawn-definition-module-r1.wasm` passes **113 two-client checks** in
`spawn-definition-live-r2.json`, on `mt2-p2-mob-registry-qa-r2-20260908`. Coverage
includes exact authored homes, movement, target rejection, physical damage,
kill/reward handling, respawn, reconnect and no reward replay. The actual published
schema matches the committed protocol-18 bindings exactly.

The first live run failed six obsolete unscaled-duration assertions; the shared
combo fixture now checks ceiling-rounded duration using the subscribed action's
captured speed. The corrected run used a fresh database with the unchanged server
module. Both runs and their databases are preserved. No timing rule was weakened,
no server speed changed, and no new mob or served build was deployed by this slice.

Conversion follow-up: `tools/import_mob_content.py` reuses the pinned Blender
actor converter for the five selected wildlife definitions. The candidate
`.local/mobs/wildlife-converted-r1` contains five models, 68 reachable motions and
zero deferred motion events. `.local/mobs/wildlife-actors-r1` passes 304 native
Godot checks. Wolf, Wild Boar, Bear and Tiger were visually inspected from four
angles; front orientation is -Z. The original dog has one unreachable second
back-damage entry after a 100-weight registration, explaining 69 source entries
versus 68 converted clips. No source weights were replaced.

The original dog model has a shared ambient/diffuse texture. The material
resolver now accepts that exact case while rejecting a separate ambient map;
the regression and Python lint pass. The failed initial conversion is retained.
No mob gameplay or served build changed. The next step remains the per-definition
runtime registry and two-client combat qualification.

The [mob source pipeline](../mobs.md) selects Wild Dog, Wolf, Wild Boar, Bear and
Tiger using explicit vnums and pinned server/client metadata. It preserves stats,
rewards, resistances, enchantments, flags and special fields without assigning
unimplemented mechanics to a default physical handler. Original blank skill slots
remain null. It resolves model paths, collision metadata and 69 motion-list entries.

`.local/mobs/yongan-wildlife-r3` reproduces five definitions offline, with hashed
inputs and source provenance. Three regression tests and Python lint pass.
The first offline attempt lacked Wolf metadata; the selected metadata was fetched
from the pinned archive and the complete command then passed offline. Original
Wild Dog HP is 126, distinct from the current 100-HP development fixture. Runtime
integration must preserve that distinction explicitly. Assets have not been
converted by this slice; no extra mob is deployed. The next step is conversion
and a shared runtime registry replacing ordinary-mob lookups fixed to vnum 101.


### Area NPC exports accepted locally

The protocol-18 build now serves at `http://127.0.0.1:8186`, using the preserved
isolated `mt2-p2-npc-areas-qa-r1-20260908` database. The old town database and
exports remain available on disk. The public endpoint is unchanged.

Actual exports `.local/npcs/exports/area-web-r1` and `area-linux-r1` pass package
audits: 1,208 Web / 2,011 Linux paths, 38 NPC models and 239 exact UI images each.
The server module remains `.local/npcs/area-module-r2.wasm`. The local proxy
was switched only after both exports passed their audits.

`.local/npcs/area-browser-r2/report.json` passes **115 actual Chrome/Linux checks**
with no browser engine errors. The new `yongan-areas-route.json` retains source
rectangles rather than sampled coordinates: both exports must show all six area
NPCs inside their bounds with identical positions/headings, original names and
playing idle animations. The 23 fixed entry NPCs, guard approach/private dialogue,
Close/Escape/WASD, dummy held-Space combat, Skills input, character switching,
disconnect/reconnect/reload and logout/login also pass. The browser dialogue
capture was visually inspected. This does not visit every remote NPC with both
cameras; the separate native map fixture inspected all six area residents.

Two focused browser-verifier tests pass and Python lint passes. The first launch
used system Python without Playwright and stopped before creating clients;
`area-browser-r1.log` is retained. Running with `.local/venv-dev/bin/python`
resolved that environment error. No game code or auth limits were changed.
The accepted hashes and limitations are recorded in `area-deployment-r1.json`.
No server-process restart, Windows execution or public deployment is claimed.

### Training dummy customization validation

The authored dummy is already present in the accepted local town build. A fresh
background Blender rebuild, `.local/p6-class-skills/dummy-profile-build-r1`,
reproduces its installed GLB hash exactly and retains the editable `.blend`.
`dummy-profile-actors-r1` passes 16 native Godot checks; the rendered model was
inspected. Blender MCP remains unreachable on port 9876.

`tools/build_training_dummy.py --check-profile` validates custom data without
launching Blender. Authoring and server compilation now reject typos, duplicate
map/placement IDs, malformed colors and out-of-range dimensions in addition to
gameplay bounds. Three Python and three Rust focused tests pass. No gameplay
content changed, and this is not a new export or multiplayer qualification.
The requested 44 playable abilities remain incomplete; existing conversion and
formula evidence must not be described as runtime skill integration.

The separate protocol-18 area-NPC changes now have generated bindings, live
subscription QA and native map evidence as recorded below. The matching exports
are now accepted locally as recorded above.

### Original area-spawn townspeople: conversion and source contract

Placement follow-up: `server/src/npc_placement.rs` implements the shared inclusive
centimetre sampler, sixteen terrain attempts, post-success heading selection and
original-to-Godot heading conversion. Malformed rectangles, out-of-range RNG values
and nonfinite heights reject. Exhaustion returns no placement, never a center.
The sampler is now connected to the game module's public `npc_spawn` table;
private retry timestamps retain the source interval after failed attempts.

`tools/test_npc_placements.py` qualifies converted definitions using real Yongan
terrain. `.local/npcs/area-sampling-r2/report.json` passes **600 placements across
100 seeds**, bound to actual terrain bytes, source files, Cargo lock and the binary.
The Rust example suite passes 18 tests, including four sampler regressions and
shared terrain/movement tests. This earlier offline evidence is complemented by
the runtime qualification below.

Protocol 18 / catalog schema 3 adds persistent area rows and Godot subscriptions.
The installed candidate contains 38 definitions, 41 fixed placements and six areas.
The module `.local/npcs/area-module-r2.wasm` is published to the isolated database
`mt2-p2-npc-areas-qa-r1-20260908`; the served development database is preserved.
Bindings were generated from that module and validated in isolated Godot.

`.local/npcs/area-live-r1.json` and `area-live-r2.json` each pass 51 actual
authenticated two-client checks. The latter additionally captures public spawn
rows for scene QA. Coverage includes identical positions/headings, mutual movement,
rejected forged interactions, disconnect presence removal, repeated reconnects
and unchanged rows after both clients leave. No server-process restart was tested.

`area-world-r1/report.json` passes 122 native Main/map checks with those captured
rows and an explicit offline connection spy. All six area NPC screenshots were
inspected, including Ah-Yu's baby and Yonah's pot. Row removal/restoration, original
names, position/heading, idle playback and picking-only collision are covered.
Python NPC tests pass 16 cases; Rust NPC compiler tests pass three cases;
`make server-test` passes. Lint passes after a Python formatting correction.
The formatter-only tool change followed the rendered run; gameplay inputs did
not change. Matching exports and local browser QA subsequently passed as recorded
above; the public endpoint remains unchanged.

`content/profiles/yongan-area-npcs.json` selects six `NOMOVE` NPCs: Aranyo, Ah-Yu,
Yonah, Mirine, Uriel and Baek-Go. Their original regeneration rectangles are
preserved as inclusive centimetre bounds with 16 attempts and independent random
integer headings (0..360), following pinned `regen.cpp` / `char_manager.cpp`.
The explicit area policy omits fixed X/Z coordinates. The initial point-only
builder rejected it; schema 3 now preserves these areas for runtime placement.
The non-stationary Shabby Pedestrian remains outside this profile.

`.local/npcs/yongan-area-r3` converts all six models and 26 original motions;
`yongan-area-qa-r1` passes **144 rendered Godot checks**. Ah-Yu, Yonah and Mirine
captures were visually inspected. Fifteen NPC tests, four GR2 tests and repository
lint pass. `area-point-rejection-r1.log` proves the real catalog command rejects
area data before creating an output package.

The first conversion exposed the potter's unused empty material slot, now accepted
only with topology proof; used textureless materials remain rejected. The next
attempt exposed Mirine's embedded run translation without MSA accumulation.
Stationary NPC conversion now preserves and flags that unused source clip while
retaining the playable-character and double-travel checks. Failed logs remain.
That initial conversion slice did not deploy NPCs. Its runtime integration and
local deployment are now qualified above.

### Remaining original point NPCs: candidate package

Live follow-up: the expanded package now serves at `http://127.0.0.1:8186` on the
preserved `mt2-p2-town-dev-r1-20260908` database. The published snapshot is
`.local/npcs/points-module-r1.wasm`; matching exports are `exports/points-web-r1`
and `exports/points-linux-r1`. Actual PCK audits cover all 32 NPC models, no clips
for the two static landmarks, exact UI pixels, and 1,176 Web / 1,979 Linux paths.
`points-browser-r2/report.json` passes **114 actual two-client checks**, including
23 entry NPCs, private guard dialogue, movement, dummy combat and full account
rejoin. Browser errors are empty; the dialogue capture was visually inspected.
`make server-test` passes against the installed schema-2 package.

The first exported run passed 111 checks but failed the final rejoin after an
abnormal native WebSocket closure. No content mismatch or browser error occurred;
the same exports/scenario passed on repeat. The cause of that initial transport
drop is not established. Both reports and exact build hashes are retained in
`.local/npcs/points-live-acceptance.json`. The exported route does not visit every
remote placement. Public/Windows qualification and connected-editor inspection
remain unproven. Prior packages, database state and source assets are preserved;
only completed disposable QA project copies were pruned for disk space.

The new `yongan-season1-npcs` profile selects eight NPCs, including six animated
townspeople, Weol Memorial and Nameless Flowers. Conversion in
`.local/npcs/yongan-season1-r3` preserves all 18 registered motions and exports the
two source-static landmarks without fabricated idle clips. Explicit `#` race
folders and GR2-local texture bindings now follow pinned client behavior.
NPC catalog schema 2 makes static/animated presentation explicit; legacy schema 1
remains supported. The candidate package is
`.local/npcs/yongan-complete-points-r1/runtime` (32 definitions, 41 placements).

`.local/npcs/yongan-season1-qa-r2` passes 137 rendered gallery checks. Chaegirab,
memorial and flower captures were inspected; bounds-based framing fixes cropped
landmark previews. The real Main/map test in
`.local/npcs/yongan-complete-points-world-r2` passes 53 checks, including static
placement, labels and picking-only collision on both remote landmark chunks.
Its connection is simulated. The follow-up
`.local/npcs/yongan-complete-points-world-r3` also passes 53 checks, removes the
prior guard dialogue overlay and frames landmark bounds. Both unobstructed map
captures were visually inspected.
Twelve focused Python tests, `make server-test` and repository lint pass.

The first conversion attempts exposed model-local texture names and pack-prefix
normalization; logs are retained. The first map run exposed strict Array membership
for JSON float versions, fixed by numeric version comparisons. Reproducible map-QA
project copies were pruned after terminal runs to recover disk space; reports,
logs, source assets, databases and served builds are preserved.
The later local integration is recorded above. Remaining
random-area NPCs, shops, quests, full abilities and foliage are still unfinished.

### Skill mechanic metadata and dummy recheck

The full-class candidate Rust generator previously omitted damage attributes,
primary/secondary affect IDs, learning limits and rank powers. It now preserves
these fields with bounded validation, so later shared handlers can distinguish
magic/ranged/melee damage and apply the correct source effects. This does not
activate the other 43 abilities; the live catalog still supports Sword Spin only.
The new qualification uses compiled rank powers and checks metadata against the
candidate input. `.local/p6-class-skills/formulas-metadata-r2/report.json` passes
21,120 formula evaluations and 221 metadata assertions, with hashes of all inputs.
Three compiler tests cover valid effects and rejection of malformed mechanic and
rank metadata. Repository lint passes (`metadata-lint-r2.log`), and all 227 Python
tool tests pass (`metadata-tools-r2.log`). The first tool-suite attempt could not
bind sandboxed loopback sockets; the authorized local-socket rerun passes.

The existing Blender-authored dummy passes a fresh 16-check native Godot run in
`.local/p6-class-skills/dummy-actors-current-r1`; its rendered model was inspected.
No game endpoint, database or runtime content was changed in this follow-up.
The unrelated explicit-registration/static-NPC importer work remains unfinished.

### Original town NPC population delivered locally

Live follow-up: `http://127.0.0.1:8186` now serves
`mt2-p2-town-dev-r1-20260908` with `.local/npcs/town-module-r2.wasm` and matched
`exports/town-web-r2` / `exports/town-linux-r2`. The actual exported run
`.local/npcs/town-browser-r2/report.json` passes **114 checks**, without browser
engine errors. Both clients verify 21 original entry-chunk NPCs, guard dialogue,
movement, training-dummy combat and account/reconnect lifecycle. Remote fisherman
placements have not all been visited in that run. All 24 NPC definitions pass
the actual PCK audits: 1,140 Web and 1,943 Linux packaged paths, including exact
UI pixel checks. `town-live-lint-r1.log` passes all lint groups.

The first combined browser run exposed a stale prior combat target when choosing
an NPC. The normal client clear-target intent and an authoritative clear on
accepted conversation fix that transition; the failed run is retained. The
catalog is installed with its previous installation preserved, and prior databases
were not reset. Public deployment and Windows execution remain unchanged.

`content/profiles/yongan-town-npcs.json` now selects 23 original stationary NPC
definitions at 32 point placements, including merchants, eight teachers,
blacksmith, fishermen and townspeople. `.local/npcs/yongan-town-r7` converts 190
reachable original motions. Combined with the existing guard,
`yongan-town-catalog-r2/runtime` builds a 24-definition / 33-placement candidate.
The subsequent live integration is recorded above.
Shops, training interactions, NPC combat and quests remain unimplemented.

The work fixes source-driven importer issues: GR2 face material assignments now
survive replacement of Blender slots; same-image opacity maps export as alpha
masks; ordered 0–99 motion weights discard unreachable trailing registrations;
event-free animation duration follows the GR2 as the original client does.
Soon's 2-second MSA / 1.5-second GR2 mismatch remains recorded in metadata.
The bailiff's attack projectile event is explicitly deferred in the profile and
receipt, not silently treated as a working effect.

Static NPC positions now use the source's finite/in-map policy, allowing the
original fisherman on blocked terrain. Player movement and mob-home validation
retain collision checks. The same function is used by server initialization and
the offline inspector. Candidate package input and population-aware assertions
make the real map-scene runner reusable without modifying installed assets.

Evidence in `.local/npcs/`: `yongan-town-qa-r3/report.json` passes 936 native
checks and captures all 23 actors; armour merchant, blacksmith, fisherman,
teacher and alchemist screenshots were inspected. `yongan-town-world-r4/report.json`
passes 39 real Main/map lifecycle and picking checks with a simulated connection.
`town-server-r1.log` passes 146 Rust tests; `town-lint-r3.log` passes all groups.
Focused Python suites pass 9 NPC, 4 GR2 and 2 world-authoring tests.
These isolated checks are separate from the live export evidence above.
No connected-editor or public-deployment qualification is claimed for this slice.

Failed attempts are retained: source material/motion restrictions, lost secondary
material faces, incorrect idle duration expectation, blocked fisherman placement,
screenshot numeric filenames, outdated fixture content hashes, first-row-as-guard
assumption and a Godot-only void-return parser error. The final runs above pass.

### Foliage and abilities remain in progress

The continuing full-project goal includes quests, with filling the world first.
The next foliage checkpoint prepares all 14 original tree definitions and 368
Yongan placements through `tools/prepare_foliage.py`; the hash-verified receipt
is `.local/foliage-r1/inputs.json`. Original tree placement ignores object rotation
and property size overrides, unlike building placement. Two focused Python tests,
Ruff and strict C compilation pass. The offline DLL probe was rejected by
automatic approval review and has not run; explicit approval is pending.
No new foliage is rendered or deployed. See [foliage](../foliage.md).

The requested scope remains **all 44 classic abilities**, data-driven and
customizable. It is not complete: the running skill implementation remains
Warrior Sword Spin. Do not equate converted motions or compiled formulas with
playable abilities or original-game parity.

The candidate importer discovers all four classes/eight trees and converts 88
normal-grade skill motions. `.local/p6-class-skills/actors-r3/report.json` passes
625 native checks, including finite bone transforms and changing poses across
sampled times. These checks do not cover bow/dagger attachments or skill particles.
`formulas-r2/report.json` passes 21,120 evaluations of all skill/rank formula
programs. Catalog SHA-256 is
`eaacb2e1e224afd151f298b282f1e899fce9a9f4e1afc2b0f1d9c0d179aecb6b`.
The candidate accepts bounded overrides through
`content/profiles/classic-skill-tuning.json`, preserving pinned originals.
Shared server handlers, skill-tree selection, new weapon modes, timed buffs and
status effects, friendly targeting and matching UI/multiplayer acceptance remain.

The [authored training dummy](../training-dummy.md) is implemented independently
as a real combat target. Its default profile has 30,000 HP, no AI/knockback and
no rewards, with a two-second respawn. It stands near the Yongan spawn at
`(662, 580)` and has a separate Training Grounds placement. Blender generates its
original straw-and-wood model; only a 230,672-byte GLB and its manifest ship.
All three clips (idle/impact/defeat) are verified in Godot and actual exported packs.
Protocol 17 adds `WorldInfo.training_target_hash`; client/server mismatch fails
before world entry. Normal local developer permissions remain default-deny.

Evidence under `.local/p6-class-skills/`:

- `dummy-actors-r4/report.json`: 16 native presentation, picking and life checks.
- `dummy-live-r4.json`: 45 actual two-account checks on the preserved isolated
  600-HP `mt2-p2-dummy-qa-r2-20260908` fixture, including Sword Spin/melee damage,
  no rewards, anchoring, respawn, stale revisions/lives and reconnect.
- `dummy-resistance-live-r1.json`: 65 checks with a custom 600-HP/50%-resistance
  profile on `mt2-p2-dummy-resistance-r1-20260908`. A focused Rust regression
  verifies that resistance reaches the runtime calculation and halves its result.
- `dummy-browser-r4/report.json`: 82 actual Chrome/Linux checks with no browser
  engine errors; pointer-select/held-Space damage, mutual model presentation,
  K/Escape and account lifecycle on normal `mt2-p2-dummy-dev-r1-20260908`.
  The final `exports/dummy-web-r3` and `exports/dummy-linux-r3` packs pass their
  content audits: 1,018/1,821 paths, 239 exact UI images and all three dummy clips.
  The served module is `dummy-module-default-r2.wasm`, with normal permissions.
- `dummy-fan-r1.json`: 144 live Shaman/fan regression checks with practice actors
  present; dog-specific fixture queries select the intended definition.
- `python-r4.log`: 223 Python tests. `server-r4.log`: 144 Yongan Rust tests before
  the additional resistance regression; `server-r5.log` passes 145 including it.
  `server-training-r2.log`: Training Grounds
  passes after correcting an older root-motion test's hardcoded Yongan coordinate.

Failures are retained. Early dummy conversion omitted exported actions; explicit
NLA tracks fixed it. Native checks exposed the previous Wild-Dog-only presentation
branch and missing fixture screenshot expectations. Live attempts exposed a parser
issue and a test character without an equipped sword; the final fixture also waits
for and acknowledges melee actions. The resistance review found a legacy policy
that rejected nonzero resistance despite configurable data; runtime validation now
accepts bounded resistances. The UI tool tests found a default-argument capture
that ignored the temporary output root: the generator is fixed, and the accidentally
replaced local atlas PNG was restored from the validated original import. The
complete Python suite then passed. Historical dog-specific smoke queries now select
vnum 101 so an additional practice target does not change their intended fixture.
The final export's first browser run timed out waiting for world entry; the next
attempt hit the real signup rate limit. No watchdog or auth limits were relaxed.
After the signup window expired, r4 passed all 82 checks without engine errors.
The earlier timeout is retained as an unresolved intermittent observation.

The public endpoint and Windows execution are unchanged/unverified for this slice.
Blender MCP was unreachable; background Blender and isolated native/exported Godot
were used. No connected-editor claim is made. Prior databases and exports remain
stored; no database was wiped. Continue full skill gameplay integration next,
reusing the already converted package rather than repeating all motion conversion.

## Current project overview

The current local build is a playable, bounded shared-Yongan vertical slice.
Authenticated accounts can create and select characters, enter the same map,
see and move with each other, use the selected original Warrior, Sword+0, Wild
Dog, Yongan and classic-UI assets, manage the connected inventory/equipment
subset, fight and respawn through server-owned PvE, gain and allocate the
implemented progression, select an exact private target, and play the common
four-step one-hand combo with authoritative root displacement. These are
integrated slices of their catalog systems; they are not complete versions of
the original game.

Current P2 work is qualified on isolated local default-deny databases. The
protocol-9 finisher Slice D has accepted server, headless and package evidence
plus a 154-check instrumented Web/Linux gameplay run. The public route
remains the older protocol-4 `mt2-p1-v4` checkpoint; its HTTP availability was
verified, but it does not expose or qualify the local P2 progression, targeting,
combo or root-motion work.

Full P0 definition coverage and the full P1 content/motion factory remain
incomplete. The broader P3 through P10 systems are still pending. The 194
feature records across 41 systems are a scope inventory with different sizes,
dependencies and acceptance criteria, so their record counts do not support a
meaningful percentage-complete claim.

## First Warrior skill — protocol 16

At this earlier protocol-16 checkpoint, **http://127.0.0.1:8186** served
`mt2-p2-skills-dev-r1-20260908` with matched audited Web/Linux test exports.
Previous databases and auth accounts are preserved. The public endpoint is unchanged.
[Sword Spin](../skills.md) adds level-5 learning, point spending, rank upgrades,
server-owned SP/cooldown/damage, original male/female animations and icon, K/Skills
UI, persistent quickslot bindings and authorized `/skill <id> <0..20>` commands.
Administration remains default-deny in the development database; the separate QA
module bootstraps only its disposable test operator. No user account has been
newly provisioned for the developer commands.

Evidence under `.local/p5-skills/`:

- `admin-prepare-r1.json`: 15 two-account checks establish default-deny commands.
- `skills-live-r4.json`: 35 checks on `mt2-p2-skills-qa-r2-20260908` cover learning,
  points, revision/replay rejection, rank-one 56-SP cost, remote action delivery,
  rank changes, private state, cooldown preservation and reconnect.
- `skill-combat-r2.json`: 15 additional checks with those identities cover actual
  Yongan mob damage, bidirectional movement, one hit per life and post-cast return.
- `actors-r1/report.json`: 116 rendered actor checks, including both original
  Warrior skill motions at four animation times; inspected the 700 ms captures.
- `skills-ui-r2/report.json`: 13 rendered component checks; inspected the original
  icon, rank, point button and cooldown display in `skills-ui-component.png`.
- `browser-r1/report.json`: 108 actual Chrome/Linux checks, including K/Escape,
  class/held-attack regression and account lifecycle; no browser engine errors.
- `server-r5.log`: 138 Rust tests. `lint-r5.log`: all lint groups pass.
  Focused Python: 41 export tests, 8 character tests and 3 restricted-formula tests.
- `exports/web-r1` and `exports/linux-r1`: actual exports, 1,015/1,818 packaged
  paths and 239 exact UI images audited. Both contain skill catalog SHA-256
  `85a5eb2b7b28b2e4ac17c517d389d297a4ab21cd94cc8ea67d2e237069af353e`.
  Web PCK: `09c2950463ad9f4939e11ef0352773d99db06005224bdbc41d7a677833a6a1bc`.
  Linux PCK: `4a117674e9d9136c30f67eee0a6a077a240c795d56195b82989bfde49a6d5277`.

Earlier skill live runs failed test-script parsing, an incorrect expected denial
message and a test that violated the existing command rate limit. Those failures
are retained; r4 is the clean progression run on a new database. The first UI
attempt had a test identifier shadowing Godot's native Panel class; r2 passes.

This is one selected skill and interim original-art panel. Original skill particles,
external-force reaction, specialization choice, Master books/higher ranks and
other skills remain pending. The compiled English gameplay formula intentionally
uses the pinned international power table; locale differences and linear MSA-root
approximation are documented in the skill contract. Exported K/Escape and native
UI intent checks do not establish an exported mouse-driven level-5 learn/drag/cast
flow; authoritative learning/casting is covered by the separate live SDK clients.
No connected-editor MCP, Windows execution or new public gameplay qualification
was available in this session.

## Captured item attack speed — protocol 15

The local endpoint **http://127.0.0.1:8186** now serves
`mt2-p2-attack-speed-r1-20260908` with matching Web/Linux development exports.
The previous class-effects database and all auth accounts are retained. Protocol
15 adds captured attack speed to Player/Controller and the current equipment
speed to owner-private progression; trusted content is schema 8 and the item
registry is schema 2. This does not update the public protocol-4 deployment.

The compiler imports Sword+0's +22 and Fan+0's +26 `APPLY_ATT_SPEED` values.
Player speed is base 100, capped at 170; ordinary equipment produces 122/126.
Shared code scales action duration, hit windows, cooldowns, combo windows,
root-motion duration and area/camera activation using the speed captured at
acceptance. Original source times and root endpoints remain unchanged. Godot
playback/late seeking use the same rate, while idle resets to normal. Status
shows current server-owned speed and original-item tooltips show their bonuses.
Unequipping during a swing cannot retime it or bypass its cooldown.

The precise microsecond clock deliberately follows the original client's
speed/100 playback factor rather than legacy server integer-percent rounding.
Slows, buffs, other equipment applies and full original DPS parity are pending.
Ordinary-hit invulnerability, area/camera 200 ms lifetimes, mob timing and
knockback remain on their existing clocks. Source references are the pinned
client `InstanceBaseMovement.cpp`/`ActorInstanceBattle.cpp` and server
`char.cpp::GetLimitPoint`/`utils.cpp::CalculateDuration`; this is a bounded
modernized contract, not a claim of exact original-server arithmetic.

Evidence under `.local/p4-attack-speed/`:

- `shaman-r2.json`: **144 live checks**, two independent authenticated identities,
  both Shaman sexes, source speed/durations, queued/direct/duplicate combo links,
  active-swing unequip capture, current speed projection, damage/force/recovery,
  movement, private records and disconnect/reconnect. Staged sources unchanged.
- `native-fan-r1/report.json`: **87 rendered Godot checks** including 1.26 playback,
  scaled late seeking, held fan input, bone attachment and idle reset. The reviewed
  female combo-2 capture shows the original fan following its right-hand pose.
- `components-r1/report.json`: **131 component checks** for content gating, probe,
  waves, status/tooltips and protocol. `camera-speed-r1/report.json` separately
  passes **42** dispatch checks with exact 81,968 us activation for a synthetic
  100,000 us event at speed 122, unchanged duration and no replay across all eight
  real class appearances. `protocol-r2` passes **4** explicit 14→15 gate checks.
- `server-tests-r3.log`: **136 Rust checks**, including all compiled root endpoints
  and combo windows at 100/122/126/170, integer boundaries and malformed rates.
  Python: **198 checks** pass in the initial sandbox run; its 15 socket-bound
  gateway checks pass separately in `python-gateway-tests.log` with local sockets
  enabled (**213 total**). Lint passes in `lint-r2.log`.
- Both actual exports pass PCK audits: **998 Web / 1,801 Linux paths**, all 238 UI
  images, selected actors/items/effects, and exclusion of MCP, evaluators, identity
  tokens and source archives. These are authorized development probe builds.
- The first browser run stopped at an exact float comparison: the correct 1.22
  animation rate is represented by Godot as `1.2200000286`. The runner now uses
  a 1e-6 tolerance; this required no game/export change.
- `browser-r2/report.json`: **106 passed Chrome/Linux checks**, actual held-Space
  common sword chains for female Ninja and Warrior, both subscribers rendering
  1.22 playback, the Warrior camera event, mutual presence/movement, reconnect,
  reload and login/logout. Browser engine errors: none. The reviewed Warrior
  capture shows both original characters and the equipped sword on Yongan.
  This run does not repeat the separate four-minute token-refresh scenario.
- `acceptance-r1.json` binds the final changed-source hashes, module, generated
  content/bindings and accepted test/export evidence.

The installed WASM is `module-r1.wasm`, SHA-256
`075da5978d4f0455eb7e96e14107de05634f32e25d1ad7d6cc42d7f7e3a4eae3`.
Gameplay definition hash is
`6bb092453062392b807b57852071624fa6980ca3b5d61029f14457cbe914af0e`.
Web `index.pck` is 23,181,384 bytes, SHA-256
`3794031e4d639d93d582d530d2f0dd53b144b78a372e8b619b7b42cdf37dc7a8`;
Linux `MT2Spacetime.pck` is 115,376,240 bytes, SHA-256
`e0a6bdb07f1b44d14a1c26ea6f2371a33ad3c67c87f818dd3333c2bf6fd276ab`.
Godot MCP was unavailable, so connected-editor inspection remains unverified;
Windows execution and public gameplay qualification are also outside this run.

## Ordinary Sura/Shaman finisher force and mob recovery

The tested server module is installed on the existing local development database
`mt2-p2-class-effects-r1-20260908`, served at **http://127.0.0.1:8186**. Publication
used `--delete-data=never`; characters, inventory and prior databases are preserved.
Protocol 14, catalog hashes and client assets are unchanged, so the existing
Web/Linux class-effects exports remain in use. The public deployment is unchanged.

Both Sura and Shaman appearances compile their original fourth-hit GREAT/force-15
metadata into an ordinary knockback definition. Valid surviving hits use the
shared collision-clipped, one-second ease-out force with a nominal unobstructed
distance of 3.675 m. Hit revision, exact lives, range/path and invulnerability
checks gate damage and force together. A surviving reaction cancels the victim's
pending attack; a lethal hit clears force/reaction state. Ordinary non-GREAT
small pushes and attack-speed modifiers remain pending.

The live Sura test exposed a pre-existing recovery bug: a mob's next normal attack
could retain its back-knockdown action ID. Normal attack scheduling now explicitly
publishes the normal action ID. This fixes the recovery transition for shared
area and ordinary reactions alike.

Evidence in `.local/p4-ordinary-force/`:

- `sura-final.json` and `shaman-final.json`: 134 checks each, using two independent
  authenticated clients on `mt2-p2-ordinary-force-final-qa-20260908` and the exact
  published module. Four real Wild Dogs survive the four finishers. Both clients
  observe damage and reactions, and normal attacks resume after recovery. The
  scenarios also cover movement, duplicate combo rejection, item ownership/stale
  revisions and disconnect/reconnect. Staged source checks pass.
- Recorded peak displacements: Sura male 3.675293 m, Sura female 3.587072 m;
  Shaman male 3.674992 m, Shaman female 3.675206 m. Live checks allow bounded map
  displacement; the exact unobstructed endpoint and collision consumption are
  covered separately. Sura traces exercise back knockdown; Shaman traces include
  front knockdown and front stand-up. All four finish with normal attack IDs.
- `server-tests-r2.log`: 131 Rust checks pass. `training-force-tests.log`: six
  focused force checks include the training-wall collision path. The Yongan
  suite includes its authored-wall path and the new 3.675 m endpoint check.
- `native-r3/report.json`: 88 rendered Godot actor checks, including normal attack
  selection after back knockdown. The recovered-attack screenshot was inspected
  after the ordinary 120 ms animation crossfade. This fixture uses authored
  subscription-shaped rows, not a live server connection.
- `lint-final.log` passes owned-source lint; `build-r2.log`,
  `publish-final-qa.log` and `publish-development.log` record the module build and
  non-destructive publications.

Failed diagnostic runs remain available. The initial Sura run caught the stale
action ID; an intervening retry hit the normal signup rate limit and waited for
expiry without weakening it. The native fixture needed its required character
catalog hash and a settled-blend capture. Earlier Shaman evidence predates the
recovery fix; the final pair above uses the corrected module.

Module SHA-256: `9b5a761b76f2d9e12fe5672d0bb0114541fb18761473eb0f857eeb595adc051b`.
No new browser combat run, Windows execution or public internet qualification
was performed for this server-only change. Godot editor MCP was unavailable.

## Original common-chain camera events

The local endpoint **http://127.0.0.1:8186** now serves
`.local/p4-class-effects/exports/web-r1` against the new database
`mt2-p2-class-effects-r1-20260908`. Existing databases and accounts are preserved;
the public deployment is unchanged. The matching module remains protocol 14.

The character catalog adapter now consumes supported camera-wave metadata for
registered common-chain motions. The pinned sources contain an event on both
Warriors' fourth attacks: activation at 633,334 microseconds, duration 200 ms,
viewer range two metres and source power 300. The existing deterministic camera
policy and accessibility setting apply. Ninja, Sura and Shaman receive no
invented event. Advanced-chain events remain disabled. All converted model hashes
are unchanged; the verified fan-milestone Blender conversion was reused, and the
previous installed catalog is retained in `catalog-r1-previous-install`.

Evidence under `.local/p4-class-effects/`:

- `components-r4/report.json`: 34 main routing/content checks and 42 screen-wave
  checks, including actual source-derived events on both Warriors, no events on
  the other six appearances, disabled advanced events and camera lifecycle.
- `python-r1.log`: eight character/importer tests, including duplicate events,
  invalid power/range/duration and inconsistent source/timing rejection.
- `exports/web-r1` and `exports/linux-r1`: actual exports and package audits,
  inspecting 996 and 1,799 resource paths respectively, with 238 UI images.
- `browser-r2/report.json`: 106 checks pass with zero browser engine errors.
  Two independent accounts in actual Chrome/Linux exports exercise all eight
  previews, female Ninja and Warrior held combos, the female Warrior's camera
  wave, movement, rejection, character switching and reconnect/login lifecycle.
  Her recorded wave count is one and the completed offset is zero. Rendered
  status and world screenshots were inspected. This run checks the local
  attacker's wave; remote-viewer range behavior is covered by component tests.
- `lint-final.log`: owned-source lint passes. `build-r1.log` and `publish-r1.log`
  record the matching module build and non-destructive local publication.

The first browser run reached the camera event but failed its first-step
comparison. Its assertion repeatedly read each process during one predicate;
the corrected test takes one snapshot per client and passed on the same exports.
The failed report is retained. An initial component expectation also needed
numeric comparison for JSON-decoded microsecond values.

Module SHA-256: `52f7b3fb272500498e8a1c36635c9db12d605fbfc91b684938b209287df389a6`.
Character catalog SHA-256: `aa5ef3b8c3922c09fbb7b6731720acf238caee9aefd8bb714ed09a0b2c5c36df`.
Web PCK SHA-256: `1eb029237d74d43822ad0ae105d8b6489e23f63218657d1b49fad42117ed59fe`.
Linux PCK SHA-256: `9bb1fc864a5614b3edbfadbbfda929a755424cb9955f33072ed1a9c213664a6d`.

Godot editor MCP was unavailable. Actual exported renderers provide the visual
evidence; no Windows execution or public internet gameplay test was performed.
Attack-speed modifiers, ordinary finisher knockback and abilities remain pending.

## Class-aware camera-event routing follow-up

Main now resolves each subscribed attack's camera event using that character's
appearance, rather than always querying the male Warrior. Missing appearances
produce no event. The isolated target-client runner now stages the required
character package and records its catalog hash; previously it omitted this new
runtime dependency.

`.local/p4-class-effects/components-r2/report.json` records 34 main/content-gate
checks and 29 screen-wave checks. The routing regression exercises all eight
installed appearances, repeat suppression and missing-appearance rejection. It
uses synthetic camera events on real registered motions: additional original
class camera events are **not** adapted by this change. The existing Warrior
event is independently tested from the generated catalog. Owned-source lint
passes in `.local/p4-class-effects/lint.log`.

This is a source-level follow-up, not a newly deployed gameplay milestone.
The local and public exports remain as described below. Godot editor MCP was
unavailable; these checks used an isolated headless Godot project, with no new
rendered, exported-client or multiplayer evidence. The first sandbox run failed
on engine socket creation; the host run completed successfully.

## Protocol 14 Shaman Fan+0 and shared weapon combos

The local endpoint **http://127.0.0.1:8186** now serves
`.local/p4-fan/exports/web-r3`, using `mt2-p2-fan-r1-20260908`.
Previous development databases and auth accounts are preserved. Existing accounts
can create characters in this fresh development database. The public deployment
has not been updated by this milestone.

Both Shamans receive the selected original Fan+0, with one inventory cell,
Shaman-only requirements and physical power 11–15 derived from the pinned proto.
The converted model, texture and icon use the existing item import pipeline.
Class data selects `starter_weapon_vnum`; creation validates its requirements and
registered attack before granting the item transactionally. Common combos resolve
against the captured weapon and character appearance. Held Space looks up the
registered actor action without assuming a sword mode. Fan resistance is distinct
from sword resistance. The package audits now validate every registered weapon's
model and public stats against the item registry and load each packaged model.

Evidence in `.local/p4-fan/`:

- `characters-r2`: all eight original appearances and 234 clips converted in
  background Blender, verified and installed with the prior package retained.
  `base-build-r2.log` and `ui-import.log` cover the selected fan model and icon.
- `server-tests-r2.log`: 130 Rust unit/integration tests pass, including all
  compiled common chains, Shaman restrictions and separate weapon resistance.
- `native-r5/report.json`: 69 real Godot checks, ten rendered captures, both
  Shaman skeletons and four fan clips, hand attachment, input windows, duplicate
  scheduling and release. The isolated fixture also checks texture imports.
- `two-client-r3.json`: 106 live checks on `mt2-p2-fan-qa-20260908`, using the
  identical module. The focused `--class-id 3` run checks all eight private
  starter records, both Shaman appearances, unarmed/fan actions, four-step links,
  duplicate queues, foreign/stale item rejection, actual Wild Dog damage,
  movement in both directions and disconnect/reconnect without starter duplication.
- `exports/web-r3` and `exports/linux-r3`: actual exports and audits cover 996
  and 1,799 resource paths, eight character packages, both weapon models and
  238 UI images. Fan+0 loads as one textured static mesh attached at runtime.
- `browser-r1/report.json`: 105 checks pass with zero browser engine errors.
  Actual Chrome/Linux exports exercise all eight creation previews, female Ninja
  sword combos and male Shaman fan combos through held Space, equipment,
  movement/rejection, character switching, reconnect, reload and login/logout.
- `tool-tests-final.log`: all 211 Python tooling tests pass. `export-tests-final.log`
  independently covers 41 package/export tests. `lint-final-r2.log` passes the
  owned Python, GDScript, Rust and TypeScript checks.
- `acceptance-r1.json` binds this evidence to the module, generated catalogs,
  export hashes and reviewed source files.

Module SHA-256: `5d4a218bb5a21aa9317730875c7deb81bd4ae1d2fc1f05fe20a29206c1d1ccec`.
Character catalog SHA-256: `500e1a72dd38c625e9c7c059863d67577ebf203bf118bbcfd7613e6d4a72930a`.
Web PCK SHA-256: `68283cc456979d1caea700cc01dc0a8a42efac958b2659b52101b37fb9d213a8`.
Linux PCK SHA-256: `8476b042f77f11f99151310db065aa375c791cbdcd92361523c02e276dffc1ba`.

The pinned male Shaman MSA files copy female hit landmarks despite distinct GR2
poses. The native fixture records that discrepancy, checks both attachments against
their own right-hand bones, and retains the female source-geometry check. No male
rig correction was invented to fit copied landmarks. Failed diagnostic runs remain
in the evidence directory. The first sandboxed Blender runs hung during shutdown;
the completed conversions ran outside that sandbox.

This remains ordinary physical combat at authored, unscaled animation times.
Attack-speed modifiers, force-15 ordinary finisher knockback, advanced chains and
skills remain pending. Godot editor MCP was unavailable; isolated rendered Godot
and actual exported clients provide the visual/input evidence. No Windows execution
or public internet gameplay qualification was performed for this build.

## Protocol 14 creation lineup and held common combos

The preceding local checkpoint at **http://127.0.0.1:8186** served
`exports/web-r4` from `.local/p4-classes/`, using the new database
`mt2-p2-class-combos-r1-20260908`. The previous databases and exports remain intact.
The public endpoint remains on the older protocol-4 release.

Creation now presents all four classes around the selected foreground model,
including both gender pages. Every preview uses its original `intro.wait` clip.
The male Warrior's extra intro model is confined to the preview; its accepted
world model is retained. Gender switches detach retired nodes before creating
their replacements. The taskbar now uses the original attack image instead of
the initial layout's movement placeholder, as the pinned `uitaskbar.py` and
`mousebuttonwindow.py` specify.

Held Space schedules ordinary intents against source input windows. All six
Warrior/Ninja/Sura sword appearances resolve their common four-step chains
through shared server queue/target/equipment validation. The newly compiled
Warrior/Ninja fourth actions use their original area timing; disabled ordinary
windows cannot create extra hits. Shaman remains unarmed. Advanced chains, Sura's
force-15 fourth-hit knockback, other weapons and skills remain pending.

Current evidence in `.local/p4-classes/`:

- `intro-lineup-r3`: 61 native Godot preview checks; all eight captures rendered.
- `taskbar-r2`: 21 native HUD interaction checks and the corrected icon capture.
- `combo-server-tests-r4.log`: 129 Rust unit/integration checks pass.
- `tool-tests-r3.log`: 210 Python tooling checks pass.
- `automated-r2`: the full pinned importer converted eight appearances and 234
  clips, verified receipts and installed into an isolated QA destination. It
  leaves the current game package and open Blender scene untouched.
- `exports/web-r4` and `exports/linux-r3`: actual export/package audits inspect
  990 and 1,793 resource paths and load all eight character packages.
- `browser-combos-r2/report.json`: 100 Chrome/Linux checks pass with no browser
  engine errors. Original mouse/keyboard controls select all eight four-model
  previews, hold Space through Ninja's four sword steps and repeat Shaman's
  unarmed attack. Both subscriptions/renderers observe the actions, then return
  to idle after release. Movement, rejection and account lifecycle also pass.
- `lint-final.log`: all owned Python/GDScript/Rust/TypeScript checks pass.
- `combo-two-client-r5.json`: 282 live two-identity checks pass on the separate
  QA database using the exact playable WASM. All eight appearances, private
  creation/stats/inventory, rejected appearance IDs, six four-step sword chains
  with queued/direct inputs and duplicate rejection, real mob damage, movement,
  character switching, disconnect and reconnect are covered.

The local module SHA-256 is
`793477d2a987d885666b94e523a738f688d97e55b40398b4ec9b001247eabc90`;
the shared catalog SHA-256 is
`fdac0c3b96b433b2aa8c413229ece827e8f530e9dcf068faf58ed035d2c84226`.
Superseded failed reports remain available. Fixture corrections replaced old
Warrior-only duration expectations, moved targetless checks outside dog aggro,
and allowed 24 seconds for each approach/return across the actual map. The full
eight-appearance scenario has a six-minute bound. Browser registration initially
hit the existing signup limit and passed after normal expiry; limits remain
enabled. No connected Godot editor MCP is available in this session. Native
rendered fixtures and exported clients provide evidence; Windows execution,
public deployment and original-client parity are not qualified by this run.

## Earlier protocol 14 classic character creation and basic actions

The latest requested milestone adds Warrior, Ninja, Sura and Shaman in both sexes
to character creation. Original class titles, default hair, body models and
class/sex status portraits are installed. Class starting HP/SP and stats are
server-owned; original basic action IDs and class physical stat contributions
use the shared combat, movement and inventory rules. The selected male Warrior
keeps its accepted combo implementation. Shaman currently begins unarmed;
its fan item/combat, other weapon modes, skills and the additional classes' full
combos remain pending. Quests remain deferred.

`make characters-build` now discovers the selected pinned inputs and performs
Blender conversion, artifact verification and installation. `--replace` preserves
the previous installation alongside the new output. Eight bodies/default-hair
sets and 234 motion clips converted successfully; seven additional actor packages
extend the accepted Warrior baseline. See [the workflow](../characters.md).

Current evidence in `.local/p4-classes/`:

- `classic-r3/`: successful Blender conversion and source/artifact receipts.
- `intro-ui-r4/`: 53 native Godot UI checks, including eight front-facing previews.
- `two-client-r3.json`: 196 live checks against two ordinary accounts on one
  actual server, covering all eight creations, exact initial stats, invalid IDs,
  private subscriptions, mutual appearance/movement, actual mob hits, switching,
  disconnect and reconnect without duplicated starter items.
- `exports/web-r1/` and `exports/linux-r1/`: actual exports and package audits;
  980 Web and 1,783 Linux resource paths inspected. Every added actor is loaded
  to verify its textures, skinning, attachment bones and registered animation clips.
- `browser-r1/report.json`: 96 passing exported Chrome/Linux checks. Browser
  controls exercise all eight previews, female Ninja creation/equipment/keyboard
  attack, male Shaman creation/unarmed keyboard attack, bidirectional movement,
  character switching, rejection, disconnect/reconnect and login/logout.
  Browser engine errors are empty. Native uses an isolated Xvfb display; this
  is not Windows execution or inspection through the user's open Godot editor.

The earlier local playable build served the Web export
against `mt2-p2-classes-r1-20260907`. Its protocol-14 module uses the matching local
auth issuer and disables guest access. The previous protocol-13 database/export
are preserved; `proxy-before.json` records the old routing. The public endpoint
remains the older protocol-4 release.

The local module SHA-256 is
`70164499c8fb008959c24fbb4a7d32013094bdd12e52cd94fd199867fa2a646d`;
the shared character catalog SHA-256 is
`2cd7fa42f55837417363c373de1ecef2b1740f5f4c6bf2f38741109e3083a880`.
Creation and basic actions are the qualified slice; full class gameplay, broader
content factories and retail parity remain separate work.

## Protocol 13 NPC interaction slice

The City Guard now supports click-to-approach and a private server-owned dialogue.
The implementation joins authored interaction records to the converted catalog,
checks its advertised hash, validates active character/range/path/attack state,
and uses exact unique session IDs for closing. Duplicate opens cannot renew the
60-second deadline. Movement, attack, leave, disconnect, death and expiry clear
the session. Quests and shops remain deferred; the greeting is new development
text. Picking uses a separate body with no movement collision.

The fresh local database `mt2-p2-npc-interaction-r1-20260907` preserves all older
databases. `.local/p3-interactions/two-client-r3.json` passes 59 ordinary-account
checks, including raw owner-only subscriptions, forged/distant/stale/foreign
rejections, real expiry, two-way route movement and reconnect without replay.
R1 caught a test parser error before creating accounts; R2 exercised the gameplay
but failed an assertion expecting the wrong inactive-character error wording.
These failures remain recorded; R3 is the accepted network result.

The isolated native Main fixture passes 38 checks and its original-asset panel
capture was reviewed. The final focused client preflight passes content gate 9,
picker 9, export probe 35 and protocol gate 4. The full tooling suite passes 203
checks; owned lint, strict Clippy and TypeScript checks pass. Current Rust tests
pass 127 checks. Godot MCP was unavailable; the user's open editor was preserved.

The local 8186 proxy now targets the matching protocol-13 Web/Linux test exports
under `.local/p3-interactions/exports/`. Actual-PCK audits check 877 Web core files,
all 20 streamed map packs and 1,680 Linux files. The actual Web/Linux run passes
103 checks on its first attempt, with clean browser/native engine logs. Both
clients click and approach the guard, receive independent conversations, close
with the original-asset button, and retain normal input; browser Escape and WASD
are explicitly exercised. Both dialogue captures were reviewed. The source
freeze remained unchanged throughout qualification. Evidence is
`.local/p3-interactions/acceptance-r1.json` and `browser-two-client-r1/report.json`.

The missing-catalog bootstrap fixture proves that the offline terrain example
builds successfully while the game library fails closed. It uses an isolated
copy, preserving installed content and the editor. Its report is
`.local/p3-interactions/bootstrap-r1/report.json`. Current-source WASM is checked
against the preserved published artifact in `server-build.json`.

These are authorized local instrumented exports. Public protocol 4 remains
unchanged; Windows execution and current editor-MCP inspection are not claimed.
Full map pathfinding, shops, quests, live admin placement, trees and additional
classes/abilities/maps remain beyond this slice.

## Gameplay population and offline development mode

Current user priorities defer quests and move gameplay, mobs, map NPCs, scenery,
classes, abilities and additional maps ahead of quest execution. The catalog
remains the complete scope; this changes implementation order.

Population profiles now select six authored Wild Dog homes for Yongan and one
for training. The build and offline tool share validation; position checks use
the server's actual terrain/collision code. Add/move/remove commands produce
reviewable drafts without modifying source profiles or live databases. Changed
populations require a fresh development database until migration is implemented.

The new local `mt2-p2-yongan-population-r1-20260907` database uses protocol 12,
ordinary accounts and no privileged bootstrap identities. Its module SHA-256 is
`dfbb9cb596dc98e2a689061817f7c737ab2b9aee47a629bf4eabb93145073fa0`.
`.local/world-content/population-server-r1/two-client-r1.json` passes **107
checks** with unchanged staged sources: exact subscribed homes/heights, mutual
movement, invalid target rejection, ordinary combat and one reward, independent
other mob lives, natural respawn, disconnect and reconnect without extra rewards.
Rust passes 109 unit plus 14 integration tests and strict all-targets Clippy.
The Python suite passes 198 tests. The authoring CLI also rejects an actual
Yongan building intersection without writing a draft, and a valid move preserves
the input and unrelated IDs. The final NPC receipt passes 22 headless checks.

Original City Guard 20354 converts with two textures and five clips. The shared
rigid-binding adapter fixes its weapon's missing skin weights; yaw normalization
fixes facing. The native gallery passes **22 checks**; its attachment was visually
reviewed in `.local/p3-npcs/city-guard-qa-r2/`. Final conversion inputs/artifacts
are in `.local/p3-npcs/city-guard-r7/` using converter 1.1.0; its GLB is byte-identical
to the rendered R6 artifact. The first gallery exposed a floating weapon despite
passing pose checks; explicit mesh skin checks now cover that omission.

The isolated Yongan dev preview passes **15 checks**, including actual ItemList
selection/focus and idle animation for six mobs and the guard. Its reviewed
`.local/world-content/yongan-preview-r2/population-preview.png` shows the guard at
source X/Z 605/663 and server height 198.515. R1 caught a JSON numeric-key error
at runtime and remains recorded as failed. The corrected launcher owns and cleans
up its preview process group. See [the runnable workflow](../world-content.md).

Godot MCP is unavailable; these checks use isolated native projects, not the
user's live editor. This population/preview checkpoint preceded the Main-scene
NPC integration below. Live admin placement, trees, further mob types/classes/maps
and abilities remain pending.
At this population-only checkpoint, public deployment and the served protocol-10
local Web export were unchanged; the newer local rollout is recorded below.

## Stationary NPCs integrated in Main locally

The City Guard is now installed through a reusable public NPC catalog and the
normal Main-scene `WorldNpcs` layer. It uses original point X/Z 605/663, baked
height 198.515, deterministic source-random heading, original green name color,
both weighted idle variants and the corrected rigid weapon attachment. There
are no new NPC collisions or interaction/reward intents. Protocol 12 is unchanged.

The catalog compiler validates completed conversion receipts, stable IDs,
terrain/collision placement, map hashes and an exact public payload. It reuses
the existing actor PNG extraction/import policy; pixel checks accept Godot PNG
re-encoding but reject changed imagery. Prior installed assets are retained when
installing an update. Main creates/removes actors with terrain availability and
clears the layer on leave, disconnect and reconfiguration.

`.local/p3-npcs/runtime-qa-r1/` passes 36 real-Godot Main-scene checks, including
original positioning, both idle variants, both skinned meshes, no added collision,
stable instance refresh, real chunk reload, five connection-state cleanup/reentry
pairs, map-hash rejection and training-map cleanup. Its native screenshot was
reviewed. This is an explicit offline connection spy, not new multiplayer proof.
The preceding 107-check live population result remains the server evidence.

The normal Linux export first rejected the earlier item registry's newly added
public field. The exporter now validates its exact public boundaries, checks it
against trusted server item definitions, and exercises the packaged runtime
reader. NPC package checks inspect actual remapped skins/materials/idle clips.
The final native project `.local/p3-npcs/runtime-qa-r2/` also passes all 36 checks
with unchanged staged source and reviewed rendering. The final normal Linux export
at `.local/p3-npcs/exports/linux-r3/` passes the actual-PCK audit of 1,666 files,
including two textured/skinned NPC meshes and five imported clips; no test probe
is packaged. Its PCK SHA-256 is
`1373e9af32606423c077330c64cdccbe0c77ef0b0529d3dc9745a0acb9f3b918`.
Final catalog/conversion provenance is `.local/p3-npcs/runtime-r3/`; the public
catalog remains byte-identical across R1–R3. Four NPC tooling regressions,
40 export-tooling tests, and owned Python/GDScript lint pass. The export is staged
for the population database; its intended gateway has not been switched and no
new authenticated exported-client/browser gameplay run is claimed.

The final production PCK also passes the same 36 lifecycle/render checks under
the installed Godot engine in `.local/p3-npcs/pack-runtime-r1/`; its captured
render was reviewed. The preceding direct release-executable attempt at
`.local/p3-npcs/export-runtime-r1/` did not execute the external probe to completion
and timed out at 90 seconds; its process group was terminated. That attempt
is recorded as failed, not exported-client gameplay evidence.

No new quests, NPC interactions, shops, live placement controls, trees, classes,
abilities or maps are claimed. Godot MCP was unavailable; the user's editor was
preserved. The local browser rollout below supersedes the older served build.

## NPC browser rollout qualified on the local endpoint

The actual instrumented Web/Linux exports now pass **94 checks** on
`http://127.0.0.1:8186` and `mt2-p2-yongan-population-r1-20260907`. Two ordinary
accounts create their own characters, subscribe to each other and all six mobs,
walk a collision-checked 149-meter route to the guard, and render the same idle
NPC at its original position. Actual pointer input does not turn this stationary
NPC into a monster target. Native leave/reentry and browser reconnect restore
one NPC without duplicates. Mutual movement, invalid-input rejection, foreign
character rejection, character switching, disconnect/reload, logout and login
also pass. The optional four-minute refresh scenario was not repeated.

`.local/p3-npcs/browser-two-client-r1/report.json` has no browser or native engine
errors. Its browser/native NPC screenshots were reviewed: consistent terrain
colors, grounded actors, original hair, and the guard's attached weapon. Chrome
used hardware WebGL 2 on AMD Radeon 860M. The read-only export probe preflight
passed 35 probe and nine content-gate checks before account creation. All 130
frozen build/QA input hashes stayed unchanged; the concise acceptance record is
`.local/p3-npcs/browser-acceptance-r1.json`.

The local proxy was deliberately switched from the older physical-finisher
database/export to these matched packages under `.local/p3-npcs/exports/`:
`web-probe-r1` and `linux-probe-r1`. Strict PCK audits checked 865 Web core files
and 1,668 Linux files, including the NPC catalog and remapped skins/materials.
The Web export also builds and audits its streamed map packs. Prior routing is
saved in `local-service-before.json`; `local-service-update.json` records verified
served-manifest equality, database identity and auth health. Game/auth processes
and all existing databases were preserved. The local proxy's owned exec session
is 52594. A separate Chrome MCP tab shows the original server-selection screen
with CH 1 online; no unrelated tabs or editor scenes were changed.

This is local connectivity evidence. The public endpoint remains the protocol-4
release; no new internet or Windows qualification is claimed. Normal packages
still omit probes. Stationary NPCs have no interaction/shop/quest authority yet.

## Item integrity and replay protection qualified locally

Protocol 12 retains server-assigned persistent instance/stack IDs and adds checked
item revisions to move/equip/unequip/use intents. Ownership is validated against
both the active character and authenticated account; stale, forged, exhausted
and invalid revisions fail closed. Quantity changes append private audit events
in the same transaction as grants, stack changes, consumption, pickup and expiry.
Automatic progression grants now propagate integrity errors, preventing a partial
reward from being accepted. The ordinary full-bag ground fallback remains.

The fresh `mt2-p2-item-security-r1-20260907` local database contains the recovery
fixture with ordinary accounts, no guests and no privileged commands. Its module
SHA-256 is `3c778ca5e0eef26693c0d8edfc4a2f0eb7dfee84a671bcefed3b711e1e9cb680`.
Matching bindings contain 73 files, with schema SHA-256
`997a48863cd84380226ea8fbf73739169276c02fb172d3d3b98a3a0a9d68a12d`.
`security-two-client-r6.json` passes **110 checks**, with unchanged staged sources:
independent identities and private inventories, mutual movement, forged IDs and
revisions, foreign/inactive-character actions, stale movement, duplicate potion
consumption, reconnect persistence without duplicated starters/effects, ordinary
combat and drop production, reservation rejection, a two-client pickup race with
exactly one winner, conserved quantities and private audit-query rejection on
both clients. Failed preflights R1–R4 caught Godot lambda parsing before account
creation. R5 passed the rejection/consumption checks but incorrectly compared
reconnected inventory rows by order; R6 sorts by persistent ID and compares every
field. No gameplay rule was relaxed to make these checks pass.

The existing Godot component suite passes 130 checks and the new real-facade
item intent suite passes 10. `make server-test` passes 109 Yongan unit, six combo
builder, four item builder and two generated-definition tests. Strict Clippy,
Python/GDScript lint and 189 Python tooling tests pass. The offline audit checker
has fixture coverage for transfers, consumption, gaps, duplicate/live/exhausted
IDs and stock/ownership/revision mismatches. It is a diagnostic tool, not an
inventory repair command. An authenticated operator snapshot-export path and
history retention/archival remain pending; a CLI SQL attempt was rejected by the
module's account gate. No authentication exception or public audit table was added.
Full-bag rollback has not received a new live scenario in this slice. Trading,
shops, mail, storage and quest reward contracts remain future implementation.

Evidence and frozen source/module review are under `.local/p2-item-security/`,
including `review-root.json` and `handoff-root.json`. Changes are uncommitted.
No current release export, editor MCP inspection, public deployment or database
reset is claimed. The served local Web build remains protocol 10, and the public
endpoint remains protocol 4.

## Preceding item registry and gradual recovery

That checkpoint uses protocol 11, trusted schema 7 and compiler 1.6.0.
The profile's schema-1 item catalog resolves the selected Sword and small/medium
red potions from pinned source rows. Shared lookups now drive size/stack limits,
equipment requirements, physical power, public names/icons/tooltips and use
dispatch. Recovery is a private life-scoped pool, with 300/800 HP effects and
source 7%-of-maximum ticks. General item categories, applies, quest execution,
SP-item live coverage, migration tooling and current exported qualification
remain pending.

The isolated `mt2-p2-items-recovery-r1-20260907` database uses a default-deny
test module with two extra medium starter potions and loopback auth. The normal
starter loadout remains one Sword and five small potions. No existing database
was overwritten; no privileged actions or guest accounts were used.
`recovery-two-client-r2.json` passes all 50 checks with unchanged staged sources:
mutual presence/movement, private inventory, rejected uses, small-potion recovery
289→589, medium-potion recovery 589→760 with a cap, exact consumption and pending
effect cancellation across disconnect/reconnect. R1 remains failed: its full-health
check used a character already injured during staging. Its corrected precondition
uses the safely parked observer. Reports are under `.local/p2-items/`.

Current Godot bindings were generated from this actual module: 72 files, schema
hash `dd0b934dbca71784095da35e10ad072b5f8d2d62b92bdbab0410f8ea93c1b61d`.
The isolated Godot component suite passes 130 checks; the rendered inventory
test passes 21, including medium-potion right-click routing. The separate rendered
tooltip capture passes 14 checks, and the item-registry melee regression passes
94 live checks. Captures were reviewed. Python tooling passes 186 tests, including source-driven additional-item
and malformed-registry checks. Full lint passes, followed by the final Rust
link/fixture validation checks: 108 unit, six combo-builder, four item-builder
and two generated-definition tests, plus strict Clippy. Rebuilding after those
build-only checks yields the identical live-qualified WASM SHA-256
`faa7b266c555dccfec5eaff45f92dbaa2935861066cf6ab904c109e88befc94f`.
Model/texture/animation
artifacts remain unchanged and were reused through the compiler's client generator.
Godot editor MCP is unavailable; no editor inspection is claimed.

The item changes have not replaced the local protocol-10 Web export or the
public protocol-4 route. The previous physical growth, finisher and exported
reports below remain evidence for their recorded artifacts.

## Preceding physical damage integration

That checkpoint integrates application protocol 10 and trusted content
schema 6. The damage kernel consumes generated physical definitions and
canonical progression/equipment. The private progression row now includes
Attack minimum/maximum and Defense display values. Fresh local databases
`mt2-p2-physical-{training,finisher,yongan}-r1-20260907` preserve existing worlds
and contain no guest or privileged progression bootstrap.

The training/Yongan Rust suites pass 99/104 unit tests respectively, plus six
builder and two generated-definition tests each. Strict Clippy passes. The real server schema
generated 71 client binding files, schema hash
`4f692de9eab4b3d7b7007fcabb78e047ff2655e523476808859201c98ad1eacf`.
The isolated Godot client suite passes 127 checks, including the physical UI and
protocol gate. Model/texture/animation bytes remain unchanged from the accepted
visual checkpoint. Build and publication records are under
`.local/p2-physical/integration-r1/`.

The focused two-account Godot run passes 101 checks:
`.local/p2-physical/integration-r1/physical-two-client-r3.json`. It verifies
mutual subscribed movement, private stat projections, equipment updates,
targetless/stale-life handling, an accepted sword hit after unequipping,
subsequent unarmed and equipped damage, dog damage, a kill reward, natural
respawn, disconnect/reconnect and character switching. This is headless
subscription evidence, not an exported-gameplay or visual comparison.

The actual Web and Linux test exports pass package inspection, with 852 source
files held unchanged throughout export. Their manifests are under
`.local/p2-physical/integration-r1/exports-finisher/`. The 174 Python tool tests
and full lint pass; the plan validator retains all 41 systems/194 records.

The physical finisher now passes 65 checks in
`physical-finisher-r2.json`, including both eligible victims on both real
subscriptions, per-victim damage, 4.732 m force/standup, captured equipment after
unequipping, the untouched third monster, fifth-input rejection and reconnect.
The staged sources stayed unchanged. The separate `physical-lifecycle-r1.json`
now passes 49 checks against `mt2-p2-physical-lifecycle-r1-20260907`: presence is
removed before area activation, monster health/lives remain unchanged, and
reconnect does not replay the cancelled attack or root displacement. This uses
two real headless clients and the same reviewed finisher module on a fresh
database; its staged sources stayed unchanged.

The latest completed growth run, `physical-growth-r6.json`, passes all 1,063
checks across four segments with unchanged staged sources. Two real clients
verify twenty ordinary kills, exact XP/quarters, level two, private display,
old/new STR damage across a queued action, and VIT/DEX effects on damage and
display. Spending VIT increases maximum health without healing current health.
All three earned points are spent privately. R5 remains failed because its
assertion expected the second action at the exact 533,333 us input boundary;
R6 records subscribed ticks and verifies the actual contract: the first simulation
tick strictly after that boundary. No gameplay timing change was needed.
Earlier failed runs also exposed JSON float-versus-integer test-domain comparisons
and the need to finish an injured leftover monster through ordinary observer
combat. The test now handles both without resetting database state. R2's separate
transport timeout and observed scheduler activity gap remain recorded in
`physical-growth-r2-review-root.json`.

The actual `browser-physical-r1/report.json` passes 94 functional checks, including
Web/native equip/unequip through UI, owner-only Attack/Defense projections,
remote equipment attachment, movement and account lifecycle. All four relevant
captures were reviewed: Attack 10 unarmed, 28–31 equipped, Defense 5, and the
Sword+0 tooltip's 13–15 range. The overall run remains failed by its unchanged
engine-error gate: Linux logs two embedded-tooltip signal-disconnect errors.
A tiny independent Godot 4.7.2 release export reproduces them with a plain Button;
the external-popup comparison is clean. See `browser-physical-r1-review-root.json`
and [Godot issue 89657](https://github.com/godotengine/godot/issues/89657). The
local 8186 proxy now serves the reviewed physical finisher export/database.
Public routing, normal-export qualification and Windows execution are unchanged.

The current all-feature Rust run passes 105 unit, six builder and two generated
definition tests. All 180 Python tool tests pass, including six new content-diff
tests; subsequent non-finite-number/schema hardening also passes those six focused
tests. Full lint passes, followed by focused formatting/lint of the R6 scenario.
The implemented `content_compile.py diff` reports changed generated fields and
relevant QA scopes; the actual pre-physical/current comparison reports nine
gameplay and two presentation field changes. This is development tooling, not
general item/quest registries. Editor MCP remains unavailable in this session.

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

## Historical P1 checkpoint artifact evidence

At the P1 checkpoint, the generated `p0-warrior-dog` manifest recorded
source-content hash
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
Later combo steps, automatic chase, broader combat and social target actions,
public protocol deployment, Windows execution, full P2 and the full game remain
incomplete.

The root acceptance record
`.local/p2-target/root-acceptance-review.json` binds the 175 unchanged client
sources, 17 server source hashes, three module artifacts and both accepted PCKs.

## Protocol 7 bounded combo Slice B

The local implementation adds the first source-timed link from `combo_1` to
`combo_2` for the male Warrior with Sword+0. The compiler's trusted schema 3
projects exactly the reviewed two-action prefix and normalized
pre/direct/limit/link timings; the server receives only the existing
argument-free `perform_attack()` intent. Private checked action/chain revisions,
captured target life and exact equipped item identity guard the queue, while the
public player action ID/start/end/sequence remains the presentation surface.

The runtime preserves the accepted pending-hit snapshot and simulation order.
Queued transitions occur on the first tick strictly after the direct boundary;
duplicate, early, late and bounded third-step requests are private rejections.
Accepted movement, target change/clear and real equipment mutation cancel a
queued link without changing the current hit, while same-target renewal and
rejected/idempotent mutations preserve it. The existing locomotion hold lasts
through the attack window. Targetless and missed attacks may animate both steps
without damage, matching the reviewed original non-bow timing path, and no
transition replans a target.

The isolated Rust evidence passes 60 gameplay unit tests, four build-boundary
tests and one generated-definition test, with all-target/all-feature clippy
warnings denied. The new two-account runner and Godot smoke pass static Python,
GDScript and parser checks. The source-verified root build produced separate
default-deny training, dual-training and Yongan artifacts and published them to
fresh local databases with no data deletion; exact hashes and identities are in
`.local/p2-combo/build-manifest-root.json` and
`.local/p2-combo/publication-root.json`. Matching bindings are generated. The
focused two-client run passes all 71 checks in
`.local/p2-combo/combo-root-safe-fixture-20260907.json`; its exact report hash is
`becc30159ffab215cdb3c25f7d2c8453fe338383960daba53da93136c4b6e7ad`.
Targetless and far chains, exact 35/35 damage, duplicate preservation, immutable
pending damage across a pre-hit equipment change, death/new life, two-way
movement and queued disconnect/reconnect all pass. The root record
`.local/p2-combo/root-headless-acceptance.json` binds the report and frozen
harness to the server build manifest. This accepts the bounded headless server
slice.

The retained protocol-7 target regression passes its 51 applicable checks in
`.local/p2-combo/targets-root-first-20260907.json`. Instrumented Web/Linux PCKs
also pass the 832/1635-path content audits recorded in
`.local/p2-combo/exports-probe2-root-reviewed.json`, including 226 exact UI
images, three actors, 40 clips, 20 Web world sections and both 11-frame target
effects. The 212-file source freeze is unchanged.

The actual instrumented Web/Linux run passes all 288 checks in
`.local/p2-combo/browser-root-independent-followup-20260907/report.json`, SHA-256
`5d015eb38261ed2daa25fe447c6f4bc1b9a8c48c213932160dd5451239c8cc9c`.
Both positive queues, `100 -> 65 -> 30` damage, same-target renewal,
WASD/ground-click/target-clear cancellation, actor and inventory composition,
account lifecycle and both real refresh timers pass. The 53-row trace contains
52/50 valid Web/native positions and 1/3 transient pending rows during
lifecycle, with zero drift in every valid row and no invalid rows. No browser
engine errors or native engine-log errors were observed; the intentional
ownership reducer rejection remains recorded.
`.local/p2-combo/root-acceptance-review.json` binds this result to the focused
headless, server build and actual-PCK evidence. It also records 65 Rust tests,
143 Python tests, 71 actor checks and 56 focused component checks. Bounded local
Slice B is accepted.

Earlier diagnostic reports remain preserved under `.local/p2-combo`. The final
harnesses use received-clock extrapolation plus stable authoritative/rendered
fixture gates and retain exact reducer receipt assertions. Normal exports omit
the fixed-input probe and were not exercised. Public Slice B gameplay/deployment,
Windows, Godot MCP, original-client parity, later combo steps, root motion, full
P2 and the full game remain incomplete.

## Protocol 8 combo/root-motion Slice C

The current local implementation extends the trusted common male-Warrior
Sword+0 prefix through `combo_3`. Schema 4 derives all three action records,
their input windows and exact raw-GR2 root endpoints from pinned content. The
server retains the argument-free attack intent, private checked chain/action/root
state and the existing public player position/action projection. No client
timing or transform becomes authoritative. A root-enabled action keeps its
captured public heading through its hit instead of turning toward the target at
hit time; rootless attacks preserve the established target-facing behavior.

Root displacement uses the documented `linear-endpoint-approx-v1` policy with
f64 cumulative endpoint fractions, bounded action-relative 50 ms samples and
the existing f32 terrain/sweep path. Queue-only input does not create a physics
sample. Accepted replacement flushes only its outgoing partial interval;
collision-clipped distance is consumed. Pending hits, future links and current
root state remain separate so target death and cancellation cannot rewrite the
accepted current action, while character/account lifecycle clears residual
movement with no reconnect catch-up. Exact Granny curve and blend behavior is
still a fidelity gap.

The isolated server suite passes 67 training and 72 all-feature gameplay tests,
five build-boundary tests and one generated-definition test per configuration;
all-target/all-feature clippy passes with warnings denied. Training, dual and
Yongan default-deny artifacts and fresh database identities are bound by
`.local/p2-rootmotion/revision2/build-manifest-root.json` and
`.local/p2-rootmotion/revision2/publication-root.json`. The gameplay definition
hash is
`2f096ae82998eeecb839df391a7350f8309e477a7004ef4c2e333167bc4ada8d`.
The composed two-account revision-2 headless run passed 91 checks in
`.local/p2-rootmotion/revision2/headless-root-20260907.json`. Its normal authenticated
paths cover three-step targetless/far-missed/selected chains, exact
`100 -> 65 -> 30 -> 0` damage, open-terrain endpoints within 0.97--11.44
micrometres, training-stone clipping, current-root continuation through target
death and equipment cancellation, and disconnect/reconnect without catch-up.
Its crossed-target case holds the captured and post-hit headings at
`-1.57207345962524` while the superseded hit-time target bearing differs by pi.
Root's independent binding is
`.local/p2-rootmotion/revision2/root-headless-acceptance.json`. The original
88-check report remains preserved under `.local/p2-rootmotion/` as historical
evidence superseded by revision 2.
The reviewed revision-2 test-probe Web/Linux package audit is
`.local/p2-rootmotion/revision2/exports-root-reviewed.json` (832/1,635 paths,
226 UI images, three actors, 40 clips, 20 Web world sections and two 11-frame
target effects). The matching exact-manifest actor regression passes 77 checks
in `.local/p2-rootmotion/revision2/client-actors-current-local-sockets/report.json`,
and the fresh dual-target regression passes 51 checks in
`.local/p2-rootmotion/revision2/targets-root-20260907.json`.

The matching exported Web/Linux gameplay run passed 297 checks in
`.local/p2-rootmotion/revision2/browser-root-lifecycle-20260907/report.json`.
Both clients observed `100 -> 65 -> 30 -> 0`, all three public/rendered action
steps, renewal before both transitions and constant per-action heading. Maximum
linear endpoint error was 0.452 mm. The cancellation matrix preserved each
current hit/root while canceling its queued link, disconnect/reconnect added no
movement, and both clients agreed on the Yongan wall's clipped 0.92199707 m
travel. Both real four-minute refresh timers passed; 52 Web and 51 native
position samples had zero drift, with transient pending rows only during
lifecycle changes. No browser engine errors or native engine-log errors were
observed; the intentional ownership rejection remains recorded.

The focused client component report passes 66 checks and the Python tooling
suite passes 148. Together with the 91-check headless run, 51-check target and
77-check current-manifest actor regressions, the 67/72 Rust gameplay suites,
five build-boundary tests and one generated-definition test, this evidence is
bound by `.local/p2-rootmotion/root-acceptance-review.json`.

The bounded local instrumented protocol-8 Slice C is accepted. Public Slice C
gameplay/deployment, normal exports without the fixed-input probe, Windows,
current Godot MCP inspection, exact Granny within-cycle/transition-blend and
original-client trajectory parity, terminal step 4, skills, full P2 and the full
game remain incomplete.

## Accepted local fourth-hit finisher Slice D

The bounded local milestone is accepted after Slice C. The final R8
hardware-Chrome/Linux run passes **154 checks**, including the complete finisher,
inventory restoration, movement, account lifecycle and both real session
refreshes. Root reviewed the captures and bound the source/package/module
evidence in `.local/p2-finisher/root-acceptance-review.json`. The public route
remains the earlier protocol-4 build.

This milestone completes
the selected male-Warrior Sword+0 common chain through terminal `combo_4`, with
its fixed special-area event, server-owned monster knockback and the selected
Wild Dog front-knockdown, front-standup and back-knockdown clips. A deterministic
camera wave and a persistent player-accessible disable setting accompany the
subscribed fourth action. Other combo types, skills, classes and the remaining
full-game catalog retain their existing scope and are not covered by this slice.

The shared implementation contract uses trusted content schema 5 and application
protocol 9. Added action/area/force bookkeeping stays private; clients consume
the existing public player and monster position/action fields. The fourth raw
GR2 root endpoint has a narrow pinned MSA-discrepancy exception. Linear root
interpolation, static defending spheres, quadratic force interpolation and the
zero-mean camera wave are explicit approximation policies, not evidence of
original-client motion parity.

The server owner implements authority/lifecycle and authenticated scenarios;
the content owner implements validation, generated definitions and converted
clips; the client owner implements reaction presentation, camera/settings and
exported scenarios. The integration owner reviews the completed contracts and
owns service changes, publication, exports and final two-client qualification.
Work and new evidence are staged under ignored `.local/p2-finisher/`; accepted
Slice C inputs and artifacts remain preserved under `.local/p2-rootmotion/`.

The planned finisher scenario uses exactly three ordinary Wild Dogs on Training
Grounds: a selected victim that survives until the fourth action, a second
victim that survives its area hit and demonstrates knockback, and an outside
control. Staging uses ordinary movement/actions and natural respawn. Both
authenticated clients must observe the same lives, health and motion, including
the second hit after the selected victim dies. Existing Yongan qualification
remains a separate check.

Root integration has built and published three local default-deny protocol-9
databases on the existing `http://127.0.0.1:13223` service:
`mt2-p2-finisher-training-r2-20260907`,
`mt2-p2-finisher-finisher-r2-20260907` (the three-dog fixture), and
`mt2-p2-finisher-yongan-r2-20260907`. Publication used `--delete-data=never`,
the existing `http://127.0.0.1:8186/auth` issuer, disabled guests and no privileged
bootstrap. The preserved release WASM and earlier databases were not replaced.
The current root build passes 81 training and 86 Yongan unit tests, six build tests and
one generated-definition test per variant, plus strict all-feature Clippy.
Build/source hashes are recorded in
`.local/p2-finisher/integration-r4/build-manifest-root.json`. The r2 publication
record remains in `integration-r2/publication-root.json`; the subsequent
wording-only compatible update is recorded in
`integration-r3/compatible-update-r2-root.json`. The subsequent targetless-area
damage fix is recorded in `integration-r4/compatible-update-root.json`; both
updates preserve database identities/schema with `--delete-data=never`. The r3 optional CLI row-snapshot
preflight required game-account authentication, so direct before/after row
equality was not verified. The isolated Godot generator has
produced and instantiated 71 bindings from the actual new module, with schema
SHA-256 `b3066b26ea524ac77811b467c4c91f2814586c9626a555dc2d030a6ed00c3d4a`.
All three current modules were checked against that same generated schema.

Current focused client checks pass 101 assertions, and the current generated
actor fixture passes 85; see `.local/p2-finisher/client-components-final-inputs-2/report.json`
and `.local/p2-finisher/actors-current/report.json`. The repeat content build and
three reaction-clip deformation/import checks are recorded in
`.local/p2-finisher/compiler/report.json`. The Python tooling suite passes 150
tests. Actual Training and Yongan Web/Linux exports also passed package audits:
844 paths in each Training pack and the Yongan Web core, 1,647 in the Yongan
Linux pack, all 226 selected UI images and both target effects. Export input
hashes and package identities are recorded under
`.local/p2-finisher/integration-r2/exports-finisher/` and `exports-yongan/`;
`integration-r3/export-review-root.json` records the integration review.

The first three authenticated finisher attempts remain failed evidence under
`integration-r1/` and `integration-r3/`. The first exposed a test's stable-state
timer bug; its fresh-character snapshots also revealed that the finisher
incorrectly rejected valid initial life sequence zero, now fixed in the r2
runtime. The second and third passed 25 setup/baseline checks but exhausted their
ordinary combat-staging attempts before any attack. The third showed that the
player had approached too close to the dogs: its nearly three-metre retreat
could not retain the required attack pause. The revised setup stops earlier and
checks the retreat distance against the remaining pause.

A separate live four-step regression exposed another runtime defect: targetless
combo transitions supplied zero damage, so the fourth area's validation rejected
the action. The r4 fix derives trusted area damage independently of selection
while retaining ordinary-hit target validation. Its actual two-account replay
passes **95 checks**, including the targetless fourth action, its 1.196471 m
root endpoint (0.018 mm measured error), rejection of a fifth input, existing
collision/cancellation coverage, and disconnect/reconnect without movement replay.
See `integration-r4/headless-four-step-root.json` and its input-hash record.
The subsequent live two-account, three-dog scenario passes **61 checks**. The
fourth action kills the selected dog, hits the second exactly once and leaves
the outside control unharmed. Clearing selection and removing the sword before
area activation preserve the accepted action. The surviving dog moves 4.732 m
and transitions from front knockdown to stand-up. See
`integration-r4/headless-terminal-clock-root.json` and its input-hash record.
The expanded scenario subsequently passes **185 checks** on the separate fresh
default-deny `mt2-p2-finisher-finisher-lifecycle-r4-20260907` database with the
same reviewed r4 module. Its observer confirms owner presence removal before
area activation, no later area damage, and reconnect without action or root
replay. Disconnecting after a hit preserves the victim's exact life, knockdown
sequence/timing, full 4.732 m force and stand-up transition. Ordinary cleanup
and natural respawn then establish that a new victim life has no inherited
area, force or reaction and can take a new hit. See
`integration-r4/headless-lifecycle-root.json` and its unchanged-source record.

The first actual exported hardware-Chrome/Linux replay passes 25 checks through
account entry, mutual visibility and opening the inventory, then fails the
existing item-hover tooltip assertion before combat. Its browser-error list is
empty; the report and rendered failure capture are preserved under
`integration-r4/browser-finisher-root/`. A deterministic real pointer-entry
change in the test helper passes the unchanged tooltip assertion and the
remaining inventory checks on replay. That run passes 69 checks, including
ordinary recovery of the previously injured dog, then fails the finisher's
first-attack timing prerequisite before reaching the fourth action. Evidence
is in `integration-r4/browser-finisher-hover-root/`; exported finisher
qualification remains pending. The test helper now observes target acknowledgements
and their age on the same browser clock; an independent synthetic browser check
passes, while the full gameplay replay remains pending. The actor texture generator
now disables automatic 3D compression. An actual editor negative control reproduces
the old VRAM rewrite, and the corrected policy preserves all four current actor
textures and their decoded pixels across repeat imports.
That earlier iteration was not accepted; final R8 acceptance is recorded below.
Slice D has not been deployed publicly.

The user also reported a backwards-facing character-selection preview and
missing hair exposing the head's interior. Root confirmed both in the actual
exported `browser-finisher-hover-root/account-select.png` capture. The selected
original `HairData00` mesh and skin are now converted onto the Warrior's main
skeleton; all 427 hair vertices follow the compatible head bone. The preview
faces its fixed camera. The reported sword angle came from a 90-degree mismatch
between the converted blade axis and the hand attachment. The source-backed
profile rotation corrects it; a landmark regression rejects the former transform.

Root regenerated the combined content with Blender 5.2.1 and verified the new
client manifest against the isolated conversion. Only the content identity fields
change in the trusted server payload. The resulting Godot actor check passes
**87 checks**, including four texture pixel/import checks and sword landmarks;
the isolated entry screen passes **28 checks** with actual input and a front-facing
render showing the original hair. Wider front/side renders cover equipped idle,
run and all four combo motions. These establish the sampled poses, not continuous
intersection-free or original Granny playback parity. Evidence is under
`.local/p2-hair/actor-check-root/`, `.local/p2-finisher/intro-camera-facing/`, and
`.local/p2-finisher/sword-basis/combined-report.json`.

The offline actor preview also has motion selection, equipment switching, pause
and timeline controls, verified with real viewport input. The combined tools suite
passes 155 checks. Matching R5 modules and Web/Linux packages are being integrated
under `.local/p2-finisher/integration-r5/`. All three matching modules and all four
Web/Linux exports now pass their build/package checks. The actual packaged Warrior
has four skinned, textured meshes; audits retain all 43 actor clips and 226 original
UI images. The new training module passes 95 two-client checks with unchanged
test inputs. Root inspected the exported browser's creation and selection captures:
both face forward with the original hair present.

The first R5 browser run passes 44 checks, then stops because its test assumes
the selected-target subscription is already reflected inside the reducer-completion
callback. The helper now separately checks the exact successful completion and the
exact-life subscribed target row. That correction passes on replay; a separate
clock-estimation issue still prevents the finisher's first-whiff timing prerequisite.
The current helper uses a conservative clock bound from before the real target
click. Its latest run passes 59 checks, then exhausts three ordinary staging
attempts; it does not qualify the browser finisher. See
`integration-r5/browser-finisher-root-causal-clock/` and its unchanged-input record.

The symmetric north-approach replay passes 48 checks through exact target
selection and subscription, then stops before combat because the test helper
passes integer dictionary keys to Playwright's argument serializer. Evidence is
preserved in `integration-r5/browser-finisher-root-symmetric-stage/` with unchanged
inputs and no browser errors. A focused helper correction is in progress; this
run does not qualify the finisher.

After the serialization correction, root independently verified the helper's
real Chromium projection and replayed the exported clients. That run passes
65 checks but fails all three attack-lock staging attempts before combat;
the symmetric approach does synchronize the two dogs' attack times. See
`integration-r5/browser-finisher-root-symmetric-projection/` and its unchanged-input
record. A tighter clock anchor at the actual canvas mousedown is under review.
Root caught a mismatch between the proposed observer's synthetic ACK fields and
the real exported ACK shape before another live replay; the observer must bind
the exact next completion sequence and retain the separately verified target
subscription.

Root subsequently found the actual staging defect: the reduced Web snapshot
omitted the subscribed player's `online` flag, so the authoritative-position
reader rejected every candidate. The corrected projection retains the real
identity/online row and rejects missing, offline, nonfinite and newer-life
inputs. The replay reaches all four combo actions, fifth-input rejection,
65-health surviving area victim and front knockdown on both exported clients.

R6 fixes a game defect as well: JSON-decoded screen-wave event timings arrive
as integral floats, which the original integer-only check rejected. The actual
Web client now triggers the wave once; the distant native viewer reports
`out_of_range`. The 73-check R6 replay also verifies rendered knockback progress
on both clients. Its remaining failure exposed a probe lookup for `CameraRig`
instead of the real scene's `OrbitCamera`, leaving the transient history empty.
The corrected probe passes a test against an instance of the actual main scene;
the focused Godot suite initially passes **109 checks**. R7 packages include
this correction. These runs are preserved under
`integration-r6/browser-finisher-root-wavefix/` and
`integration-r6/browser-finisher-root-interpolated-force/`; neither is a complete
Slice D acceptance run.

The R7 `browser-finisher-root-applied-camera` replay passes 80 checks through
combat, including exact 4.732 m force history, standup, root convergence and
multiple samples applied to the actual camera. Cleanup exposed the helper's
incorrect assumption that unequip returns to the former bag slot; it now uses
the subscribed slot and explicitly restores the incoming page/slot via UI.
The next replay reaches 92 checks before a native snapshot file read races the
probe's in-place write. R8 replaces snapshots atomically. The real Godot
old-reader/new-reader regression and relevant component suite pass **112
checks**; the Python snapshot/motion regressions pass ten tests. Repository tool tests separately
pass 161 checks, and the rebuild catalog remains valid at 41 systems/194 records.

The final R8 `browser-finisher-root-combat-lifecycle` replay passes **154 checks**
with unchanged tested inputs and no browser engine errors. Both clients retain
exact 4.731999505 m force travel, the front knockdown/standup sequence and the
fourth root endpoint after target clear/unequip. The real camera applies multiple
wave samples; the distant viewer stays unaffected. Both real session timers
refresh with zero XYZ drift across 54 observations and no DOM input events.
Atomic native snapshot reads need no retries. The report SHA-256 is
`f9585c8f8e87b8841df5dcdac7adce98b0f6f6f79c906cecf88b29f0486f81c7`.
The only subsequent runner change rejects incompatible Yongan-panel/finisher
flags before startup; its focused CLI check passes. The acceptance record
documents this change, exact packages and limits. The separate Yongan panel
evidence remains the 113-check report below; the training fixture has no map
metadata and is not a valid minimap-zoom test.

The knockback test now distinguishes moving interpolation from final placement:
it requires actual renderer movement along the same exact-life/action force
path, bounds lag using the client's 12/s smoothing and server's 50 ms steps,
then requires 5 cm convergence during standup. Five Python regressions reject
static, off-path, overshooting, stale-action and missing-renderer evidence.

The separate R5 Yongan hardware-Chrome/Linux run passes **113 checks**, including
equipped actor/attack projection, movement in both directions, inventory and panels,
character switching, disconnect/reconnect, login and both real session-refresh
timers. Both clients finish with nine map chunks and no content error; the browser
error list is empty. Root reviewed the exported equipped idle/attack captures.
See `integration-r5/browser-yongan-root/report.json` (SHA-256
`c5294b14196b2a82657e4f1b15495ab88271a00b9fdfb9b9298fff248c15e77c`)
and `integration-r5/visual-review-root.json`. The visual corrections are verified
locally. Slice D browser acceptance is now complete; public publication remains
outstanding.

Next-milestone preparation is staged under `.local/p2-physical/`. Root combined
the physical-damage runtime with the schema-6 content generator in the isolated
`integration-server` tree: **104 Rust unit, 6 builder and 2 generated-definition
tests pass**, along with strict Clippy for all targets/features. The compiler
stage passes ten checks, including nonfinite/overflow inputs, exact source rows,
and values that only round to the selected multiplier. Running the actual
compiled Rust generator against 46 temporary input cases independently verifies
repeat output and malformed-value/provenance/duplicate rejection. The separate classic
Status/weapon-tooltip component stage passes eleven checks in headless and
rendered Godot runs using synthetic inputs, and the protocol gate passes four
checks. Root reviewed the canonical starting Attack 28–31 / Defense 5 render
and Sword tooltip 13–15. This is not live server evidence.
These stages do not change current gameplay balance and are not integrated into
the active database or exported packages.

Development now proceeds directly in the primary agent, following the user's
request to stop subagent implementation. Existing staged work is retained.

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
