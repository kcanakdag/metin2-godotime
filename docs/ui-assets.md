# Original UI assets

`tools/import_metin_ui.py` converts a deliberately selected original Metin2 UI
fixture from client archive commit
`bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7`. It imports taskbar gauges and button
states, eight quickslot legends, inventory/equipment art, common window and
tooltip frames, chat bar pieces, minimap controls, sword icon `00010` and potion
icon `27001`. The original sword icon occupies 32 × 64 pixels; the potion is
32 × 32. This is an asset pipeline, separate from gameplay item definitions.

```sh
python3 tools/dev.py setup
.local/venv-dev/bin/python tools/import_metin_ui.py
.local/venv-dev/bin/python tools/import_metin_ui.py --offline
.local/venv-dev/bin/python -m unittest discover -s tests -p test_metin_ui.py
```

The converter uses **Pillow 12.1.0**, pinned in `tools/requirements-assets.txt`
and included by the normal development setup in its isolated virtual environment.
It requires no Blender or
AI image generation for these raster textures. Original files stay in the
existing ignored pinned archive source cache; converted files stay under
`client/assets/imported/ui/`. The online command fetches only the explicit
fixture, its atlas dependencies, 20 original Yongan minimap tiles, and a small
set of layout/behavior references. The offline command rechecks cached file
hashes and reproduces the images. It never executes downloaded Python or C++.
See [third-party provenance](third-party.md) for original asset rights, which
remain separate from this project's source and MIT conversion tools.

## Runtime asset contract

Normalize original virtual paths to lowercase forward slashes and remove the
drive prefix. Below `res://assets/imported/ui/`, remove the initial
`ymir work/ui/` and replace `.sub`, `.tga`, or `.dds` with `.png`:

| Original virtual path | Generated path below the UI directory |
| --- | --- |
| `d:/ymir work/ui/game/taskbar/gauge.sub` | `game/taskbar/gauge.png` |
| `d:/ymir work/ui/public/slot_base.sub` | `public/slot_base.png` |
| `d:/ymir work/ui/equipment_bg_without_ring.tga` | `equipment_bg_without_ring.png` |
| `icon/item/00010.tga` | `icon/item/00010.png` |
| `icon/item/27001.tga` | `icon/item/27001.png` |

`manifest.json` has `version = 1`, `commit`, `repository`, `converter`,
`pillow_version`, `references`, `sources`, `assets`, and `maps` fields.
`assets` maps the complete normalized virtual path to `resource`, `width`,
`height`, `source`, `atlas`, `atlas_dimensions`, `crop`, and generated PNG
`sha256`. `crop` is `[left, top, right, bottom]`, with exclusive right/bottom,
or `null` for an uncropped image. `atlas` is the original archive path, or
`null`. `sources` maps every used archive path to Git blob hash, SHA-256, and
byte count, including descriptors, atlases, and consulted source references.

Original `src/EterLib/GrpSubImage.cpp` establishes the descriptor rules:
version 1.0 resolves atlas filenames under `ymir work/ui/`; version 2.0 resolves
them relative to the descriptor directory. The converter validates fields,
version, paths and crop bounds. Archive pack precedence is the existing
`Archive.resolve` contract. PNG output preserves decoded RGBA pixels without
resizing, recoloring, or additional lossy compression. Every image is reopened
and checked for exact pixel equality.

## Original layout observations

The consulted English `inventorywindow.py` describes a 176 × 565 window, a
title at `(8, 7)`, and 155 × 187 equipment art at `(10, 33)`. Equipment slot
coordinates begin three pixels inside that image. The weapon area is 32 × 96
at window position `(16, 39)`. Bag cells start at `(8, 246)`, form a 5 × 9
grid with 32-pixel steps, and have two page tabs at `(10, 224)` and `(88, 224)`.
This reference includes additional equipment categories beyond the current
gameplay slice; importing its art does not implement those categories.

The original taskbar occupies the bottom 37 pixels. Its 158 × 47 gauge frame
extends ten pixels above it. HP and SP gauges begin at frame positions
`(59, 14)` and `(59, 24)`; stamina begins at `(59, 38)`. The 105 × 37 experience
frame starts at taskbar `(158, 0)`. Eight 32-pixel quickslots are arranged as
two groups of four with a 14-pixel division. The four right buttons begin at
screen width minus 144, 110, 76, and 42 pixels.

The minimap frame is 136 × 137 at the top right, with a 128 × 128 viewport at
`(4, 5)`. Common boards use 32-pixel corners and 128-pixel edge tiles; tooltips
use 16-pixel corner/edge art with a black, 51%-opaque center. The original
tooltip default width is 190 pixels and text line height is 17 pixels.
No TTF/OTF/FNT font files exist in the pinned archive inventory. This conversion
does not add a font or establish identical original font rendering.

## Yongan map image

`maps/metin2_map_a1.png` stitches the 20 original
`bin/pack/OutdoorA1/metin2_map_a1/XXXZZZ/minimap.dds` tiles. Each is 256 × 256
pixels and covers 256 × 256 meters. The resulting image is 1024 × 1280 pixels,
covering map-local X `[0, 1024]` and Z `[0, 1280]`. Increasing X goes right;
increasing Z goes down. There is no resizing or interpolation during stitching.
`maps.metin2_map_a1` records its resource, hash, dimensions, bounds, axes and
every source tile's grid coordinates. This is original static map imagery;
live player markers must come from subscribed game state.

The initial conversion produced 148 UI images and one stitched map using 185
pinned source files. Synthetic tests cover atlas version rules, invalid crops,
alpha preservation and map tile orientation. Actual conversion verified PNG
pixel round trips; Godot rendering and interaction require separate client
inspection and are not established by conversion alone.

## Godot HUD and interaction verification

The runtime composes the original bitmaps at their native pixel dimensions:
176 × 565 inventory, two 5 × 9 pages, the original equipment positions, bottom
37-pixel taskbar, eight quickslots and top-right minimap. `I` opens the inventory;
left-click attaches an item to the cursor, and a second click selects its
destination. Holding and dragging also works. Right-click equips or unequips
the sword and uses a potion. Moving, equipping and using send server intents;
items and counts remain unchanged until subscription confirmation arrives.

Drag or attach an inventory item to a quickslot to bind it. Keys `1`–`4` and
`F1`–`F4` activate the eight slots; Shift+`1`–`4` or the original arrow buttons
select one of four local quickslot pages. Right-clicking a quickslot clears it.
Quickslot bindings, inventory position and pages are saved per endpoint,
database and identity under `user://ui/`; these settings contain no identity
tokens. `Enter` opens chat; submitting a message closes its entry field.
`Escape` cancels a held item, closes chat/inventory, or opens the system menu.
Developer diagnostics use `Ctrl+F3` so the original `F3` quickslot remains usable.

```sh
make test-ui
make test-ui UI_FLAGS=--native
```

`tools/test_classic_ui.py` stages only UI code, its imported artwork, the minimap
renderer and `client/tests/classic_ui_smoke.gd`. It copies no editor bridge,
networking addon, saved player identity or database. The real Godot import and
runtime check exercise GUI mouse events, inventory anchoring, equip/use/move
intents, confirmation-only counts, quickslot binding, chat keyboard ownership
and per-identity setting restoration. `--native` requires `xvfb-run` and also
renders a standalone screenshot. Logs, a JSON result and the optional PNG are
written to `.local/classic-ui/`. These presentation checks complement the
multiplayer and exported-browser checks; they do not establish a server action.

Current fidelity limits are explicit: the archive includes no distributable
font, so text uses the Godot font at the original 12-pixel size. HP uses current
server health, while SP, stamina and EXP remain empty until those game systems
exist. Character, friends, expanded taskbar, extra equipment, shop and options
controls are disabled. The minimap shows the original map with subscribed
positions and working zoom; its close/atlas artwork is not interactive yet.
The sword and potion tooltips use current server values (+10 damage and 40 HP),
not unimplemented retail progression. Animated gauge frames, exact font
rasterization, the full settings/character screens and all original chat
channels still require further fidelity work.
