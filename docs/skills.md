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

## Full classic ability pipeline in progress

The completion target is all 44 abilities playable across the four classes and
eight trees. Converted animations and evaluated formulas alone do not satisfy
that target. Each ability needs learning/upgrades, validated casting, its actual
damage/healing/buff behavior, matching presentation and two-client evidence.
The authored [training dummy](training-dummy.md) is available for repeatable
hostile-target practice; friendly-target and healing abilities also need player
fixtures. Definition changes should reuse shared handlers, with new code reserved
for genuinely new mechanics. Balance customization must remain in reviewed
profiles and participate in the client/server content hash.

The candidate pipeline discovers 44 skills across four classes/eight trees and
selects 88 normal-grade motions for both appearances. `tools/discover_skills.py`
reads pinned registrations/table/descriptions without executing legacy scripts;
`tools/import_character_content.py` converts that explicit selection in Blender.
`tools/build_class_skills.py` links the converted motion metadata to skill data,
and `tools/test_class_skill_catalog.py` compiles and evaluates restricted formulas
through Rust. The candidate schema is version 2; the live Sword Spin catalog is
still version 1. Do not install the candidate as if every mechanic were supported.

The converted package passed 625 native motion checks. The formula compiler passed
21,120 evaluations, covering all skills/ranks with bounded random extrema. These
are asset/compiler checks, not evidence that all abilities can be cast in game.
Shared gameplay handlers, specialization selection, bow/dagger equipment, timed
buffs/status effects, friendly targeting, UI integration and multiplayer acceptance
are still required. The requested scope remains all classic abilities.

The candidate Rust compiler preserves the source damage attribute (normal, melee,
ranged or magic), primary/secondary affect identifiers, learning limits and the
catalog's rank-power table. Shared handlers must consume these fields when they
are integrated; an imported skill must not silently become physical damage or lose
its secondary buff. Unknown damage attributes, malformed affect IDs and invalid
rank progression fail compilation. This remains candidate tooling, not additional
live skills.

Qualify a linked catalog before integration:

```sh
python3 tools/test_class_skill_catalog.py --catalog /path/to/catalog.v2.json \
  --output .local/class-skill-qualification
cargo test --manifest-path server/Cargo.toml --features yongan --offline \
  --example compile_class_skills
```

The runner executes generated Rust, compares all 44 skills' mechanic metadata to
the input, and uses the compiled rank powers for formula evaluation. Its receipt
binds the catalog, compiler, interpreter and harness; changes during the run fail
qualification. The current candidate passes 21,120 formula evaluations and 221
metadata assertions. These checks do not replace two-client casting tests.

Five Shaman normal registrations reference missing filenames in the pinned pack.
The discovery tool explicitly selects the available `_me.msa` self-cast variant
for Blessing, Reflect, Dragon Strength, Cure and Swiftness and records the original
registration separately. This does not establish targeted-cast animation parity.
MSA import also preserves source attack-area lifetime after the clip, bounded to
ten seconds after activation, following `ProcessMotionEventSpecialAttacking`.

Candidate skill balance changes belong in `content/profiles/classic-skill-tuning.json`,
not edited archives or generated Rust. An override such as
`{"vnum":2,"values":{"sp_cost":"40+100*k","splash_radius_cm":300}}` goes in its
`overrides` list. The linker accepts `--tuning PATH`, recompiles changed formulas,
and records the selected tuning in the catalog hash. Names/descriptions, damage,
cost/duration/cooldown/upkeep formulas, ranges and target limits are bounded;
mechanic/identity changes are rejected and need a shared handler. This tuning is
for the candidate full-class schema and does not silently alter live Sword Spin.

### Multi-hit timing integration

The candidate Rust compiler now preserves `hit_windows_us` on each generated
`ClassSkillMotion`, in source event order. Each interval must start at a registered
activation, finish no earlier than it starts, and stay within the existing bound
of ten seconds beyond the animation. Unknown event kinds and missing hit lists
reject; non-attack motions retain empty lists. Three-Way Cut's three independent
windows therefore survive compilation instead of becoming activation-only data.

The qualification harness executes 88 interval comparisons against the input
catalog alongside 21,120 formula and 221 mechanic metadata checks. Four compiler
unit tests pass, including malformed intervals. Evidence is in
`.local/p6-skill-windows-r1/qualification-r2/`. This is candidate compiler work:
the live cast resolver still uses the single Sword Spin envelope and must be
extended to consume these intervals, collision shapes and original hit limits.

The server's shared `skill_hits` ledger now admits hits by monster ID, life and
motion event, with independent per-life and total-hit limits. Event zero keeps
the persisted `monster:life` receipt format; later events add an event suffix.
Sword Spin uses event zero, a per-life limit of one and its existing total budget,
so its accepted-hit policy remains unchanged. Receipt admission does not mutate
state; the resolver records a receipt only after damage calculation succeeds.
Three-event repeat limits, duplicate event rejection, respawn identity and invalid
receipts/limits have focused unit coverage. This prepares shared runtime admission;
additional skills still need event scheduling, collision geometry and live QA.

Candidate motions also retain a `hit_geometry` entry aligned with every hit window:
actor-local sphere lists for attack areas, or the named bone and length for weapon
windows. The compiler validates coordinate space, finite bounded coordinates,
positive sphere radii and bounded geometry lists. Explicit empty-bone/zero-length
weapon windows remain as authored; no fallback shape is invented. The qualification
harness compares all 88 generated geometry arrays to input records and hashes the
separate geometry compiler as an input. Six compiler tests pass. Runtime shape
sampling, attack/reaction parameters and two-client acceptance remain pending.

The server's existing fixed-area combo resolver now shares `combat_geometry`
rotation and full-3D sphere-sweep math with future skill resolution. The checked
intersection entry point rejects nonfinite input, negative radii and overflow;
ordinary finite geometry retains the previous inclusive boundary and crossing
behavior. Eight existing area tests and two geometry tests pass. Compiled skill
shapes are not yet dispatched through this runtime path; multi-event activation
state and original hit/reaction policies remain to be integrated.

The live resolver now uses the shared bounded `skill_hits::active_events` selector
for its existing saved interval. The selector preserves gaps and overlapping event
IDs, returns no expired events, supports at most 32 events, and retains the live
inclusive-endpoint contract. It does not synthesize missed damage after a stall.
The qualification executable runs both compiled Three-Way Cut appearances through
this same selector and hit ledger: repeated ticks within each interval yield exactly
three distinct receipts. This replay assumes a hit-eligible target; it does not
prove collision, damage, network casting or animation fidelity. Pending cast state
still contains the original single interval until multi-event capture is integrated.

Accepted casts now convert authored event offsets to absolute deadlines through
`skill_hits::capture_events` before gameplay mutations. The shared capture rejects
negative clocks, overflow and out-of-motion offsets as a whole. The existing
Sword Spin stores the same single captured interval; no pending-table schema has
changed. Both compiled Three-Way Cut timing replays now use a nonzero captured
clock rather than only relative offsets. Seven focused skill tests pass, including
late invalid intervals and clock overflow. Full multi-event persistence, activation
positions and collision dispatch remain pending. The installed actor package lacks
`skill_1`; its two motions exist in the separate candidate character package and
must be installed with matching client/server content hashes for the live rollout.

The candidate generated `SkillHitGeometry` now resolves fixed attack areas through
the shared server rotation and full-3D sphere sweep. It validates placement and
returns an error for weapon windows, which require sampled attachment geometry.
The qualification executable combines the compiled Three-Way Cut shapes, captured
clock, event selection and exact-life ledger for both appearances at two headings.
Front targets yield three distinct receipts; rear/elevated targets miss and repeated
ticks do not add hits. This is an offline collision/admission replay: it does not
run server subscriptions, damage, knockback, activation capture or the client.
Evidence: `.local/p6-skill-area-r1/`. Six compiler tests also pass.

Protocol 25 now persists the ordered event list and per-life hit limit in
`pending_skill`. The resolver selects each active event and uses its event ID for
hit deduplication, retaining controller/action/life cancellation. Sword Spin still
captures one event with a one-hit-per-life limit. Generated Godot bindings include
the nested `SkillEventTiming` type; an actual BSATN round-trip preserves event
order/timing. This requires a fresh database rather than destructive migration of
the public world. Three-Way Cut content and fixed-area activation dispatch are
still pending; the schema alone does not make it playable.

Protocol-25 Sword Spin runtime acceptance now passes on a fresh local Yongan
world: 35 authenticated skill checks plus 15 real combat checks, including damage
observed by both clients and one hit per monster life. Evidence:
`.local/p6-skill-cast-r1/acceptance.json`. These are headless Godot clients, not
rendered browser exports; additional abilities remain disabled. The isolated QA
module contains a local bootstrap identity and must not be used for public rollout.

The all-class motion package is now installed locally using the preserved Blender
conversion and current catalog generator. All 236 previous motion records survive
exactly, and the package exposes 88 skill motions. The actual native class-skill
scenario passes 625 checks; both Three-Way Cut appearance captures were reviewed.
Those captures are pose-only and do not include equipped swords. The skill linker
now prefers installed character definitions over the legacy base actor, matching
the client; an offline rebuild proves Sword Spin's current skill catalog unchanged.
Evidence: `.local/p6-skill-install-r1/acceptance.json`. The character catalog hash
changed and needs a matching module/export rollout; this does not enable skills.

Live schema-v1 motion variants may now provide `hit_windows_us` as an ordered
list of `[start,end]` microsecond pairs. Omission preserves the existing single
`hit_start_us`/`hit_end_us` interval. The compiler rejects empty/oversized lists,
invalid pairs, duplicate/unordered starts and a list whose bounds differ from the
action envelope. It emits per-skill/per-appearance event lists, and accepted casts
capture these exact lists into pending state. This does not imply that radial
handlers support source-faithful multi-hit geometry; the new area handler must
still be integrated before enabling Three-Way Cut. Eight runtime and three live
compiler tests pass; no additional multiplayer run accompanied this local change.

Live skill profiles may specify `hits_per_life` (integer 1–32); omission retains
one. The Python linker and Rust compiler both validate the bound, and acceptance
captures the generated value in pending state. Later definition/rank changes do
not rewrite a saved cast's repeat limit. Event deduplication and the total hit
budget still apply independently. The installed Sword Spin catalog remains
byte-identical with a limit of one. Four live compiler and eight runtime tests pass;
this local change has not enabled Three-Way Cut or been published.

Fixed-area activation now shares `area_lifecycle` with the existing combo finisher:
placement captures the activation position/heading, scanning starts after the
activation tick, and the area expires at its deadline. Compiled Three-Way Cut
replays use that same lifecycle with saved placements, then apply the shared
geometry and receipt checks. Four area replays and ten focused Rust area checks
pass; strict Clippy passes. Evidence: `.local/p6-area-lifecycle-r1/`. The live skill
pending state still needs these per-event placements before fixed-area dispatch
can be enabled; the existing combo uses the shared lifecycle now.

### Protocol-26 placement state

Each persisted skill event now carries an optional activation placement and a
list of exact-life target samples. Activation captures origin and heading before
the tick's normal root-motion advancement, once per event, after verifying the
controller lease, connection, action revision and owner life. Catalog-selected fixed areas now seed and refresh the target list and resolve
sweeps against frozen per-event placement; activation ticks do not deal area hits.
Sword Spin retains its radial resolver. The fresh local database
`mt2-p2-area-state-v26-r1-20260908` passes 35 skill and 15 combat checks with two
authenticated clients; this does not establish Three-Way Cut or browser fidelity.
The module in `.local/p6-area-state-r1/module.wasm` embeds local QA authorization
and must not be deployed publicly.

### Fixed-area authoring and runtime

The live linker accepts `physical_area_v1` alongside the existing radial handler.
It preserves ordered source `attack_area` events, windows and full event metadata.
The Rust compiler requires exactly one valid geometry record per event and rejects
weapon windows in this handler, missing shapes and geometry silently attached to
radial skills. The resolver samples validated defending spheres, uses exact-life
identity for previous centers, skips activation ticks and expires areas exclusively.
Samples are sorted for binary lookup and removed lives are discarded each scan.
The existing damage receipt limits apply after collision qualification.

Candidate Three-Way Cut plus Sword Spin compiles at
`.local/p6-live-area-r1/catalog.v1.json`; the installed catalog remains Sword Spin
only. Required-target acceptance, source hit reactions/knockback, event dispatch
quantization and original icon integration remain unfinished. Geometry compilation
and pure resolver tests do not establish live Three-Way Cut or visual fidelity.

To check a candidate without changing the installed catalog:

```sh
cargo run --manifest-path server/Cargo.toml --locked --offline \
  --example compile_live_skills -- candidate.json /tmp/live-skill-definitions.rs
```

Use `--installed` in place of the input path to compile the installed catalog.
The geometry enum has a narrow generated `dead_code` allowance because selected
catalogs can omit either kind; the compiler and runtime still reject unsupported
weapon windows for the fixed-area handler. No checks are disabled globally.

### Authored area hit responses

Each fixed-area event now compiles its GOOD/GREAT type, invulnerability duration
and external force. Runtime rejection during an existing hit cooldown leaves the
event eligible for a later scan, without recording a damage receipt. Accepted hits
set their authored cooldown (zero adds none); lethal hits use ordinary death cleanup.
Surviving GREAT hits cancel the victim's pending attack and enter the shared force/
knockdown/recovery path. GOOD flinch animation is still missing and is not claimed.

Three-Way Cut's original events use GOOD/100 ms/force 0 twice, then GREAT/500 ms/
force 5. The unit-mass, friction-0.3 endpoint calculation produces 0.392 m for force
5 and reproduces existing force-15/17 endpoints. Movement uses the existing one-
second server ease-out and collision clipping; the original client uses a different
interpolation path, so exact physical parity is still pending. Source references:
pinned client `GameLib/GameType.h`, `ActorInstanceBattle.cpp` and `PhysicsObject.cpp`
at `bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7`; no reference code was copied.

The compiler explicitly rejects nonzero stiffen, GOOD pushes, unsupported hit
kinds, non-splash/non-area policies and out-of-range values. Those features need
separate implementations before their content can be enabled. Ten focused skill
tests, seven compiler tests and strict library/example Clippy qualify this code;
the prior 50 Sword Spin client checks cover the preceding build. Three-Way Cut
is not installed, deployed or qualified in two real clients by this change.
