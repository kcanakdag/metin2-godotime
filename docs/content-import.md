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
`mt2spacetime.trusted-action-definitions` **schema 2**. Schema 2 adds the
selected source-derived Warrior progression definitions: levels 0 through 120,
the default cap of 99, EXP and level-delta tables, quarter thresholds, and the
bounded constants used by server progression. It is server input, not an
exported client resource. Its `gameplay_definition_hash` must exactly equal the
client presentation manifest's value.

The verified local rebuild records content hash
`28ef6604c09daf6df371fdde1b09ae8b8b508302ba8bade5c38918b824d49c8f` and
gameplay-definition hash
`7719eec33753a367bb594e38181331dec359c5ec235db53b57d563d72bffbb35` in
`.local/p2/content-rebuild-report.json`. `python3 tools/content_compile.py
validate --profile content/profiles/p0-warrior-dog.json` accepted that current
artifact. This proves the selected definitions and presentation artifacts agree;
it does not prove a server publish, player export, or full-game progression
parity.

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
