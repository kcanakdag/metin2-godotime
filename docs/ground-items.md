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
textured meshes and converter/importer versions. This is asset preparation, not a
runtime installer: gameplay still needs a validated loader, appropriate ground
placement, drop motion/effects, label layout and export qualification.

The default selection converts to two GLBs totalling 92,728 bytes. Parser tests
cover shared selection, original fallback and invalid records. An offline normalized
package exactly matched the online one. The complete offline Blender/Godot command
passed at `.local/items/ground-pipeline-r2`; all three preview instances have textured
meshes and valid bounds. The initial native capture was reviewed and showed the
coin pile and two red bottles. See `acceptance.json` for source/artifact hashes.
