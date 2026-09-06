# Original outdoor-map importer

The pipeline reconstructs **Yongan (`metin2_map_a1`)** from original terrain and
placement records. It produces an inspection scene and 20 playable section
scenes. A companion bake supplies authoritative terrain, blocking shapes and
elevated walk surfaces to the SpacetimeDB server.

## Run

After the normal development setup and `make assets` (which supplies Carbon):

```sh
make import-map BLENDER=/home/kcan/blender-5.2.1-linux-x64/blender
make bake-map BLENDER=/home/kcan/blender-5.2.1-linux-x64/blender
make map-preview
make test-map
```

Use your Blender executable and optionally `GODOT=...` on another machine.
Tested engines: Blender 5.2.1 and standard Godot 4.7.2. Python uses its standard
library; Blender supplies bpy, mathutils and NumPy.

```sh
# Rebuild without network access, requiring all source files to be cached:
python3 tools/import_metin_map.py --offline --blender /path/to/blender

# Fetch/validate the selected map without conversion:
python3 tools/import_metin_map.py --prepare-only

# Return exit code 2 if any scenery remains unsupported:
python3 tools/import_metin_map.py --strict --blender /path/to/blender
```

Options also include `--map` and `--godot`. Only A1 has been exercised end to end;
accepting another map name is not a compatibility claim. Normal mode writes a
partial scene with explicit unsupported records. Strict mode still writes the
scene/report, then returns 2 for those records. Corrupt hashes, invalid formats,
unresolved material dependencies and engine errors fail the command.

The first run caches the pinned inventory and small property catalog, then the
selected map and its model/material dependencies. It does not download every
game asset. Subsequent runs verify source hashes and reuse Blender outputs when
inputs, converter code and generated-file hashes agree. Godot assembly and checks
run again. Background Blender leaves the interactive scene and unsaved work
intact. Godot's import pass uses recovery mode to disable editor plugins and
separate user-data directories. No database or second MCP server is started.

## Generated files and inspection

| Path | Contents |
| --- | --- |
| `client/assets/imported/maps/metin2_map_a1/map.tscn` | Generated Godot map |
| `client/assets/imported/maps/metin2_map_a1/chunks/` | 20 terrain/scenery sections with terrain and authored-floor click colliders |
| `client/assets/imported/maps/metin2_map_a1/collision.json` | Collision shapes, walk triangles and shared content hash |
| `client/assets/imported/maps/metin2_map_a1/map.json` | Parsed records and status |
| `client/assets/imported/maps/metin2_map_a1/models/` | Reusable static GLBs |
| `client/assets/imported/maps/metin2_map_a1/terrain/` | Section GLBs, tile and attribute images |
| `client/assets/imported/maps/metin2_map_a1/textures/` | Material images and terrain texture array |
| `.local/map-import/metin2_map_a1/report.json` | Conversion counts and unsupported definitions |
| `.local/map-import/metin2_map_a1/sources.json` | Commit, Git blob/SHA-256 hashes and byte sizes |
| `.local/map-import/metin2_map_a1/manifest.json` | Full build input and local source paths |
| `assets/source/maps/<commit>/` | Ignored original sources |
| `.cache/metin-archive/<commit>/` | Ignored archive inventory |
| `server/content/yongan.bin`, `.sha256`, `.json` | Ignored authoritative map, shared hash and source/bake report |

Open the generated map to inspect `Sections`, `Scenery` and `UnsupportedMarkers`.
Scenery roots retain their source CRC, property name and position as metadata.
Select a section or object and press **F** in the editor to frame it. The upstream
MCP editor-camera helpers currently call unavailable SubViewport methods;
runtime inspection works and the importer does not depend on those helpers.
Keep authored changes in a wrapper scene: importing again replaces generated files.

The separate `res://scenes/map_preview.tscn` has these controls:

| Control | Action |
| --- | --- |
| WASD; Q/E | Fly relative to camera; down/up |
| Right drag | Look around |
| Shift; wheel | Faster movement; adjust speed |
| R; M | Town view; whole-map overview |
| U | Pink markers for unsupported placements |
| C | Raw terrain attributes: bit 0 red, other nonzero flags blue |

The camera has no gameplay collision. Attribute colors are an inspection aid,
not a verified navigation mesh or complete flag decoder.

## Conversion rules

Sources use client commit `bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7` and Carbon
commit `8cba23114bf1d30c9da597c1ecf49271e00b939d`. Virtual paths normalize drive
prefixes, slashes and case. The first registered pack in `bin/pack/Index` wins
for differing files, following the pinned original loader.

Source centimeters `(x,y,z)` become Godot meters `(x,z,-y)/100`. Placements
already span the map; chunk offsets are not added twice. Height bias is applied
before conversion; global base position is retained separately in metadata.
Source yaw/pitch/roll rotations are transformed into the same Godot coordinate
system as Blender's glTF output.

Each section has 128 by 128 two-meter cells. Visible heights use the inner
129 by 129 samples of a 131 by 131 uint16 grid; the halo supplies edge normals.
Shared edges are validated before export. HeightScale applies to terrain and
water, while scenery supplies its own Z. GR2 material bindings retain sparse
topology IDs, preventing untextured surfaces caused by compacted slot indices.

Ground rendering uses original tile IDs and texture UV scales/offsets, with
17 normalized 512-pixel layers through Godot's
[layered-texture importer](https://docs.godotengine.org/en/stable/classes/class_texture2darray.html).
Shader interpolation blends neighboring categorical tiles; legacy splat
dilation is not reproduced exactly. Water uses source levels and a simple
translucent material. Scene assembly retains PackedScene instance state, so
child overrides do not duplicate geometry.

Tile and attribute PNGs contain numeric IDs/bits, not ordinary color imagery.
`data_png` writes a lossless Godot import policy with no mipmaps or 3D texture
compression. Lossy block compression changes those IDs and selects the wrong
terrain layers. The Web pack generator follows all feature-specific import
remaps, including S3TC color-texture resources, so terrain and prop dependencies
remain available when a section is mounted alone.

This is project code using the MIT Carbon reader. Original loader source was
consulted for formats, not copied into gameplay or conversion code. See
[third-party provenance](third-party.md).

## Authoritative content bake

After import, `make bake-map BLENDER=/path/to/blender` runs
`tools/bake_yongan.py` in a separate factory-startup Blender process, then
reassembles the Godot scenes. It requires the map import manifest and pinned
source cache, currently supports A1 only, and leaves interactive Blender intact.

The bake combines heights into a 513 × 641 vertex grid, source blocking into
1024 × 1280 one-meter cells, water occupancy, 1,334 transformed collision shapes
and 688 authored elevated walk triangles.
`tools/metin_collision.py` decodes model attribute data. The bake rejects
unsupported height/cell/map scales, duplicate or missing chunks and broken
height seams instead of silently producing incompatible coordinates. The binary
uses the `MT2YON02` header; its SHA-256 is recorded in client metadata and
`world_info.content_hash`.
`server/src/content.rs` embeds it when built with `--features yongan`.

The current bake hash is
`fcb702a8e2089e97baf88bcf5096acd9297f6d2d025c14071d481058655c27e6`,
recorded in `server/content/yongan.json`. Water occupancy uses the visible mesh's
four-corner terrain-height test: records below every terrain corner add no water
block. This omits 75,520 buried two-meter water cells (302,080 one-meter cells)
without removing original blocking attributes or authored collision shapes.
The earlier all-water-record bake incorrectly blocked dry terrain.

The server uses the visible terrain's triangle interpolation and the highest
applicable bridge/platform surface. A Rust regression checks an authored bridge
at X=256, Z=700, Y≈131.393 across a section seam; this is a rules test, not a
rendered traversal test. This is not independent navigation on several
overlapping floors. Movement checks bounds, speed, radius, height
changes, source blocking, water and model shapes; it does not find routes around
walls. Client terrain/walk-surface colliders support click picking; building
blocking remains server-owned. Visuals display the replicated X/Y/Z.

Re-bake, rebuild/publish the server and re-export clients together after content
changes. Keep fixes in the converter/bake, not generated binaries or scenes.
Web export partitions the sections into shared and content-hashed section PCKs
for loading nearby scenery. See [distribution](distribution.md#loading-assets-during-play)
for current browser verification and cache limits.

Every Web export containing Yongan automatically runs an isolated resource audit
for all 20 section packs. Run it separately after an export with:

```sh
make test-world-packs WEB_DIR=dist/web
```

The audit starts a fresh empty Godot process per section, mounts only the shared
pack and that section's pack, and checks shader/terrain layers, texture resources
and exact exported numeric red-channel bytes against source tile/attribute PNGs.
It fails missing dependencies, compressed numeric textures, mipmaps or altered
IDs. Reports are `world-pack-audit.json` under the export work directory, or
`.local/world-pack-audit/` when run separately. This resource test complements
rendered browser screenshots; it does not replace them.

## Evidence and remaining work

A1 has **20 sections, 119 unique converted static models, 601 rendered scenery
placements, 17 terrain layers and zero height-edge mismatches**. All placement
CRCs resolve. **368 SpeedTree placements and 6 effects** remain explicit
unsupported records with optional markers. No inspected model has an embedded
animation.

Format tests cover units/axes, padded heights/seams, water variants, attributes,
rotations, invalid records, unsafe paths, patch precedence and corrupt caches.
`make test-map` loads the actual scene in Godot and checks all 975 placements,
heading/offset conversion, texture layers and duplicate terrain. Live MCP checks
exercise the town, overview, flying, reset and diagnostic toggles; screenshots
are in `.local/map-import/metin2_map_a1/`.

Further converters are needed for SpeedTree SPT geometry/wind and Metin2 effects.
Environment/sky/fog, ambient audio, animated water, legacy shadow maps, exact
splat blending, scenery LOD and complete original collision fidelity are not reconstructed.
Supporting section sources are retained. This is not an exact rendering match
with the original client.

Yongan's live two-identity SDK movement/combat suites passed in
`.local/yongan-network-final.json` and `.local/yongan-combat-final.json`. The public
Web/Linux test passed 26 multiplayer, section-loading, keyboard combat and
lifecycle checks in `.local/browser-proof/20260906-161458/report.json`. Its
browser/desktop screenshots show corrected terrain textures; native appearance
is also recorded in `.local/yongan-native-public.png`. The final export's
`world-pack-audit.json` confirms all 20 isolated sections and 40 lossless numeric
textures. See
[distribution verification](distribution.md#verification-status).
