# Third-party sources

The Warrior skill-effect investigation selects six MSE scripts (`samyeon_d`,
`palbang_sword`, `palbang_spin`, `gigongcham_making`, `gigongcham_swing`,
`gyeoksantau_triple`) at client pin
`bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7`. The five particle-only scripts
and their 12 referenced textures are converted as ignored candidates; Bash
contains mesh groups and is not partially installed. The independently authored
scalar-curve adapter follows `EffectLib/Type.h:GetTimeEventBlendValue`: ordered
duplicate timestamps are valid, exact timestamps use the first duplicate, and
subsequent interpolation starts from the last duplicate. No source code was copied.

The independently authored ground-label layout uses the five-pixel spacing and
20-adjustment bound observed in the pinned client's `PythonTextTail.cpp` as a
behavioral reference. No original implementation was copied. It uses our shared
Godot UI text styling; original font and full text-tail interaction parity remain
unqualified.

These are the source revisions used by the current project. Code licenses and
original game asset rights remain separate.

The projectile effect follow-up fetches the eight previously resolved MSE scripts
and the arrow's referenced `arrow_01.mde`/TGA at the existing client pin. The arrow
geometry is converted offline with our shared Blender tool; original blend metadata
is retained without claiming renderer parity. Seven MSE files contain particle
systems; their recipes and textures are now converted separately, with runtime
simulation/rendering still pending. Source files and converted models remain ignored.

The particle adapter reads the seven selected MSE scripts and fetches only their
12 referenced texture paths at the same client pin. `metin_particles.py` is an
independently authored adapter informed by `EffectLib/ParticleSystemData.cpp`,
`Type.h`, `EmitterProperty.h` and `ParticleProperty.h`; it copies no original
implementation. Original centimetre/second values and render enums are preserved.
The conversion uses Pillow for decoded RGBA-to-PNG output and verifies exact
decoded pixels. Original scripts/textures and converted outputs remain ignored.
The Godot emission component is independently authored from the lifecycle contract
in `EffectElementBaseInstance.cpp`, `ParticleSystemInstance.cpp` and
`ParticleInstance.cpp` at the same pin. No original implementation is copied.
The companion independently authored motion adapter also follows force order in
`EffectUpdateDecorator.cpp`/`.h`, original shape/velocity sampling and attached
versus world-space coordinates. Godot's seeded RNG supports repeatable QA, not
original random-stream parity. No additional source assets were fetched for it.
The selected Godot renderer adds independently authored interpretation of
`ParticleInstance.cpp::Transform`, `EffectUpdateDecorator.h` texture/rotation
timing and `Type.h::DWORDCOLOR` packed interpolation. It reuses only the already
selected converted textures and does not import original rendering code. Godot
color-space/blend parity still needs direct original-client comparison.
The independently authored `projectile_flight.gd` follows the selected trajectory,
homing and collision-order contract in `GameLib/FlyingInstance.cpp` and quaternion/
segment conventions in `EterLib/GrpMath.h`. It copies no original implementation
and introduces no new asset downloads. Its hit output is presentation-only.
The companion projectile wrapper/trail renderer independently interprets line and
multi-line attachment transforms, impact lifetime and trail-history/segment rules
in `FlyingInstance.cpp` and `FlyTrace.cpp`. It reuses already selected assets;
original mesh-blend behavior remains outside this particle-only wrapper.

The flight-discovery extension fetches only the four MSF definitions selected by
the 26 White Oath launch declarations, at the existing client pin. It resolves
eight MSE dependency paths without fetching their contents. Loader/default and
negative trail-lifetime behavior were checked against `GameLib/FlyingData.cpp`
and `GameLib/FlyTrace.cpp`; the parser is independently authored. Original scripts
and generated inventories remain in ignored source/evidence directories.

The ordinary mob projectile linker preserves selected original MSA type-6 launch
declarations and references their MSF paths without fetching additional effect
assets. Damage-type interpretation was checked against the pinned server's
`char_battle.cpp` (`CHARACTER::Attack`, `CFuncShoot`) and `battle.cpp`
(`CalcMagicDamage`). This metadata adapter is independently authored; no original
combat implementation was copied into the project.

The mob motion-registration adapter was independently implemented from the pinned
client's `GameLib/RaceManager.cpp::__LoadRaceMotionList` contract. Unregistered
rows are retained as ignored metadata. The actor mesh selector follows
`EterGrnLib/Model.cpp`, which renders model-bound meshes rather than every mesh
stored in the file. Unused source geometry is recorded in conversion reports;
no source implementation or vendored Carbon code was copied or modified.

The bounded `yongan-population.json` selection derives 44 monster definitions from
the original map's audited regeneration/group dependencies. Metadata resolves 12
GR2 models and 19 race scripts at the existing pins; this is not an import of every
game asset. Default ShapeData texture remaps are now retained. Blue Wolf 104,
Red Wild Boar 109 and Black Bear 112 were converted as a focused appearance check,
with their original variant DDS textures kept in ignored source storage and only
converted derivatives used by Godot. No original runtime implementation was copied.

The foliage preparation selects Yongan's 14 referenced SPT files and the matching
`bin/SpeedTreeRT.dll` / `extern/include/speedtree/SpeedTreeRT.h` from the existing
client pin into ignored storage. The header and PE exports are ABI references;
no SDK implementation was copied. Runtime execution has not been approved or
performed. The DLL is not a game dependency and must not enter exports. See
[foliage conversion](foliage.md) for the bounded probe and current limitations.

The selected Yongan town-NPC profile expands original NPC models, textures and
reachable motions only for its 23 declared definitions and 32 pinned point spawns.
Its source material/opacity interpretation follows `GameLib/ActorInstanceRender.cpp`
and its idle selection follows `GameLib/ActorInstanceMotion.cpp` / `RaceManager.cpp`.
Original sources and converted assets remain ignored; no source implementation
is copied. NPC shops, combat and quests are not established by model conversion.

| Source | Pinned revision/version | Use and license |
| --- | --- | --- |
| [Metin2 client archive](https://git.old-metin2.com/metin2/client) | `bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7` | Selected original bodies/default hair and general/intro/one-hand-or-fan motions for eight classic appearances, Yongan dependencies, UI/portraits/minimap tiles and two target-selection effects; originals and derivatives are ignored |
| [Pillow](https://github.com/python-pillow/Pillow/tree/12.1.0) | `12.1.0` in `tools/requirements-assets.txt` | Build-time decoding/cropping of selected original raster UI and target-effect texture assets; Pillow's own license applies independently of source art rights |
| [Carbon Blender tools](https://github.com/carbonenginejs/tools-blender/tree/8cba23114bf1d30c9da597c1ecf49271e00b939d) | `8cba23114bf1d30c9da597c1ecf49271e00b939d` | MIT importer/reader, downloaded with its license into `.cache` |
| [Native Godot SpacetimeDB SDK](https://github.com/flametime/Godot-SpacetimeDB-SDK/tree/f6c59d7068e5dacbde0559906746d0a6c5933ffb) | `f6c59d7068e5dacbde0559906746d0a6c5933ffb` | MIT; plugin version 0.3.2, vendored in `client/addons/SpacetimeDB` |
| [SpacetimeDB Rust module library](https://docs.rs/spacetimedb/2.8.3/spacetimedb/) | `spacetimedb = "=2.8.3"` | Apache-2.0 module dependency; exact dependencies are in `server/Cargo.lock` |
| SpacetimeDB runtime container | `clockworklabs/spacetime:v2.8.3`, digest pinned in `deploy/Dockerfile` | Server runtime, independent of the Rust module library's license; see image/upstream notices |
| Nginx proxy container | `nginx:1.28.0-alpine`, digest pinned in `deploy/compose.yaml` | HTTPS/static-file/WebSocket proxy; image and component notices apply |
| [Playwright Python](https://github.com/microsoft/playwright-python) | `1.55.0`, supporting packages pinned in `tools/requirements-browser.txt` | Apache-2.0, optional development-only browser integration runner; uses installed Chrome |
| [Godot MCP](https://github.com/mkdevkit/godot-mcp/tree/328e15f7d38092371b2aca8b81c40b8188bbe747) | `328e15f7d38092371b2aca8b81c40b8188bbe747` | MIT editor add-on and companion Node server, vendored with LICENSE files; development tooling |
| [cloudflared](https://github.com/cloudflare/cloudflared/releases/tag/2026.8.3) | `2026.8.3`, Linux amd64 | Apache-2.0; optional host-only tunnel binary downloaded into `.cache/cloudflared`, excluded from the game ZIP |
| [open-mt2](https://github.com/willianmarquess/open-mt2/tree/8d8800d470f0b69221886723eb5877a2ed9d9d8d) | `8d8800d470f0b69221886723eb5877a2ed9d9d8d` | Research reference only; its GPL-3.0 LICENSE conflicts with ISC package metadata; no implementation copied into this project |
| [Metin2 server archive](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318) | `7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318` | Full-game planning reference: C++ systems, quest APIs and data catalogs; source/data availability is not a redistribution grant; no implementation executed or copied |
| [NakiuS Metin2Client](https://github.com/NakiuS/Metin2Client/tree/40e2d9fef3bed9fa56a113001ae678efb72e06d3) | `40e2d9fef3bed9fa56a113001ae678efb72e06d3` | Narrow client-source comparison for planning; repository code license is MIT, original asset rights remain separate; no implementation copied |
| [Quantum Core X](https://github.com/MeikelLP/quantum-core-x/tree/ddab58ba493dfcedefd8b265513950f865edfffc) | `ddab58ba493dfcedefd8b265513950f865edfffc` | MPL-2.0 independent emulator; static gameplay/tooling comparison only, no implementation copied |

The Shaman weapon slice selects Fan+0 (vnum 7000) from the same pinned original
archive: `ymir work/item/07000.msm`, `ymir work/item/weapon/07000.gr2`,
`weapon_chogeup_02.dds` and `icon/item/07000.tga`. Its item values/restrictions come
from the pinned server `item_proto.txt` row 1164. These use the existing ignored
source and conversion directories and retain hashes in the generated receipts;
this selection does not alter the original assets' terms.

The wildlife profile selects vnums 101, 102, 108, 110 and 114, with the original
`monster/stray_dog`, `wolf`, `wild_boar`, `bear` and `tiger` model folders, their
reachable motions and bound textures. The pinned proto/name/client registrations
and conversion receipts retain provenance. These narrow original-asset selections
remain in ignored source/generated directories under the same asset terms.

The [full-game source audits](full-rebuild-plan.md#source-and-coverage-discipline)
record exact paths/symbols, feature flags, source-tree/registry metadata and
known gaps. Research snapshots stay under ignored `.cache/full-game-research/`;
tracked evidence contains metadata rather than third-party code or asset bytes.
The primary client archive has no code LICENSE at the inspected pin. A mirror's
license statement does not establish rights over every original contribution
or bundled asset. Publisher-domain community wiki pages are additional feature
discovery evidence with per-page revisions, not code dependencies or exact
retail balance specifications. No new bulk asset fixture is introduced by this
planning audit.

The installed engine used for tests is standard **Godot 4.7.2**; conversion uses
**Blender 5.2.1 LTS**. SpacetimeDB CLI/runtime and the Rust module dependency are
**2.8.3**. Version compatibility means the tested combination, rather than the
latest version of each dependency. Godot's runtime notices and addon licenses
belong in distributable packages; the export helper's manifest records what was
included. See [distribution.md](distribution.md).

Web/Linux export manifests record the selected Godot template's SHA-256. The
browser runtime uses the same standard engine/GDScript SDK as desktop. Playwright,
Blender, original archives, conversion caches and editor MCP code are not player
dependencies and are excluded from normal exported packs. Docker image pins are
separate from the committed Rust and Node dependency locks.

## Temporary public playtest hosting

`tools/share_server.py install` downloads the official Linux amd64 binary from
the pinned [cloudflared 2026.8.3 release](https://github.com/cloudflare/cloudflared/releases/tag/2026.8.3)
and requires this SHA-256 before installation or launch:

```text
f29324fe934d1e100617484c78deef803c4dc2cd351d645bbde42e96b4fccc5e
```

The binary lives at `.cache/cloudflared/2026.8.3/cloudflared`; it is a host tool,
not a player dependency. It connects the project's game gateway to Cloudflare's
Quick Tunnel service. The launcher uses its own local config and logs without
installing a global service. See [playtesting.md](playtesting.md) for the exposed
routes, temporary hostname behavior and the distinction between a development
tunnel and a stable hosted deployment. Cloudflare service availability is
separate from the Apache-2.0 license of its client binary.

## Native Godot networking SDK

The vendored directory is copied from upstream
`godot-client/addons/SpacetimeDB`. Its capitalized path is intentional: upstream
loads core schema scripts from that resource path. This is pure GDScript, so it
does not require the .NET engine or a native networking binary.

The exact pin uses `v3.bsatn.spacetimedb`, supported by the installed SpacetimeDB
2.8.3 server. The [server's v3 definition](https://github.com/clockworklabs/SpacetimeDB/blob/v2.8.3/crates/client-api-messages/src/websocket/v3.rs)
describes its use of the v2 message schema with coalesced messages. Actual Godot
tests verify authentication, subscriptions, typed row decoding, reducers,
replication, reconnects, and duplicate identities. SDK documentation contains
some older version examples, so the pinned source and these tests are the basis
for compatibility claims.

Three local adaptations are retained:

- Emit protocol and subscription error signals so `GameConnection` can show
  useful failures and clear stale state.
- Honor `SpacetimeDBConnectionOptions.save_token`; the application owns scoped
  token persistence instead of the SDK's default global token file.
- Omit raw authentication response bodies from console errors.

[UPSTREAM.md](../client/addons/SpacetimeDB/UPSTREAM.md),
`local-fixes.patch`, and `upstream-files.sha256.json` record the origin and local
differences. Preserve the [MIT license](../client/addons/SpacetimeDB/LICENSE)
when copying or updating the addon. Runtime uses no compression; Brotli is not
supported. Tables without primary keys are unsuitable for its ordinary cached
table API. The chosen client/server tables all have primary keys.

Generated game bindings live outside the vendored addon. Their manifest records
the SDK commit, server schema hash, and generated GDScript hashes. Regenerate
with `tools/generate_bindings.py`, and use `--offline` to reproduce them from the
committed schema. The generated code and third-party addon are excluded from
the project's owned-source formatter/linter; changes to the integration wrapper
are checked normally.

The [official SpacetimeDB Godot tutorial](https://spacetimedb.com/docs/tutorials/godot/)
uses its C# SDK with Godot .NET. That SDK was considered but is not a runtime
dependency of this standard-Godot client.

## Warrior fixture and conversion

The selected stationary-NPC extension imports City Guard 20354 (`guard_leader`),
its two model-referenced textures and five motion clips from the same pinned
client. It uses pinned server NPC/name/placement metadata as reference data.
The shared rigid skinning adapter follows the source renderer's composite bone
operation without copying its implementation. See [world-content](world-content.md)
for pins, commands and current limits. These assets and derivatives remain ignored.

The asset fetcher verifies each downloaded file against the archive's Git blob
hash and records SHA-256 values in `assets/source/warrior/manifest.json`.
It downloads model, textures, and four animation/metadata pairs under
`bin/pack/PC/ymir work/pc/warrior/`. No original executable or server binary is run.
This fixture is a small subset of the archive, not the complete Metin2 asset set.

The Carbon source is loaded inside Blender without registering its EVE-focused
add-on. Our adapter adds the old 32-bit GR2 magic, translates legacy inline float
curves, samples them with Carbon's spline sampler, and restores the model's
initial placement for the bind skeleton. Material texture names come from the
original GR2 material bindings. The original assets and downloaded Carbon source
remain unchanged.

The tested warrior has three meshes, 2,207 source vertices, 2,268 triangles, 75
bones, and wait/walk/run/attack clips. Source curves are sampled at approximately
30 fps. This validates a useful fixture path; it does not establish fidelity for
every GR2 variant, map, hairstyle, equipment attachment, or effect, nor
frame-for-frame agreement with the original Granny runtime.

The P1 `p0-warrior-dog` profile expands this narrow fixture to the selected
male Warrior, Sword+0 vnum 10 and Wild Dog 101. It records pinned source paths,
source hashes, normalized motion/action metadata, converted GLB hashes and
generated presentation/action hashes. The selected 27 Warrior and 13 Wild Dog
motion records are not a license to redistribute the original source files or
an assertion that every original race, mob, weapon, effect or animation is
supported. Original GR2/MSA/MSM/MSS files, Granny and Blender runtimes, and
source archives remain build-time inputs only and are rejected from player
exports. The generated output remains ignored under the same distribution
constraints described above; see [P1 actor content import](content-import.md).

## Target-selection effect fixture

The same client pin supplies exactly two bounded mesh effects:
`click_select.mse/.mde` and `click_glow_select.mse/.mde`, plus their four named
TGA/JPEG textures. `tools/import_target_effects.py --fetch` uses the existing
archive reader to fetch nine explicit conversion inputs and verifies their Git
blob IDs, byte counts and SHA-256 values before parsing. Resolving those paths
also downloads `bin/pack/Index` and caches archive tree inventory metadata. The
conversion provenance set contains the nine inputs; it excludes the Index and
inventory metadata. MSE and MDE files, downloaded images, conversion caches,
Blender files and development reports stay in ignored source/local directories.
The authoritative player inputs are the generated runtime catalog, two GLBs and
four PNGs; Godot may retain remapped resources derived from those files inside
its package.

The MDE/MSE parser and Blender adapter are project code implemented from direct
format and pinned-client behavior inspection. GPL research implementations were
not copied. Pinned client sources were consulted for D3D blend constants, D3DX
color-byte quantization, mesh-frame stepping, the strict frame boundary and the
20-advance cap. This source reading does not change the original assets' rights
or grant redistribution rights.

The converter records exact source/output hashes, coordinate conversion,
unsupported records and the known Godot material/playback boundary. Isolated
Godot checks validate geometry, imported animation and selected rendered samples;
the actual-PCK audit also checks decoded texture bytes. This is evidence for the
two named fixtures only. It does not establish frame-for-frame, color-space or
pixel-identical parity with the original D3D client, and it does not generalize
to other MSE effect types, particles, sounds or arbitrary MDE files. See
[Target-selection effect fixture](content-import.md#target-selection-effect-fixture).

## Original-map conversion

The [map pipeline](map-import.md) reads the small property catalog to resolve
CRCs, then fetches only the selected map's models/material dependencies. Its
`sources.json` records Git blob and SHA-256 hashes at the same client pin.
Original `Area.cpp`, `AreaTerrain.cpp`, `Terrain.cpp`, `Terrain.h`, `TerrainType.h`,
`TextureSet.cpp`, `GrpObjectInstance.cpp`, `EterPackManager.cpp`, `AttributeData.cpp`,
`CollisionData.cpp` and `UserInterface.cpp` were consulted for terrain, placement,
collision and pack-order semantics;
their implementation was not copied. The project's static-model adapter uses
Carbon's geometry importer and explicitly restores sparse material bindings.
The existing animated-warrior converter is unchanged.

The shared Yongan bake reads original model attribute collision shapes and walk
triangles together with terrain, blocking attributes and water. Generated
`server/content/` files and client collision/chunk derivatives are ignored along
with other converted original assets. `yongan.json` records the collision-source
hashes and generated content hash. These additions do not import another game's
server code or change the original assets' terms.

The first enemy, Stone Sentinel, and its gold pickup use project-authored
procedural Godot geometry. They introduce no downloaded monster mesh, animation
or effect fixture, and should not be described as an original Metin2 mob import.

## Original UI fixture

`tools/import_metin_ui.py` fetches an explicit selection from the same pinned
client archive: taskbar gauges/button states, quickslot legends, inventory and
equipment art, common windows/tooltips, chat/minimap controls, sword icon `00010`
and red-potion icon `27001`. It converts 196 UI images and stitches 20 original
Yongan DDS minimap tiles into one 1024 × 1280 image, using 260 source files.
The expanded fixture includes the separate original 171 × 214 Yongan atlas,
chat-history title/scrollbar parts, working minimap controls and selected
English account/character-entry backgrounds, panels, empire map/flags, warrior
title and button states. `tools/import_metin_intro.py` explicitly lists that
entry subset and its eight original layout/behavior references; it does not
recursively import the archive or expand the warrior model fixture.

`client/assets/imported/ui/manifest.json` records Git blob/SHA-256 hashes for
sources, atlas/crop information, PNG and decoded RGBA hashes, pixel dimensions
and consulted references. Output retains decoded RGBA pixels without recoloring/resizing;
each PNG is reopened to verify its pixel round trip. The converter pins lossless
Godot imports without mipmaps, automatic 3D compression or alpha-border changes;
the actual PCK audit checks every loaded UI texture's RGBA bytes against its
manifest hash. `GrpSubImage.cpp` was
consulted for `.sub` descriptor semantics, and selected taskbar, inventory,
minimap, chat, tooltip, system and account/character-layout sources informed presentation. No
downloaded Python/C++ is executed or copied as runtime implementation.

Pillow is pinned and installed by development setup; it is not shipped in the
player runtime. Original UI art has the same separate asset-rights constraints
as the warrior/map, and both its originals and converted files remain ignored.
The pinned English locale specifies Tahoma at 12, 14 and 9, and original
rendering uses GDI; equal Godot size numbers do not establish equal metrics.
This fixture adds no font. No Microsoft font is redistributed, and neither
original text rendering nor complete behavioral parity has been established. See [UI assets](ui-assets.md) for the precise
source/layout contract and remaining fidelity limits.

## Gameplay reference

`open-mt2` is a TypeScript/Node Metin2 server emulator. Its gameplay rules, data
organization, and tests can inform later work, but its TCP protocol, process
lifecycle, and storage are not a drop-in SpacetimeDB module or Godot client.
The current Rust gameplay implementation is project code. See
[open-mt2.md](open-mt2.md) for the detailed assessment and licensing distinction.

The Sword Spin fixture adds only the selected male/female `skill/palbang.msa`
animations and their referenced GR2 clips, plus `skill/warrior/palbang_01.sub`.
They use the same pinned original client and Blender conversion path as the
existing character/UI fixtures. English skill rows and the international power
array are read as data by `tools/build_skill_catalog.py`; the compiler records
source revision and hashes. Locale differences, formula selection and unsupported
skill particles are documented in [skills](skills.md). No legacy runtime or
additional external project is bundled.

## Authored training model

`tools/blender_training_dummy.py` generates project-authored geometry/materials
from `content/profiles/training-dummy.json`; the model contains no third-party game
assets. Its editable Blender source and conversion receipt stay under `.local/`;
only its generated GLB and runtime manifest are installed/exported. The selected
full-class motion/UI expansion uses the same pinned client revision above; it adds
88 normal-grade skill motions and their selected icons, not the complete archive.

The bounded `yongan-season1-npcs` profile adds eight original point-placement NPCs,
including the static memorial and flowers, under the same asset restrictions.
Pinned `GameLib/RaceManager.cpp::__LoadRaceData` supplies the `#folder/shape.msm`
registration rule; `EterGrnLib/Material.cpp::__GetImagePointer` supplies model-local
texture resolution. These source files are references for independently written
import logic. Original GR2s, textures, converted GLBs and receipts remain ignored.

The bounded `yongan-area-npcs` profile selects six additional stationary NPCs and
pins `src/game/src/char_manager.cpp` alongside `regen.cpp`. Their `SpawnMobRange`
and point-spawn branches define the preserved centimetre ranges, retry count and
different heading policies. These are source-backed definitions for a future
server-owned placement implementation, not imported legacy server code.

## Arrow material color transfer

`projectile_mesh_effect.gd` implements the opaque source-color /
inverse-destination-alpha case described by Microsoft's
[D3DBLEND reference](https://learn.microsoft.com/en-us/windows/win32/direct3d9/d3dblend).
For opaque source and destination alpha one, the RGB result is source RGB squared.
Transparent viewports and unsupported material recipes reject configuration.
This does not establish the original client's destination-alpha state.

Godot Compatibility's
[color-transfer functions](https://raw.githubusercontent.com/godotengine/godot/master/drivers/gles3/shaders/tonemap_inc.glsl)
were consulted to diagnose dark-pixel error observed in the installed engine.
The project-authored shader uses bounded Newton iteration to invert that numerical
transfer function; its polynomial coefficients are recorded engine behavior,
not a copied engine implementation. Godot is MIT licensed; no additional engine
source or binary is bundled. This adapter is qualified against the installed
Godot 4.7.2 Compatibility renderer; engine changes require rerunning the rendered
256-step pixel ramp. Nonlinear tone mapping, fog, other renderers and original
client pixel parity are not covered by that qualification.

The independently authored ordinary-mob damage finalizer uses the existing pinned
server reference (`battle.cpp` and `char_battle.cpp`) to distinguish NPC normal,
normal-range and magic damage, including floor, resistance and critical ordering.
No original implementation is copied or new reference dependency downloaded.


## Selected original ground items

`tools/import_ground_items.py` independently interprets the pinned client
`GameLib/ItemManager.cpp::LoadItemList` and `ItemData.cpp::SetDefaultItemData`.
It fetched the English item-list metadata and only the selected Yang/red-potion
models (`money.gr2`, `medicine_R.GR2`) and their diffuse textures (`money.dds`,
`medicine.dds`) at client pin `bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7`.
Original inputs and converted derivatives stay ignored; no original implementation
was copied. Conversion reuses the pinned Carbon reader and existing Blender tool.
Original asset rights remain distinct from tooling licenses. See [ground items](ground-items.md).

The Warrior ground-plane renderer and birth-heading adapter independently follow
`EffectLib/ParticleInstance.cpp:Transform` and
`ParticleSystemInstance.cpp` at the pinned client revision above. Color operation 5
uses doubled RGB modulation per Microsoft's
[D3DTEXTUREOP reference](https://learn.microsoft.com/en-us/windows/win32/direct3d9/d3dtextureop).
The adapter preserves the original separate alpha modulation; these references do
not establish pixel parity across the original Direct3D and Godot renderers.

`tools/motion_effects.py` independently adapts the effect-event loading contract in
`GameLib/RaceMotionDataEvent.h` and attachment branch behavior in
`GameLib/ActorInstanceMotionEvent.cpp` at the existing client pin. The selected
MSA source files remain ignored; no original implementation is copied.

The motion-effect linker also follows `GameLib/ActorInstanceAttach.cpp:AttachEffectByID`
for missing follow-bone fallback and the separate capture-bone branch in
`ActorInstanceMotionEvent.cpp`. The selected original female Warrior GR2 lacks
`Bip01 Footsteps`; source and converted skeletons were compared using the existing
pinned Carbon reader and legacy-header adapter, without modifying the asset.
