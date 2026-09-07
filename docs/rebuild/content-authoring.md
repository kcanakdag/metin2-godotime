# Extensible content authoring

This is an architecture requirement for the upcoming generalization work.
The current compiler and runtime still select the Warrior/Sword/Wild Dog
fixture; general item, quest, class and content-pack authoring is not implemented.

Adding content that uses supported mechanics must require definitions and assets,
without adding item-ID, quest-ID or class-ID branches throughout gameplay code.
Adding a new mechanic introduces one reusable, validated handler. Definitions
select handlers; they cannot execute arbitrary client or server scripts.

## Definitions and state

Keep reviewed, versioned authoring records separate from generated artifacts and
mutable SpacetimeDB rows. Use stable namespaced IDs and explicit schema versions.
The compiler resolves references and emits typed server definitions plus a
separate public Godot manifest. Adding rows under an existing schema should not
require database schema changes or regenerated network bindings.

| Content | Definition data | Mutable server state |
| --- | --- | --- |
| Item | Category, stack/size limits, equipment requirements, stats, supported use effects, prices, icon/model references | Unique instance ID, owner, count, location, upgrades and rolled attributes |
| Quest | Prerequisites, dialogue, objectives, transitions, repeat policy and rewards | Character, accepted definition revision, active state, objective counters, timers and completion/claim identity |
| Mob | Stats, behavior profile, motion set, drops and spawn references | Spawn/life identity, health, target, action and position |
| Class | Base stats, growth, supported equipment/motion sets and skill definitions | Character selection, learned skills, allocated stats and cooldowns |

Reused mechanics include typed objective handlers such as killing a specified
mob, talking to an NPC and handing in items; and typed effects such as healing,
granting experience or creating an item. Unsupported handlers fail validation.
Conditions and transitions must have bounded complexity and execution cost.

An illustrative quest record could contain:

```json
{
  "schema_version": 1,
  "id": "quest.shinsoo.first_hunt",
  "revision": 1,
  "prerequisites": [{"type": "minimum_level", "value": 1}],
  "objectives": [
    {"id": "dogs", "type": "kill_mob", "mob_id": "actor.mob.wild-dog-101", "count": 5}
  ],
  "completion": {"type": "interact_npc", "npc_id": "npc.shinsoo.guard"},
  "rewards": [{"type": "experience", "amount": 100}]
}
```

This sketches the intended shape; it is not a currently accepted input format
or a claim about original quest rewards. Dialogue and more complex progression
use explicit states and transitions with localization keys.

## Authority and versioning

Quest progress consumes validated server gameplay events. A client can request
interaction or select a dialogue option; it cannot report kills, complete an
objective or grant rewards. Interaction checks include character ownership,
current quest state, NPC identity, map and distance.

Reward checks, item/currency changes and completion records share one reducer
transaction. A persisted completion/claim identity prevents duplicate rewards
after retries and reconnects. Required-item consumption and reward-capacity
checks must succeed together. Keep character quest state and inventory private.

Activate immutable content revisions through the normal reviewed publication
workflow. Existing quests retain their accepted revision until an explicit
migration policy applies. Item rebalance changes need a defined treatment of
existing instances; changing a definition must not silently reset or reinterpret
stored player progress. Hot editing live tables is not the authoring workflow.

Future content packs declare a namespace, version, dependencies and required
mechanic/schema versions. The server selects the enabled packs. Clients load
the matching public artifacts; they cannot enable gameplay rules themselves.

## Authoring tools and verification scope

Extend the existing compiler and previews before building a separate editor.
Validation must cover duplicate IDs, missing references, unsupported handlers,
numeric bounds, item placement rules, unreachable quest states, invalid reward
definitions, asset/skeleton compatibility and content-version compatibility.
Provide inspectable validation errors, dependency/diff reports and previews.
An admin inspector should explain quest state and rejected actions; privileged
changes remain authorized server operations with an audit record.

| Change | Appropriate verification |
| --- | --- |
| Texture, mesh or visual animation using an unchanged gameplay contract | Changed-content validation, rig/attachment checks and Godot preview; affected export format when needed |
| Item, quest or mob definition using existing mechanics | Definition/reference validation and a focused scenario for the changed behavior |
| New mechanic, attack timing/root travel, networking or persistence | Handler tests plus relevant actual two-client regression, including rejection/lifecycle paths that changed |
| Release candidate | Broader exported-client integration, package inspection and intended-endpoint checks |

Classify changes from their generated gameplay/presentation diff. An animation
that changes hit timing or authoritative root travel is a gameplay change.
Routine content work must not depend on rerunning account creation, inventory
dragging and four-minute token refresh unless those contracts are affected.

The first generalization milestone should add a second representative definition
through shared registry lookups, then prove adding another needs no new ID
branches. Preserve the selected original-source fixture as a regression case.
General item effects precede quest reward integration; persisted quest execution
and exact-once reward handling precede bulk quest import and authoring UI.
