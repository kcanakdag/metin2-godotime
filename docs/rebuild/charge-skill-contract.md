# Charge skill implementation contract

Dash is not yet enabled. This records source behavior needed to implement it,
separately from its already qualified model, animation and effect conversion.
It also identifies the shared mechanics needed by later charge/buff abilities.

## Verified source behavior

References below are the local source audit checkouts under
`.cache/full-game-research/{client,server}/source/src/`. The candidate content is
`.local/p6-charge-r1/catalog.v2.json`, SHA-256
`fcaa58701e41faa4e43dd77fe1adb1b2fdb115486ab06d5513f1b2796a16f6bc`.
Do not redistribute the source checkouts with the game.

| Stage | Original behavior | Source location |
| --- | --- | --- |
| Target approach | Melee/charge flags override the raw table range to 170 cm. Distance at or above that range reserves an approach action. A charge sends a target-zero use before approaching, unless that skill is already reserved. | `client/UserInterface/PythonSkill.cpp:1051`, `:1087`; `PythonPlayerSkill.cpp:396` |
| Approach presentation | The out-of-range path returns before `NEW_UseSkill`. The attack motion and targeted use happen after range checks succeed. | `client/UserInterface/PythonPlayerSkill.cpp:594`, `:754` |
| Begin | A target-zero charge use chooses the caster as victim. Self-computation suppresses primary damage and adds the secondary MOV_SPEED affect with the Dash flag. | `server/game/src/char_skill.cpp:2476`, `:2230` |
| Resource payment | Starting the charge follows normal cost/cooldown handling. An already charged targeted use branches before that handling, computes the strike and removes the affect. An immediate targeted use starts the charge recursively if needed. | `server/game/src/char_skill.cpp:2368` |
| Damage timing | The targeted branch calls `ComputeSkill` immediately. It does not schedule a hit at an MSA collision timestamp. | `server/game/src/char_skill.cpp:2383` |
| Damage placement | `FuncSplashDamage` is centered on the selected victim; admission uses original `DISTANCE_APPROX`, battle eligibility and hit accounting. This is not the caster-centered Sword Spin resolver or an animation-local area. | `server/game/src/char_skill.cpp:990`, `:2023` |
| Push/stun | CRUSH pushes 200 cm for a player attacker. The main target is offered a four-second stun through `SkillAttackAffect` with `IMMUNE_STUN`. The block excludes NOMOVE victims. | `server/game/src/char_skill.cpp:1363` |
| Speed | Player MOV_SPEED clamps to 0–200, then uses the original integer duration percentage. | `server/game/src/char.cpp:2844`; `utils.cpp:119` |

The selected Dash definition supplies +150 MOV_SPEED for three seconds, twelve
seconds cooldown, `60+120*k` SP, a 200 cm splash radius and a four-target limit.
Its weapon flags allow SWORD and TWO_HANDED. Party buffer bonuses affect the
original secondary duration; future party integration must preserve that path.
The current live skill handler's sword-only check is not sufficient for Dash.

The full-class Rust compiler now resolves the original melee/charge range
override while retaining the raw table field. This fixes Dash, Ambush and Finger
Strike, whose raw zero previously generated `range_m:0.0`. Other skills retain
their authored ranges. This is a candidate compiler change, not a live rollout.

## Implementation boundaries

The selected catalog now supports `physical_charge_v1` and compiles a typed
`charge_lifecycle::Definition` with duration, speed bonus, push distance and stun.
Rank cost and cooldown remain part of the skill row; `activation_policy` combines
them with that definition for the lifecycle transition. Original collision events
are retained under `source_hit_events` and do not populate charge damage windows.
The live reducer currently rejects a charge definition explicitly. The candidate
is not installed, and persistence, immediate damage and client approach remain
required before removing that gate.

`server/src/charge_lifecycle.rs` now provides pure activation, consumption and
invalidation transitions. Activation returns the remaining SP and next skill
state; consumption returns the captured rank and next state without a second
payment or cooldown restart. Proposals leave their inputs unchanged so the
future reducer adapter can validate all combat conditions before persisting.
The adapter must atomically persist resource/state changes and damage. This
component does not itself establish database atomicity, validate combat targets
or authorize a supplied owner snapshot. It is compiled into the server but not
yet called by a reducer or movement simulation.

Six focused tests cover approach/immediate consumption, repeated activation and
consumption, exclusive expiry, captured owner character/connection/life, stale
revisions, insufficient SP, bounded policy/rank values and arithmetic overflow.
Protocol 26 and the live four-skill catalog remain unchanged. Next integration
requires a persisted charge record, its authoritative client projection, movement
interval handling and the separate immediate damage path described below.

Use a separate, server-owned timed affect/charge record. The current
`PendingSkill` lifetime is tied to an attack action revision and owns animation
hit windows. A charge must survive ordinary approach movement and must not
derive damage timing from that record. Existing candidate Dash motion hits remain
source metadata; their presence does not authorize delayed or repeated damage.

Bind charge state to the owning character life and active controller lease.
Capture the skill rank and duration on acceptance. Resource payment, cooldown,
revision changes and charge insertion must occur in the same reducer transaction.
A target strike must validate its exact target life, range, map and attack
eligibility before consuming charge and applying damage. A rejected strike must
not partially spend, consume, damage or move anything. A replayed strike must
not bypass cooldown after consumption. These are modern server-authority rules;
the original client-side approach check alone is not a sufficient security gate.

Movement must integrate the charged and normal portions of a tick around affect
expiry, preserving the existing anti-stall cap and swept collision. Disconnect,
character switch, death and lease replacement must invalidate the charge.
Network reconnection must not restore a consumed or expired charge.

`movement::Travel::tick` now implements this interval calculation. Its optional
`SpeedEffect` contains only a validated time range and bonus points; deriving it
from a current owner lease remains the adapter's job. Movement consumes at most
the most recent 100 ms after attack recovery. A charge that expired before that
window contributes no boost, even if the simulation was stalled for seconds.
Held and click movement use the same opaque allowance.

Do not delete affect history before accounting for the elapsed movement interval.
Expiry at the current tick still leaves a potentially boosted portion before it.
Likewise, consuming charge between simulation ticks must account for movement up
to the consumption time exactly once. The adapter needs either movement advancement
with a per-character accounted-through timestamp or retained ended-effect history;
blindly passing only currently active affects loses that portion of movement.

Publish the minimal authoritative affect state needed for speed presentation,
the charged icon and the ability to finish a charge during its original cooldown.
The client should reserve an approach/strike intent for an exact target life and
cancel it on manual movement, target loss, world exit or rejection. It must not
grant speed, teleport to the target or infer permission from a local timer.
Server cooldown remains authoritative even though the original client's
`__SendUseSkill` restarts its local cooldown display on each send.

Implement target-centered admission, bounded per-cast victims, CRUSH and stun
through reusable combat/affect policies. Confirm original approximate-distance
rounding, hit-budget ordering, stun immunity and push collision before claiming
physics parity. Do not substitute existing GREAT animation knockback for the
original CRUSH policy without verification.

## Acceptance required before enabling Dash

- Two subscribed clients observe one payment and cooldown start on approach,
  boosted movement, one in-range strike and one charge removal.
- Immediate in-range use pays once and strikes once; ordinary approach does not
  start the attack motion early. Test both Warrior appearances and weapon types.
- Below/at/above 1.7 m target boundaries, moving targets, blocked approach and
  target death/respawn preserve exact-life ownership and never teleport.
- Duplicate requests, stale revisions, insufficient SP, wrong class/weapon and
  unauthorized state changes cannot create extra charge or damage.
- Expiry in the middle of a tick, server stall, death, logout, lease replacement,
  character switch and reconnect preserve movement/resource limits.
- Target-centered splash observes its range and victim budget. Main-target
  stun, immune/NOMOVE targets and collision-limited push are checked separately.
- Regenerate bindings for the eventual schema change in a fresh disposable
  database; verify rejection, subscriptions, disconnect and reconnect before
  touching the public world. Never reset an existing database for this fixture.
- Exported browser gameplay shows approach, strike, effects and cooldown from
  both clients; native actor-only checks do not establish these behaviors.
