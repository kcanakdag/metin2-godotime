# Selected skills

The first supported ability is Warrior Sword Spin (vnum 2), using the original
male/female `palbang` motions and selected original icon. This is a bounded first
ability, not complete skill-system or original-client parity.

At level 5 a Warrior has one skill point; each subsequent level adds one. Open
Skills with **K** or the character window's Skills tab. The plus button learns
or upgrades the skill, spending one point after server acceptance. Drag a learned
skill to a quickslot and use its number/F-key, or right-click the skill icon.
Ranks currently range from 0 (unlearned) to 20. Sword Spin requires an equipped
sword, spends SP, and has a persistent 15-second cooldown.

Authorized progression operators can use `/level 5` followed by `/skill 2 1`,
or `/skill 2 20` to test the maximum supported rank. `/skill 2 0` unlearns it.
The command targets the operator's selected character, requires the class and
level prerequisites, refunds its invested points, and preserves cooldown and an
already accepted cast. Commands share the existing one-second rate limit, private
feedback, request receipts and audit trail. Ordinary accounts cannot grant ranks.

## Content pipeline

Run the existing pinned base-actor, character and UI importers first:

```sh
make content-build BLENDER=/path/to/blender
make characters-build BLENDER=/path/to/blender
make import-ui
make skills-build
```

`content/profiles/classic-skills.json` selects definitions. Character profiles
select the required motions, converted offline through Blender into GLB clips.
`tools/build_skill_catalog.py` reads pinned English `skilltable.txt`,
`skilldesc.txt` and the client international power table. It compiles restricted
arithmetic into bounded coefficients; it never executes source expressions.
The resulting ignored `client/assets/imported/skills/catalog.v1.json` connects
class, rank limits, cost, cooldown, original motion IDs and the shared
`physical_splash_v1` handler. The Rust build validates and embeds those definitions.
Rebuild the server and matching exports after changing shared skill content.

Protocol 16 includes the exact skill-catalog hash in WorldInfo. The Godot content
gate rejects mismatches, and actual PCK audits verify the packaged hash alongside
the existing model, animation and exact UI-pixel audits.

## Authority and current limits

`character_skill` is owner-private and stores rank, invested points, revision and
cooldown. Learning and casting carry the subscribed revision. The server validates
class, level, points, equipment, life, active controller, SP and action timing.
Pending casts capture rank, attacker stats, connection, action revision and life;
disconnect, replacement or death prevents later damage from that cast. Each exact
monster life can receive one hit, at most 12 targets within the selected two-metre
radius and collision-clear path. Damage uses the existing PvE credit/reward path.

The selected English gameplay formula differs from its tooltip formula and from
other locale tables. We explicitly use the English gameplay row with the pinned
international rank powers. Rank 20 uses power 50%; random Master promotion,
books, higher grades and specialization selection remain unimplemented.
The present handler targets the supported Wild Dog physical model. Other skills,
PvP policies, casting-speed modifiers and passive SP regeneration remain pending.

The original two-second animation plays at rate 1.0 independently of sword attack
speed. Its MSA endpoint supplies bounded linear root displacement; the exact GR2
root curve is not reproduced. Original skill particles and its external-force
reaction are also pending. The skill panel uses original art but is an interim
single-ability layout, not the complete original skill-page layout.

## Qualification

`tools/test_progression_admin.py skills` follows the existing `prepare` and
restricted local bootstrap workflow on a fresh disposable database. It checks
level-5 learning, point spending, replay rejection, SP cost, remote action updates,
private state, developer rank updates, cooldown and reconnect persistence.
The subsequent `skill_combat` phase expects that character at level 5/rank 20;
it raises level to 6 through the authorized command, approaches a real Yongan dog,
and checks bidirectional movement, damage replication and one hit per life.
Do not rerun these progression-mutating phases against their already advanced
state as though it were a fresh fixture; preserve the database and use a new name.

Native UI checks: `tools/test_target_client.py --suite skills_ui --native`.
Actor checks: `tools/test_actors.py --native`, including both Warrior skill clips.
These component checks are distinct from exported browser input evidence.
