# Original UI assets

`tools/import_metin_ui.py` converts a deliberately selected original Metin2 UI
fixture from client archive commit
`bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7`. It imports taskbar gauges and button
states, eight quickslot legends, inventory/equipment art, common window and
tooltip frames, chat bar/history pieces, minimap/area-map controls, selected
account/character entry art, sword icon `00010` and potion
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
| `locale/en/ui/login/loginwindow.sub` | `locale/en/ui/login/loginwindow.png` |

`manifest.json` has `version = 1`, `commit`, `repository`, `converter`,
`pillow_version`, `references`, `sources`, `assets`, and `maps` fields.
`assets` maps the complete normalized virtual path to `resource`, `width`,
`height`, `source`, `atlas`, `atlas_dimensions`, `crop`, generated PNG
`sha256`, and decoded `rgba_sha256`. Map entries also include `rgba_sha256`.
`crop` is `[left, top, right, bottom]`, with exclusive right/bottom,
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

Generated `.png.import` files pin lossless mode (`compress/mode=0`), disable
mipmaps and automatic 3D compression, and disable alpha-border modification.
The actual PCK audit loads every UI/map texture, rejects compressed or mipmapped
images, converts pixels to RGBA8, and compares their SHA-256 to `rgba_sha256`.
Its result reports `ui_images` and `ui_pixels_verified`. This detects altered
exported pixels even when the original PNG file and dimensions are correct.

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

The chat-history window uses its own 32 × 64 left/middle/right title pieces,
`pattern/chatlogwindow_titlebar_{left,middle,right}.png`, with the middle tiled
horizontally. The original `uichat.py` starts the movable, resizable window at
`(20, 20)` with a 450 × 120 minimum size. Channel buttons start at `(13, 24)`
and use 48-pixel spacing. Its small thin scrollbar uses 13 × 13 up/down buttons
and a 13 × 18 thumb, imported under
`public/scrollbar_small_thin_{up,down,middle}_button_*.png`. The original chat
panel center and borders are drawn colors, not missing texture assets.

`interfacemodule.py` places the ordinary 600-pixel chat window horizontally
centered at `screen_height - 25 - 37` and gives it a 200-pixel history height.
`game.py` binds `L` to chat-history visibility. `PythonChat.cpp` begins passive
line fading after five seconds, or once a line is fifth-newest or older;
opacity decreases by ten percent per update until at most 0.1. `PythonChat.h`
sets the default line spacing to 15 pixels and retained history to 300 lines.
These are consulted source observations; runtime verification is separate.

The original chat source keeps editing after a nonempty submission. The current
runtime intentionally returns keyboard control to the game after sending, as
requested during playtesting; this is a documented usability difference.

## Original font reference

The pinned English `bin/pack/locale_en/locale/en/locale_game.txt`, lines
795–797, defines `UI_DEF_FONT` as `Tahoma:12`, `UI_DEF_FONT_LARGE` as
`Tahoma:14`, and `UI_DEF_FONT_SMALL` as `Tahoma:9`. These values select an
installed font. There are no TTF/OTF/FNT font bytes in the pinned archive.
The `.fnt` resource name is interpreted by `src/EterLib/GrpText.cpp`, while
`GrpFontTexture.cpp` creates a normal-weight GDI font using positive
`LOGFONT.lfHeight` and `ANTIALIASED_QUALITY`. Matching a Godot font-size number
alone does not establish the same font metrics or rasterization.

A read-only local inspection found Wine's `Tahoma` substitute, version 0.001,
derived from Bitstream Vera, with LGPL-2.1-or-later terms in its font metadata.
It also found Microsoft Tahoma 7.00 in a browser cache, with Microsoft copyright
and restrictive embedded usage terms. Neither file was copied, packaged, or
added as a dependency; a cached file is not an authorized redistributable font
input. The present Godot font remains a fidelity limitation. A future font
input must have appropriate provenance and permitted use, and must still be
checked against the original GDI rendering before claiming font parity.

## Yongan map image

`maps/metin2_map_a1.png` stitches the 20 original
`bin/pack/OutdoorA1/metin2_map_a1/XXXZZZ/minimap.dds` tiles. Each is 256 × 256
pixels and covers 256 × 256 meters. The resulting image is 1024 × 1280 pixels,
covering map-local X `[0, 1024]` and Z `[0, 1280]`. Increasing X goes right;
increasing Z goes down. There is no resizing or interpolation during stitching.
`maps.metin2_map_a1` records its resource, hash, dimensions, bounds, axes and
every source tile's grid coordinates. This is original static map imagery;
live player markers must come from subscribed game state.

The original area map uses separate artwork:
`atlas/metin2_map_a1/atlas.png` is the native 171 × 214 crop defined by
`ymir work/ui/atlas/metin2_map_a1/atlas.sub`, from
`ymir work/ui/metin2_map_a1_atlas.dds`. The original `AtlasWindow` sizes itself
to image dimensions plus `(15, 38)`, yielding 186 × 252, with the image at
`(7, 30)`. Its initial position is `(screen_width - 402, 0)`. Common board,
title and close-button art already in the fixture frame this image. Map
markers scale map-local X/Z against the full 1024 × 1280 meter bounds.

`PythonMiniMap.cpp` confirms that the area map renders at native image size;
the small minimap instead starts at scale 2, doubles/halves zoom, and clamps
to `[0.5, 4]`. Its source cell scale is two meters, so the default minimap
scale corresponds to one rendered pixel per meter.

The current conversion produces 196 UI images and one stitched map using 260
pinned source files. Synthetic tests cover atlas version rules, invalid crops,
alpha preservation and map tile orientation. Actual conversion verified PNG
pixel round trips; Godot rendering and interaction require separate client
inspection and are not established by conversion alone.

## Account and character entry fixture

`tools/import_metin_intro.py` lists the selected entry artwork and eight source
references. The converter reads the pinned English `loginwindow.py`,
`selectempirewindow.py`, `selectcharacterwindow.py`, `createcharacterwindow.py`
and corresponding `root/intro*.py` files as references only. Their implementation
is neither copied nor executed. Selected dependencies include the original
1024 × 768 login/server/selection backgrounds, 208 × 97 login panel, warrior
title, empire map/flags, selection arrows, and attribute slots/gauges.

The server board is 375 × 400 at horizontal center and `height - 472`.
The login image is centered at `height - 410`, with 120 × 18 username/password
fields at `(77, 16)` and `(77, 43)` inside it. The connection strip is 35 pixels
above it. The selection board is 208 × 323 at `(width * 65/800, height * 220/600)`;
the creation board is 208 × 329 at `(width * 65/800, height * 215/600)`.
Background scaling and these mixed native-pixel/proportional anchors follow
the selected source layouts. The original four character slots use arrows or
keys 1–4; Start remains disabled until the chosen character is confirmed by
the server. Empty slots expose Create.

`classic_intro.gd` emits login, registration, selection, creation, entry and
logout intents. Roster refreshes preserve an active creation/selection panel;
the account coordinator chooses the next screen after confirmed actions.
Error responses preserve username/email and character-name input. Password
fields are masked and cleared immediately after submission; logout also clears
any unsubmitted password. Read-only snapshots expose control rectangles without
username, email or password field values. The supported fixture enables one
server/channel, Shinsoo/Yongan, male warrior and the first shape. Other choices
remain disabled. Attribute values are blank unless supplied by actual state.

The native preview loads the existing original warrior GLB into an isolated,
transparent Godot viewport. It reuses the converted `wait` animation; the
original dedicated intro motion set, exact original lighting, selection
transitions and full job/gender/shape choices are not implemented. Registration
is an in-client adaptation using original board/button art: the reference
client delegated account creation to a website. Font limitations above also
apply. These differences prevent a claim of complete entry-screen parity.

```sh
make test-ui UI_FLAGS="--suite intro --native --output .local/classic-intro"
```

The isolated native intro suite passes 27 checks for real GUI click handling,
original input geometry, focus, masked fields, explicit submit signals, error
retention, submitted-password clearing, busy-state rejection, server-confirmed roster/selection, unavailable
choices, original model loading and credential-free snapshots. Native images
for server, login, registration, empire, creation and selection are saved as
`classic-intro-<stage>.png`; their original artwork and warrior rendering were
visually inspected. This fixture uses synthetic responses and establishes no
authentication or database behavior; exported account-to-world verification is
separate.

`tools/test_browser_accounts.py` runs that separate check against matching Web
and Linux `--test-probe` exports. It uses actual browser canvas clicks/typing
for original entry controls and system-menu actions, and a fixed native command
list for normal server intents. It creates two independent test accounts and
checks subscribed/rendered movement, character ownership rejection, creation
errors, switching, reconnect, session restore, logout and subsequent login.
Optional `--panels` and `--inventory` reuse the ordinary HUD interaction checks.
`--session-refresh` additionally waits for both real four-minute session timers,
checking renewed connection timestamps and the same rendered identities/positions;
it neither changes token expiry nor adds a privileged refresh action.
Use the normal development Python environment with browser dependencies installed;
both exports must name the supplied `--database` and share the supplied `--url`.
Each run uses fresh userdata. Native command files have owner-only permissions
from creation and are removed with the fresh userdata afterward; credentials
are excluded from printed results and read-only snapshots. A generated
`report.json` distinguishes completed checks from a failed or unfinished run.

The complete loopback Web/Linux account run passes **103 checks** with
`--inventory --panels --session-refresh`; evidence is
`.local/browser-accounts/20260906-193823/report.json`. Real browser typing verifies
focus and the complete character name before creation, including retry after a
duplicate-name rejection. Actual clicks exercise both original system-menu
actions, character switching and entry. Both real four-minute session timers
renewed their connections and restored identical character identities/positions.
Login, creation, two-character selection and both world screenshots were
inspected; neither client reported an engine error. The native client runs under
Xvfb, so this is functional/rendering evidence rather than a native GPU performance
comparison. Private command files and fresh userdata were removed after completion.

The same complete **103-check** run also passes against the public
`https://kcanakdag.com:8443` release with database `mt2-accounts-v3`, including both
real renewal timers. Public evidence is
`.local/browser-accounts/20260906-194508/report.json`; login and both rendered
world screenshots were inspected. Browser/native TLS validation remained enabled,
both clients retained the same identities/positions after renewal, and neither
reported an engine error. These runs use fresh synthetic test accounts and do
not establish Windows execution or exact original font/intro-animation parity.

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
tokens. `Enter` opens chat; submitting nonempty text clears it, releases text
focus and returns to movement. Empty Enter closes ordinary entry too. Up/Down
recalls recently submitted text. `Escape` cancels a held item, closes
chat/inventory/map, or opens the system menu.
Developer diagnostics use `Ctrl+F3` so the original `F3` quickslot remains usable.

The minimap has working close/reopen and zoom controls, with original local and
other-player marker artwork driven by subscriptions. `M` or its atlas button
opens the separate 171 × 214 Yongan area-map image inside the original-size
186 × 252 window. Drag its title to reposition it; M, Escape and close dismiss
it. The atlas marks the local player and does not fabricate unavailable NPC or
warp records. This is separate from resizing the stitched minimap image.

The ordinary chat field is 600 pixels wide, centered at viewport height minus
62. Passive messages begin fading after five seconds or when older than the
four newest. `L` or the history button opens a movable, resizable log with
original title pieces, channel-button art and scrollbar controls. Message
display comes from subscribed server rows; only normal chat exists, with the
server's 160-character, rate and 100-row retention limits. The consulted original
300-line history is a reference, not a completed server feature. Chat focus
keeps I/M/L and movement keys from also triggering gameplay controls.
Sending, cancelling/closing, or left/right clicking the world releases both
chat inputs and closes ordinary entry before movement/camera handling. The
submit event is consumed before that focus change, preventing accidental chat
reopening. Native and loopback Chrome/Linux regression checks for this behavior
pass. The updated public release also passes panel, inventory and multiplayer
checks; no synthetic chat was sent to public players.

```sh
make test-ui UI_FLAGS="--suite ui --native --output .local/classic-panels-ui"
make test-ui UI_FLAGS="--suite map --native --output .local/classic-map"
make test-ui UI_FLAGS="--suite chat --native --output .local/classic-chat"
```

`tools/test_classic_ui.py` stages only UI code, its imported artwork, the minimap
renderer and the selected `client/tests/classic_<suite>_smoke.gd`. It copies no editor bridge,
networking addon, saved player identity or database. The real Godot import and
runtime check exercise GUI mouse events, inventory anchoring, equip/use/move
intents, confirmation-only counts, quickslot binding, chat keyboard ownership
and per-identity setting restoration. `--native` requires `xvfb-run` and also
renders a standalone screenshot. Logs, a JSON result and the optional PNG are
written to the chosen `--output` directory (default `.local/classic-ui/`). Separate
outputs preserve each suite's evidence. `--suite` accepts `ui`, `map`, `chat` or `intro`;
omit `--native` for a headless check. These presentation checks complement the
multiplayer and exported-browser checks; they do not establish a server action.
The intro suite additionally stages the existing warrior GLB for its preview.

The latest local native UI, map and chat runs pass 19, 17 and 22 checks,
with screenshots in `.local/classic-system/`, `.local/classic-map/` and
`.local/classic-chat-final/`.
The UI suite additionally verifies that Escape opens the system menu inside
the viewport, that it remains centered when resizing from 1280 × 800 to
1024 × 768, and that actual clicks emit Change Character and Logout intents.
Native MCP also observed M opening the exact-size atlas in the connected game.
The new loopback exported Chrome/Linux run passed 45 panel, chat-focus and
multiplayer checks in `.local/browser-proof/20260906-174144/report.json`.
Fresh exported PCKs also verify all 160 UI/map images against raw RGBA hashes.
`--chat-focus` is restricted to loopback URLs, keeping synthetic messages out
of public sessions. Public release `20260906T154235134255Z` separately passed
45 core/panel/inventory checks in `.local/browser-proof/20260906-174806/report.json`,
with no engine errors. The served manifest matches the audited Web export.
Native editor inspection of the connected public game confirms centered entry
and Escape clearing focus; see `.local/classic-chat-native-editor/centered-chat.png`.

Current fidelity limits are explicit: the archive includes no font bytes,
so text uses Godot's font at nominal size 12; this does not match GDI metrics by
itself. HP uses current
server health, while SP, stamina and EXP remain empty until those game systems
exist. Character, friends, expanded taskbar, extra equipment, shop and options
controls are disabled. The minimap shows the original map with subscribed
positions, working zoom and close/reopen; the separate atlas is interactive.
The sword and potion tooltips use current server values (+10 damage and 40 HP),
not unimplemented retail progression. Animated gauge frames, exact font
rasterization, the full settings/character screens and all original chat
channels still require further fidelity work.
