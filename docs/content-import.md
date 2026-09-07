# P1 presentation fixture and P2 trusted content

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
rendered fixture when `xvfb-run` is available.

## Artifact boundary

The generated player-facing manifest is
`client/assets/imported/content/p0-warrior-dog/manifest.v1.json`. It remains
`mt2spacetime.presentation-manifest` schema 1 and records the profile,
source-content hash, gameplay-definition hash, presentation-output hash, exact
GLB hashes, and structural counts. The current P2 rebuild preserved that
presentation output hash (`2bcd691596bfb76f90359955a6469eda9a5a2d65045d00452f3b66fcc699c839`)
and all three GLB hashes. P2 did not add a model, texture, original archive, or
raw Granny/Blender asset to the player fixture.

The server consumes the separate, ignored
`server/content/p0-warrior-dog/actions.v1.json`. The filename is retained for
its stable runtime path, but its payload is now
`mt2spacetime.trusted-action-definitions` **schema 4**. Schema 4 retains the
source-derived Warrior progression definitions and selects the common
`combo_1`, `combo_2`, `combo_3` Sword+0 prefix. The trusted payload contains
exactly five attacks: the player general attack, those three combo actions, and
the Wild Dog attack. Only the three ordered combo actions carry exact integer
`pre_input_us`, `direct_input_us`, `input_limit_us`, and `link_us` fields.
Later declared presentation actions, including the terminal `combo_4` record
whose source timing fields are inverted, stay outside this bounded trusted
prefix. The file is server input, not an exported client resource. Its
`gameplay_definition_hash` must exactly equal the client presentation
manifest's value.

The compiler requires every declared one-hand chain to share the distinct
three-action prefix, resolves each selected motion exactly once, and requires
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
`(0,-1.317569580078125)`, `(0,-0.852515640258789)`, and
`(0,-1.4301394653320312)` over `1,000,000`, `933,333`, and `1,066,667`
microseconds. The compiler derives these values from the three pinned GR2
inputs. Raw evidence is stored as bounded decimal strings so Python and Rust
hash the same canonical JSON; runtime endpoint fields remain `f64`. Selected
root durations are limited to 1,600,000 microseconds and endpoint components to
2 metres, matching the bounded server integrator.

The Rust build repeats the prefix, timing, policy, provenance, raw metadata,
coordinate, duration, and bound checks before emitting `ComboInputDefinition`,
`RootMotionDefinition`, `PLAYER_ONEHAND_COMBO: [AttackDefinition; 3]`, and the
existing `PLAYER_ONEHAND_ATTACK` compatibility alias. General and Wild Dog
attacks have no root definition. `link_us` remains source evidence; it does not
independently schedule gameplay. Original GR2/MSA files and the Carbon runtime
remain development inputs and are not shipped in the server or client.

The compiler version is `content-compiler-v1.3.0`. The verified repeat local
rebuild records content hash
`c31bf7b0bf6afbf79d54f70d5bd20e8047cd39ce3ea14783ae8df79441a61e9f` and
gameplay-definition hash
`2f096ae82998eeecb839df391a7350f8309e477a7004ef4c2e333167bc4ada8d`.
The presentation-output hash remains
`2bcd691596bfb76f90359955a6469eda9a5a2d65045d00452f3b66fcc699c839`,
and all three GLB hashes remain byte-for-byte unchanged from the accepted Slice
A inputs. Rebuild and validate the compiler/build boundary with:

```sh
.local/venv-dev/bin/python tools/content_compile.py build --offline \
  --profile content/profiles/p0-warrior-dog.json --blender /path/to/blender
.local/venv-dev/bin/python -m unittest tests.test_metin_root_motion \
  tests.test_combo_content tests.test_content_formats
CARGO_TARGET_DIR=.local/p2-rootmotion/compiler-target \
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
