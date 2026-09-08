# Original ground-item content

The selected ground-item importer resolves the English `item_list.txt` at client
pin `bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7`. An explicit fourth column selects
its model; the original three-column fallback is `ymir work/item/etc/item_bag.gr2`.
Missing, duplicate, malformed and unsafe selected records reject. This is an
independently authored parser based on `GameLib/ItemManager.cpp::LoadItemList` and
`ItemData.cpp::SetDefaultItemData`, not copied original implementation.

The default fixture selects only Yang (vnum 1), Small Red Potion (27001) and Medium
Red Potion (27002). Yang resolves `money.gr2`; both potions share `medicine_R.GR2`.
The tool deduplicates models, resolves their diffuse texture dependencies through
the pinned archive/Carbon reader, and reuses the existing Blender item converter.
Only these selected dependencies are fetched. Original models/textures and outputs
remain ignored. Runtime models use GLB, not GR2; conversion is centimetres to metres.

```sh
.local/venv-dev/bin/python tools/import_ground_items.py \
  --blender /path/to/blender --godot /path/to/godot \
  --output .local/items/<fresh-output>
```

`--godot` requires Blender and uses Linux `xvfb-run` for a rendered preview. It
creates an isolated project and XDG directories beneath the output, preserving
open editors. Logs, native report and screenshot are retained. Omit `--godot` for
conversion only, or omit both engines for dependency normalization only. Use
`--offline` after the selected files are cached. Repeat `--vnum` to select an
explicit alternative set of at most 256 item IDs; choose a fresh output directory.
Do not expand the fixture to every game item implicitly.

`normalized.v1.json` maps each vnum to a shared model ID and records source hashes
and revision. `blender-report.json` records artifact hashes, geometry, metre bounds,
textured meshes and converter/importer versions. The converter prepares assets; use the installer below for runtime content.
Original drop motion/effects remain pending. Ground-name layout is handled by the
shared client component described below.

The default selection converts to two GLBs totalling 92,728 bytes. Parser tests
cover shared selection, original fallback and invalid records. An offline normalized
package exactly matched the online one. The complete offline Blender/Godot command
passed at `.local/items/ground-pipeline-r2`; all three preview instances have textured
meshes and valid bounds. The initial native capture was reviewed and showed the
coin pile and two red bottles. See `acceptance.json` for source/artifact hashes.


## Install and render the selected package

```sh
.local/venv-dev/bin/python tools/install_ground_items.py \
  --content .local/items/<converted-package> --client client
```

The installer checks the normalized manifest hash, converted artifact identities,
paths, hashes and byte counts. It installs only GLBs and a runtime catalog under
`assets/imported/ground_items`, using the existing staged installer with a distinct
ground-content receipt identity. A matching repeat verifies installed bytes; changed
or unowned destinations reject instead of being overwritten. Use an isolated client
for a different package until an explicit upgrade workflow exists. Receipts establish
consistency of trusted local compiler output, not a signature or license grant.

The optional shared catalog validates selected vnums/model references and package
paths, then caches PackedScenes for reuse. `PveActor` uses vnum 1 for Yang and the
subscribed item vnum for item drops. Selected models stay settled; original falling,
landing and glow effects are still pending. Items outside the installed model set
retain their catalog icon fallback. Without a package, older fixture clients retain
the previous fallback presentation. Restart a running client after installation.

`--ground-items` with `--field-combat --mob-route <route>` in
`tools/test_browser_accounts.py` verifies matching original ground-model paths and
labels for all drops owned by the browser test character in both exports. The
instrumented export exposes drop presentation IDs separately for items and Yang,
so matching numeric IDs in those tables do not collide. Use `--field-only` to omit
the unrelated return/account lifecycle path. This requires exports containing the
installed package and updated probe; existing exports are not modified in place.


The installed runtime passed 23 controlled native checks and 48 exported two-client
checks in `.local/items/ground-live-r1/report.json`. Both exports selected the same
original model paths and labels for the test character's potion and 26-Yang drops.
The browser capture was reviewed and shows those models on the actual map; labels
still overlap. Six installer tests (including the existing mob installer) and three
browser predicate tests pass. Evidence/hashes are in that run's `acceptance.json`.
This release slice does not add pickup mechanics or change existing ownership rules.

## Ground names

`WorldDropLabels` in the Main scene projects loot names into a shared canvas below
the HUD. Nearby names move downward to avoid overlap, using five-pixel spacing
and at most 20 adjustments. Labels reproject with the camera, hide with streamed
actors or when behind/offscreen, and are removed with their source drop. Their
controls ignore pointer input. Standalone actor fixtures retain their Label3D
fallback when no overlay is present. Text comes from the same item catalog or
server-owned Yang amount as the underlying drop.

`client/tests/world_drop_labels_smoke.gd` covers layout and lifecycle behavior;
`client/tests/item_drop_smoke.gd` checks integration with real converted models.
The exported `--ground-items` replay now retains both browser and native drop
captures. Original font, owner text, visibility-key and click-pickup fidelity remain
pending; this bounded layout can still overflow on exceptionally crowded piles.
