# Third-party sources

These are the source revisions used by the current project. Code licenses and
original game asset rights remain separate.

| Source | Pinned revision/version | Use and license |
| --- | --- | --- |
| [Metin2 client archive](https://git.old-metin2.com/metin2/client) | `bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7` | Warrior, selected Yongan dependencies, original UI fixture and minimap tiles; originals and derivatives are ignored |
| [Pillow](https://github.com/python-pillow/Pillow/tree/12.1.0) | `12.1.0` in `tools/requirements-assets.txt` | Build-time decoding/cropping of selected original raster UI assets; Pillow's own license applies independently of source art rights |
| [Carbon Blender tools](https://github.com/carbonenginejs/tools-blender/tree/8cba23114bf1d30c9da597c1ecf49271e00b939d) | `8cba23114bf1d30c9da597c1ecf49271e00b939d` | MIT importer/reader, downloaded with its license into `.cache` |
| [Native Godot SpacetimeDB SDK](https://github.com/flametime/Godot-SpacetimeDB-SDK/tree/f6c59d7068e5dacbde0559906746d0a6c5933ffb) | `f6c59d7068e5dacbde0559906746d0a6c5933ffb` | MIT; plugin version 0.3.2, vendored in `client/addons/SpacetimeDB` |
| [SpacetimeDB Rust module library](https://docs.rs/spacetimedb/2.8.3/spacetimedb/) | `spacetimedb = "=2.8.3"` | Apache-2.0 module dependency; exact dependencies are in `server/Cargo.lock` |
| SpacetimeDB runtime container | `clockworklabs/spacetime:v2.8.3`, digest pinned in `deploy/Dockerfile` | Server runtime, independent of the Rust module library's license; see image/upstream notices |
| Nginx proxy container | `nginx:1.28.0-alpine`, digest pinned in `deploy/compose.yaml` | HTTPS/static-file/WebSocket proxy; image and component notices apply |
| [Playwright Python](https://github.com/microsoft/playwright-python) | `1.55.0`, supporting packages pinned in `tools/requirements-browser.txt` | Apache-2.0, optional development-only browser integration runner; uses installed Chrome |
| [Godot MCP](https://github.com/mkdevkit/godot-mcp/tree/328e15f7d38092371b2aca8b81c40b8188bbe747) | `328e15f7d38092371b2aca8b81c40b8188bbe747` | MIT editor add-on and companion Node server, vendored with LICENSE files; development tooling |
| [cloudflared](https://github.com/cloudflare/cloudflared/releases/tag/2026.8.3) | `2026.8.3`, Linux amd64 | Apache-2.0; optional host-only tunnel binary downloaded into `.cache/cloudflared`, excluded from the game ZIP |
| [open-mt2](https://github.com/willianmarquess/open-mt2/tree/8d8800d470f0b69221886723eb5877a2ed9d9d8d) | `8d8800d470f0b69221886723eb5877a2ed9d9d8d` | Research reference only; its GPL-3.0 LICENSE conflicts with ISC package metadata; no implementation copied into this project |

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
