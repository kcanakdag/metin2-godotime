# P1 actor content import

The `p0-warrior-dog` profile is the first generated actor/content fixture. It
selects one male Warrior (`race_id` 0), starter Sword+0 (`vnum` 10), and Wild
Dog (`vnum` 101). It is a narrow P1 slice, not a general asset importer or a
claim of full original-content coverage.

```sh
make content-build BLENDER=/path/to/blender
make content-validate
make content-probe
make test-actors
```

`content-build` resolves only the declared, pinned profile inputs, normalizes
them, runs Blender in the background for GLB conversion, and writes ignored
generated output. The first build may fetch declared source inputs; use the
compiler's `--offline` form only after those inputs are cached. `content-validate`
checks normalized records, generated GLB hashes and the compatible trusted
action-definition hash. `content-probe` imports the generated GLBs in a fresh
headless Godot project. `test-actors` stages actor presentation and checks the
selected motion and attachment resources; `make test-actors UI_FLAGS=--native`
also captures its rendered fixture when `xvfb-run` is available.

The generated client manifest is
`client/assets/imported/content/p0-warrior-dog/manifest.v1.json`. It records
the profile, source-content hash, gameplay-definition hash, presentation-output
hash, exact GLB hashes and structural counts. The server consumes the separate,
ignored `server/content/p0-warrior-dog/actions.v1.json`. Its
`gameplay_definition_hash` must equal the client manifest's value. Player
exports package presentation data only: GR2/MSA/MSM/MSS, Granny/Blender
runtimes, source archives, server action definitions, editor bridges, test
scripts and credentials are rejected by the actual-PCK audit.

Current player exports require this generated profile. For isolated P1 Web or
Linux QA output, retain the default destinations and supply separate paths, for
example:

```sh
python3 tools/export_playable.py --target web --server http://127.0.0.1:8186 --database mt2-p1-final --include-map --test-probe --output-dir .local/p1/web --work-dir .local/p1/web-work
python3 tools/export_playable.py --target linux --server http://127.0.0.1:8186 --database mt2-p1-final --include-map --test-probe --output-dir .local/p1/native --work-dir .local/p1/native-work
```

`--output-dir` changes only the completed artifact destination; `--work-dir`
contains the staged project, imports and audit logs. Existing files in an
explicit output directory are replaced by that export. `--include-map` retains
the Yongan section packs required by this database. `--test-probe` adds the
explicit local instrumentation used by automated QA; omit it for a normal
player export.

The profile currently records 27 Warrior and 13 Wild Dog motion records. The
build validates converted artifacts and source-derived action metadata; it does
not establish full server lifecycle QA, two-client acceptance, original visual
parity, Web/Linux export behavior, or complete class/mob/equipment coverage.
The P1 server preserves the prototype's 25 base player damage, +10 starter-sword
bonus, 100 HP dog, 20 dog damage, and existing cooldown/loot values as explicit
overrides while it uses selected source-derived delayed hit windows.
