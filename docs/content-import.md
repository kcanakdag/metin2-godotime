# P1 presentation fixture and P2 trusted content

For the shared stationary-NPC converter, rigid accessory skinning and map
population preview, see [world-content authoring](world-content.md). Quests are
deferred; these tools support the current gameplay and map-population work.

The `p0-warrior-dog` profile is the selected content fixture used by the P1
presentation and bounded P2 progression slice. It contains one male Warrior
(`race_id` 0), starter Sword+0 (`vnum` 10), and Wild Dog (`vnum` 101). It is not
a general asset importer, a claim of complete original-content coverage, or a
license to redistribute the original archive.

```sh
make content-build BLENDER=/path/to/blender
make content-validate
make content-probe
make test-actors
```

`content-build` resolves only declared pinned inputs, normalizes them, runs
Blender in the background for GLB conversion, and writes ignored generated
output. The first build can fetch declared source inputs; use the compiler's
`--offline` form only after they are cached. `content-validate` checks the
normalized records, generated GLB hashes, and the compatible trusted action
definitions. `content-probe` imports generated GLBs in a fresh headless Godot
project. `test-actors` stages actor presentation and checks selected motion and
attachment resources; `make test-actors UI_FLAGS=--native` also captures the
rendered fixture when `xvfb-run` is available. The default remains fully
headless. To run the isolated editor 3D texture-policy negative control, use
`make test-actors UI_FLAGS=--texture-editor-check`; it requires `xvfb-run` and
records whether it ran in the ignored actor-test report.

For future items, quests, mobs and classes, follow the
[content authoring contract](rebuild/content-authoring.md). It describes the
generalization still needed and distinguishes focused content/preview checks
from combat/network regressions and full release qualification.

## Compare a content update

Save the generated server/client manifests before rebuilding, then use the
existing compiler's `diff` command to identify the changed fields and relevant QA:

```sh
python3 tools/content_compile.py diff \
  --before-server /path/to/baseline/actions.v1.json \
  --before-client /path/to/baseline/manifest.v1.json \
  --after-server server/content/p0-warrior-dog/actions.v1.json \
  --after-client client/assets/imported/content/p0-warrior-dog/manifest.v1.json \
  --output .local/content-change-report.json
```

The report distinguishes gameplay, presentation, combined, provenance-only and
unchanged pairs. It compares actual fields and ordered sequences, verifies the
declared server/artifact-record digests and matching client/server identities,
and records input file hashes. An action-timing, physical-stat or combo-order
change requests affected gameplay and two-client checks; a visual-only change
requests the relevant asset/animation preview and exported-rendering checks.
Source-hash changes remain visible even when runtime fields are identical.

This supports trusted-definition schemas 5/6/7 and presentation schema 1. Unknown
schemas, stale hashes, mixed pairs, duplicate JSON keys and non-finite numbers
fail comparison. The report is guidance: run `content-validate` separately to
verify the content contract and actual referenced assets. Changes to code,
network lifecycle or map bakes need their own checks; release qualification
still includes broader integration.

## Artifact boundary

The generated player-facing manifest is
`client/assets/imported/content/p0-warrior-dog/manifest.v1.json`. It remains
`mt2spacetime.presentation-manifest` schema 1 and records the profile,
source-content hash, gameplay-definition hash, presentation-output hash, exact
GLB hashes, and structural counts. Slice D adds three declared Wild Dog reaction
clips. The subsequent visual correction also regenerates the Warrior GLB with
the selected original hair mesh and texture, and corrects the sword attachment
transform. See the current hashes and exported evidence in the
[implementation status](rebuild/implementation-status.md). No original archive
or raw Granny/Blender asset is shipped.

The server consumes the separate, ignored
`server/content/p0-warrior-dog/actions.v1.json`. The filename is retained for
its stable runtime path, but its payload is now
`mt2spacetime.trusted-action-definitions` **schema 7**. Schema 7 adds the typed
item registry and shared gradual-recovery policy. It retains the
source-derived Warrior progression definitions and selects the default type-0
`combo_1`, `combo_2`, `combo_3`, `combo_4` Sword+0 chain. The trusted payload
contains exactly six attacks: the player general attack, those four combo
actions, and the Wild Dog attack. Only the first three ordered combo actions carry exact integer
`pre_input_us`, `direct_input_us`, `input_limit_us`, and `link_us` fields.
Terminal `combo_4` deliberately retains its nonordered source timing as evidence
and has no follow-up input. The file is server input, not an exported client resource. Its
`gameplay_definition_hash` must exactly equal the client presentation
manifest's value.

Compiler `content-compiler-v1.6.0` also derives selected physical values from
the pinned item/mob proto columns and records the formula/display references.
Declared client code references are fetched and hash-verified alongside server
references, including on a fresh checkout. They remain ignored source inputs.

The explicit `item_catalog` selector adds item records independently of GLB
conversion. Its current supported mechanics are one-hand swords and gradual
HP/SP recovery. The compiler validates references and the Rust build validates
the same registry independently. `content-validate` additionally checks that
the public item catalog matches the server and that required icons/equipped
presentations exist. See [item authoring](rebuild/content-authoring.md#implemented-item-authoring).
The public Sword dictionary contains only `power_min`, `power_max` and
`refine_attack`; private character Attack/Defense values arrive through the
owner-filtered server progression row. These are still selected fixture
definitions, not a general item registry or quest runtime.

The compiler requires every declared one-hand chain to share the distinct
three-action prefix, selects `combo_4` only from the declared default chain,
resolves each selected motion exactly once, and requires
`0 <= pre < direct < limit <= duration`. It reads the pinned raw GR2 metadata
with the pinned Carbon reader before the higher-level animation graph drops the
accumulation fields. Each selected file must have one animation, one `Bip01`
track group, `AccumulationFlags = 3`, a finite bounded `LoopTranslation`, zero
vertical output displacement, and explicit null `PeriodicLoop` and
`RootMotion`. Its raw duration must round to the MSA/action duration. The MSA
`Accumulation` value is a corroborating two-decimal-centimetre value and may
differ by at most 50 micrometres per component.

The fixed policy is `linear-endpoint-approx-v1`. Source centimetres `(x,y,z)`
map to Godot metres `(x,z,-y)/100`, followed by the fixture's 180-degree yaw
exactly once. The resulting actor-local `(x,z)` endpoints are
`(0,-1.317569580078125)`, `(0,-0.852515640258789)`,
`(0,-1.4301394653320312)`, and `(0,-1.1964712524414063)` over `1,000,000`,
`933,333`, `1,066,667`, and `1,266,667` microseconds. The compiler derives
these values from four pinned GR2 inputs. The first three MSA accumulations
remain strict corroboration. Combo 4 has one pinned exception: its raw GR2
endpoint is authoritative while its original MSA accumulation
`(0.1289,0,-1.0552)` and exact discrepancy remain evidence. Raw evidence is stored as bounded decimal strings so Python and Rust
hash the same canonical JSON; runtime endpoint fields remain `f64`. Selected
root durations are limited to 1,600,000 microseconds and endpoint components to
2 metres, matching the bounded server integrator.

Combo 4 also projects its single area sphere and screen wave through the fixed
60 Hz legacy dispatch rule: wave frame 37 activates at 633,334 us, and area
frame 39 activates at 666,667 us. The area lasts 200,000 us, hits each exact
victim life once, applies the separately authored 300,000 us victim cooldown,
and uses a reviewed linear 4.732 m knockback over 1,000,000 us. Ordinary hits
retain their own source cooldowns instead of borrowing the area value. The
player general/combo1/combo2/combo3 values are 500,000/100,000/100,000/200,000
microseconds, and the Wild Dog attack value is 300,000 microseconds. Combo 4
has zero ordinary-hit cooldown because it has no ordinary hit trace. The
screen-wave power/random camera behavior and legacy collision/physics curves
are recorded limitations; this slice does not claim original-client parity.

The Wild Dog fixture adds only front knockdown (32), front standup (33), and
back knockdown (35). Back standup is absent from the pinned race registration
and remains unsupported. Its static collision-type-3 `Bip01` sphere becomes the
bounded full-3D defending-sphere approximation `(0,0.8,0.1), radius 0.9 m`.

The Rust build repeats the prefix, timing, policy, provenance, raw metadata,
event, reaction, defending-sphere, coordinate, duration, and bound checks before emitting `ComboInputDefinition`,
`RootMotionDefinition`, `PLAYER_ONEHAND_COMBO: [AttackDefinition; 4]`, and the
existing `PLAYER_ONEHAND_ATTACK` compatibility alias. General and Wild Dog
attacks have no root definition. `link_us` remains source evidence; it does not
independently schedule gameplay. Original GR2/MSA files and the Carbon runtime
remain development inputs and are not shipped in the server or client.

The preceding area-combat checkpoint used `content-compiler-v1.4.0`. Its repeat
local rebuild recorded content hash
`9ec8aead8c8b6bbd37f4914f1c20371a976a3c07aa5db52d3ece99dbe4e78939` and
gameplay-definition hash
`8f9853748efb45ac0c33dcd716ff2e7f8c58fa208ff6537c75367b8d8ee8eb3c`.
The presentation-output hash is
`b8edc3f0e522a74adb97a0354733635e47213ca56d445a7d31eca4c038a846ca`;
the Wild Dog GLB SHA-256 is
`0455f474cbced95a554af6457efe55d6da0a64d56d0b958e82cd76bb8c5aeb71`.
The coverage records classify combo 4's type-2 event as
`screen-wave-schema5`; combo 7 remains unsupported. Rebuild and validate the
compiler/build boundary with:

```sh
.local/venv-dev/bin/python tools/content_compile.py build --offline \
  --profile content/profiles/p0-warrior-dog.json --blender /path/to/blender
.local/venv-dev/bin/python -m unittest tests.test_metin_root_motion \
  tests.test_combo_content tests.test_content_formats
CARGO_TARGET_DIR=.local/p2-finisher/compiler-target \
  cargo test --manifest-path server/Cargo.toml --test build_combo \
  --test generated_definitions
```

These checks prove the selected normalized data, generated Rust constants, raw
endpoint provenance, and presentation artifact hashes agree. The endpoint is
source-exact, while its linear within-action use is an explicit approximation:
the proprietary Granny within-cycle curve and 100-millisecond transition blend
were not measured. These checks do not prove a server publish, runtime root
integration, player export behavior, or full original-client parity.

P2's Status page reuses selected converted UI textures already in the ignored
UI import output. Missing original status-window artwork remains out of scope:
there is no new raw `.sub`, `.tga`, `.dds`, archive, original Python, or
unreviewed conversion in the client. Any later status-art addition needs a
narrow source descriptor and decoded-pixel provenance in the UI importer before
it can enter a player package.

## Target-selection effect fixture

The target-effect converter is deliberately limited to the two effects used for
actor selection at client revision
`bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7`:
`click_select.mse/.mde` with its two textures and
`click_glow_select.mse/.mde` with its two textures. The first is the transient
actor-hover cue. The second is the persistent accepted combat-target cue and
contains the base alpha layer and additive glow layer at the same time. Both
use 11 discrete mesh frames at 20,000 microseconds and loop indefinitely.

After `python3 tools/dev.py setup`, reproduce the ignored conversion and install
the seven runtime files with pinned Blender 5.2.1 and Godot 4.7.2 executables:

```sh
.local/venv-dev/bin/python tools/import_target_effects.py --fetch --blender /path/to/blender \
  --godot /path/to/godot --geometry-only --install
.local/venv-dev/bin/python tools/test_target_effects.py --godot /path/to/godot \
  --output .local/p2-target/effects/smoke
python3 -m unittest discover -s tests -p test_metin_effect_mesh.py
```

`--fetch` downloads the nine tracked, hash-pinned conversion inputs on the first
online run. The archive reader also downloads `bin/pack/Index` and caches tree
inventory metadata to resolve and verify those paths. The converter provenance
set contains exactly the nine conversion inputs; the Index and inventory
metadata are not converted or installed. Later conversion reads the cached
ignored source tree. There is currently no Make target for this bounded converter.
Development output is written under `.local/p2-target/effects/generated`;
`--install` replaces the ignored
`client/assets/imported/content/p2-target-effects` directory with the runtime
catalog, two GLBs and four PNGs. It never installs MSE/MDE input, a Blender
runtime, conversion reports, material sidecars or source archives.

The parser rejects unsupported effect groups, nested time-event groups,
animated topology or UVs, malformed counts and indices, non-finite values,
truncation and trailing records. The GLB audit checks every source frame and
morph position, ordered UV correspondence, scene transforms and STEP animation.
The runtime smoke checks the source client's strict `< 0` frame boundary,
20-advance cap with retained negative remainder, alpha bytes and actual imported
blend-shape weights. `--render` runs a separate native preview when a display is
available; `--geometry-only` does not claim rendered appearance.

Playable exports require this installed package. The export stage discards live
editor byproducts and copies only the seven authoritative files plus authored
lossless import settings. Its actual-PCK audit loads the packaged runtime catalog,
both remapped scenes and all four textures. It verifies two surfaces, ten blend
shapes, ten nearest/STEP tracks, the 0.22-second loop, all 11 one-hot frame seeks,
and decoded RGBA dimensions and hashes. Any engine-extracted GLB texture copies
are validated and reported separately if the export retains them. These checks
establish the bounded conversion and Godot package contract. They do not establish
pixel-identical rendering or original-client parity.

The converter, preflight and export audit use Pillow 12.1.0 from
`tools/requirements-assets.txt`; the Make export targets invoke the development
virtual environment created by `python3 tools/dev.py setup`.

## Player packages

Player exports package presentation data and ordinary typed client bindings.
Generated bindings can name progression rows and narrow `/help`, `/xp`, and
`/level` reducer calls; that metadata conveys no capability. The server alone
validates identity, selected-character control, the fixed capability, arguments,
and subscriptions. Player packages contain neither bootstrap identities nor
capability/audit data, and no operator CLI/driver or generic evaluator.

The isolated export stage strips the MCP editor/runtime bridges and tests, then
the actual-PCK audit rejects developer and private material: identity/session
files and local logs, `.env`/key/token files, `assets/source`, `server/content`,
original GR2/MSA/MSM/MSS and EPK/EIX assets, Granny/Blender runtimes, Blender
files, archives, original MSE/MDE effects, and test probes in normal exports.
`--test-probe` is a separate
authorized QA export only; it never grants server privileges.

For isolated P1/P2 export QA, retain the default destinations and supply
separate paths, for example:

```sh
.local/venv-dev/bin/python tools/export_playable.py --target web --server http://127.0.0.1:8186 \
  --database mt2-p2-yongan-20260906 --include-map --test-probe \
  --output-dir .local/p2/web-test --work-dir .local/p2/export-web-test
.local/venv-dev/bin/python tools/export_playable.py --target linux --server http://127.0.0.1:8186 \
  --database mt2-p2-yongan-20260906 --include-map --test-probe \
  --output-dir .local/p2/linux-test --work-dir .local/p2/export-linux-test
```

`--output-dir` changes only the completed artifact destination; `--work-dir`
contains staging, imports, and audit logs. Existing files in an explicit output
directory are replaced by that export. Omit `--test-probe` for a normal player
export. `mt2-p2-yongan-20260906` is the disposable, default-deny Yongan export
candidate; it is not the public P1 database and these commands do not provision
an operator. The separate training-map database
`mt2-p2-progression-20260906` remains preserved for the pending bootstrap
approval and must not be repurposed for export qualification.

The profile records 27 Warrior and 13 Wild Dog motion records. It validates
converted artifacts and source-derived action/progression metadata. It does not
establish full server lifecycle QA, two-client acceptance, original visual
parity, Web/Linux export behavior, Windows execution, or complete
class/mob/equipment coverage.

## Classic character import

The [classic character workflow](characters.md) automates selected race-script,
body/hair, material, attachment and weighted-animation discovery for all four
classes and both sexes. Use `make characters-build` rather than hand-assembling
Godot character scenes. It shares the Blender converter, preserves pinned source
hashes and receipts, and packages converted GLB/PNG assets. Adding a motion to the
presentation catalog does not enable unimplemented server mechanics.
