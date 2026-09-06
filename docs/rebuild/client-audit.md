# Original client, UI and content audit

This audit turns the original client into a rebuild checklist. It does not propose
running the old executable, copying its implementation into Godot, or preserving
its TCP protocol. The target is a recognizable classic Metin2 profile informed by
this archive; the archive also contains later, conditional systems, so its revision
does not by itself date every piece of gameplay:
movement and camera response, dense system screens, native-pixel art, animation
timing, effects and sound cues. Godot, SpacetimeDB, the content pipeline and the
operator tools should be modern, measurable and maintainable.

The primary source is the [old-metin2 client archive][primary] at immutable commit
`bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7`. Its recursive API tree has 60,161
entries, of which 56,037 are blobs, across 61 cached pages. For this audit, 842
files and 7,396,003 bytes were downloaded and Git-blob verified: every file under
`src/`, Python beneath `bin/pack/root`, `bin/pack/uiscript` and
`bin/pack/locale_en`, plus eight named build/catalog files. No bulk art, model or
sound collection was downloaded. The ignored manifests are
`.cache/full-game-research/client/source-manifest.json` and
`.cache/full-game-research/client/supplementary-manifest.json`.

The tracked [client inventory](evidence/client-inventory.json) records the exact
filters, UI module names, packet names, map settings paths, format counts and
known parser gaps. The [canonical plan](plan.json) contains 32 `CLI-*` feature rows
with immutable path/symbol evidence and behavior dependencies. Counts below are
tree counts, not decoded-record counts. They include patch-pack variants and
virtual-path overrides; equal blobs are not deduplicated.

## What the original client establishes

The source establishes four distinct contracts:

1. C++ owns the window/input/render/audio substrate, resource formats, actor
   presentation, packet decoding and Python bindings.
2. Python owns phase flow, screen composition, focus, local interactions and the
   routing of network callbacks into UI controllers. `game.py` is the input and
   world-window coordinator; `interfacemodule.py` composes the HUD and system
   windows.
3. Pack data supplies race/model definitions, motion metadata, effects, sounds,
   maps, item/mob/skill catalogs, layouts, localized strings and images. Pack
   order matters when the same virtual path occurs in several patch archives.
4. The server is implied by packet names and callbacks, but client source cannot
   prove server rules, live feature enablement, exact balance or persistence.

The Godot rebuild should keep these as data and behavior boundaries, without
recreating the old embedding architecture. Generate typed Godot resources and
scenes from pinned data. Keep server-owned action and state contracts in
SpacetimeDB. Preserve classic presentation through fixtures, measured timings
and reference captures.

## Native stack and dependencies

The solution contains 17 C/C++ projects: the executable and configuration tool,
`GameLib`, `EterGrnLib`, `EterLib`, `EterPythonLib`, `EffectLib`, `MilesLib`,
`PRTerrainLib`, `SpeedTreeLib`, `EterPack`, `EterImageLib`, `EterBase`,
`EterLocale`, `ScriptLib`, `SphereLib` and `CWebBrowser`. The [solution][solution]
pins Win32 Debug, Release and Distribute configurations. The executable's
[project file][ui-project] uses `USE_LOD` in all profiles; `_DISTRIBUTE`,
`HAVE_SNPRINTF` and `DUNGEON_WORK` differ by profile. These switches are build
variants, not a list of complete game features.

The [vcpkg manifest][vcpkg] names Crypto++, DevIL, DirectX SDK June 2010, libzip
with zstd, LZO, Python 2.7.18 and WTL at baseline
`bd602277bf7fc3188b3d086b302c6840464db900`. The executable also links Miles
Sound System, SpeedTreeRT, DirectInput/DirectDraw/DirectShow-related Windows
libraries and ships Granny 2.4/2.9, Miles and SpeedTree headers/libraries in
`extern/`; [startup][client-startup] registers Granny logging, pack-backed Miles
loading and the legacy embedded browser. Those original binaries are not a
portable dependency plan and their presence is not a license grant.

Modern replacements are already selected for the foundation: standard Godot
4.7.2 for windowing, input, rendering, audio and Web export; the pinned Carbon
reader plus Blender for selected GR2 conversion; Pillow for selected image
conversion; and the GDScript SpacetimeDB SDK for authenticated subscriptions and
intents. Still unresolved are broad GR2 compatibility, SpeedTree conversion or
replacement, full effect-script translation, exact old material blending,
original font metrics and a licensed input for any non-system font.

The primary archive has no code `LICENSE`; its [README][primary-readme] warns
about rights and provenance. Original game art, model, animation, audio and data
rights remain separate from code-reference rights. A supplementary comparison
used [NakiuS/Metin2Client][supplementary] at
`40e2d9fef3bed9fa56a113001ae678efb72e06d3`. That repository contains an MIT
license for its code and shows the same race/motion/attachment architecture, but
its `Locale_inc.h` selects Singapore with costume and energy only. It is useful
evidence that build profiles diverge; it is not the canonical feature set and
does not license original assets.

## Feature and screen inventory

Availability has three levels throughout this section:

- **present** means a source module, layout or packet name exists;
- **compiled** means the pinned Europe `Locale.h` enables its client branch;
- **implemented** means the Godot client and authoritative server complete and
  verify it.

Only the first two can be inferred from this source. The pinned Europe
[locale profile][locale-profile] compiles costume, energy, Dragon Soul and new
equipment. [PythonApplicationModule.cpp][app-module] exports those values plus
`USE_OPENID` and `OPENID_TEST` to Python. No switch proves reachable UI, matching
server behavior, complete data or a working live service.

| Feature family | Original evidence and visible contract | Rebuild boundary and acceptance |
| --- | --- | --- |
| Entry and lifecycle (`CLI-001`) | `networkmodule.py::MainStream`; [select phase][phase-select] sends empire/create/select/destroy/change-name actions and receives success/failure. Python stages cover logo, login/connect, empire, creation, selection and loading. | Keep existing authenticated account flow, expand to all empires/classes/sexes/shapes, original intro motions and errors. Two real accounts must create/select/switch/reconnect/logout through rendered controls; screenshots cover every stage and unavailable/server-rejected states. |
| Movement, smart mouse and camera (`CLI-002`) | [mouse input][mouse-input] `CPythonPlayer::NEW_SetMouseSmartState` prioritizes item, actor and ground actions; [keyboard input][keyboard-input] drives directional state and fishing cancellation; `game.py::GameWindow.__BuildKeyDict` maps movement, camera, pickup, quickslots and panels. | Send finite validated movement/action intents. Match turn, run, click priority, cursor, orbit/zoom/pitch and cancellation feel. Test obstacles, click-versus-drag, UI/chat focus, corrections and latency with fixed input traces. |
| Actors and presence (`CLI-003`) | `NetworkActorManager::CNetworkActorManager` and [actor packet handlers][phase-actor] create, update, move and remove characters; `InstanceBase` composes race, shape, hair, weapon, mount, effects, guild/alignment and text tails. | Subscribe only to authorized public state and interpolate sequenced updates. Two clients must observe join, motion, appearance, label changes, disconnect removal and reconnect; dense-town captures verify culling and readability. |
| Combat, PvP, skills and affects (`CLI-004`) | [game packets][phase-game] include attack, target, damage, dead/stun, motion, skill, cooldown, affect, PVP/duel, fly-target and projectile paths. `ActorInstanceBattle` and motion events present hits and reactions. | Server validates target, range, timing, cost, cooldown, result and damage. Share action IDs and normalized timing metadata; exercise interrupts, death/revive, ranged and melee skills, PvE/PvP, correction and rejection. |
| Items and equipment (`CLI-005`, `CLI-007`) | [item packets][phase-items] cover set/update/delete/use/drop/pickup/ownership/move/quickslot/safebox/mall. `uiinventory.py::InventoryWindow` handles bag/equipment/costume/belt, socketing/refine and drag/drop; `uitooltip.py::ItemToolTip` renders definitions and attributes. | Compile authoritative item definitions and separate visual/icon dependencies. Verify every size, stack, slot, race/sex limit, socket/attribute, confirmed mutation, ownership/expiry and equip appearance; never mutate counts optimistically. |
| Taskbar and quickslots (`CLI-006`) | `uitaskbar.py::TaskBar` plus [English taskbar layout][taskbar-layout] provide HP/SP/stamina/EXP, two groups of four quickslots, pages, mouse mode, notification buttons, energy and gift states. | Preserve native art and classic keys while supporting declared scale policy. Automate all button states, cooldown completion, bind/clear/activate/page behavior and per-identity settings; values come from authoritative state. |
| Chat and whisper (`CLI-008`) | `uichat.py::ChatWindow/ChatLogWindow`, `uiwhisper.py::WhisperDialog` and [CPythonChat][python-chat] define normal/party/guild/shout channels, history, fade, links and whisper buttons. | Reproduce ordering, fade, resize, focus, history and safe links. Validate channel membership, rate/length rejection, sanitization, blocks, IME and reconnect policy using independent identities. |
| Minimap and atlas (`CLI-009`) | [CPythonMiniMap][minimap-cpp] plus `uiminimap.py::MiniMap/AtlasWindow` define zoom, player/NPC/warp/target markers, tooltips and coordinates. | Compile per-map transforms and marker catalogs. Compare known source points at each zoom and edge, validate axes/bounds and only render subscribed or definition-backed markers. |
| Character, skill, affect, emotion and quest list (`CLI-010`) | `uicharacter.py::CharacterWindow`, `PythonPlayerSkill.cpp`, `uiaffectshower.py` and `emotion.py` expose status/skill/emotion/quest tabs, grades, point spending, timers, alignment and paired actions. | Drive all values from progression definitions and confirmed state. Verify skill groups/grades, affects, upgrades/rejections, cooldowns, emotes and timed quest entries with classic layout captures. |
| Quest dialogue (`CLI-011`) | `PythonEventManager::CPythonEventManager`, `uiquest.py::QuestDialog`, script/confirm/input/item-select packet names and NPC/target markers form the client quest surface. | Convert an explicitly supported legacy subset into bounded declarative events; never execute archive Python or unrestricted Lua. Acceptance walks every branch, persisted wait, choice, timeout, disconnect and localization variant. |
| Commerce and storage (`CLI-012`–`CLI-014`) | `uishop.py::ShopDialog`, `uiprivateshopbuilder.py`, `uiauction.py::AuctionWindow`, `uiexchange.py::ExchangeDialog`, `uisafebox.py`, `uirefine.py`, `uiattachmetin.py` and `uicube.py` cover NPC/player shops, auction UI, mall, exchange, storage, refine, sockets and crafting. | Treat auction as conditional until a matching live contract is selected. Use atomic server transactions, versioned previews and idempotent requests. Test stale offers, simultaneous changes, bounds, cancellation/disconnect, failure/success and privacy. |
| Party and messenger (`CLI-015`) | `uiparty.py::PartyWindow/PartyMenu`, `uimessenger.py` and party/messenger packet groups cover invite/answer, role/state, linked VID, HP/affects, distribution, friend presence and whisper entry. | Server owns membership, role permissions and visibility. Three-client scenarios cover invites, role changes, leave/kick, reconnect/offline, blocks and party-only data. |
| Guild (`CLI-016`) | `uiguild.py::GuildWindow` and [guild packet dispatch][phase-game] expose base info, grade authority, member list, board, skills, wars, marks/symbols, treasury, land and building screens. | Deliver basic guild, war and land/building as explicit slices while keeping the six-page shell. Validate every authority on the server, concurrent money/GSP changes, war lifecycle, sanitized bounded mark uploads and reconnect. |
| Marriage and wedding (`CLI-017`) | `RecvLoverInfoPacket`, `RecvLovePointUpdatePacket`, `uiaffectshower.py::LoverStateImage` and [motion names][motion-header] for kiss, French kiss, slap and wedding dress prove a distinct presentation family. | Preserve paired animation and wedding presentation, backed by server relationship/event state. Two clients verify consent/refusal, proximity, synchronized markers, attire, map/event lifecycle and disconnect recovery. |
| Fishing, mining and mounts (`CLI-018`) | `RecvFishing`, `SendFishingPacket`, `RecvDigMotionPacket`, `RecvMountPacket`; the motion enum includes six fishing actions and mounted modes for every classic weapon family. | Validate tool, location and state on the server. Cover cast/react/catch/fail/cancel timing, rewards, mining/digging and rider/mount alignment for every supported weapon mode. |
| Costume, belt, Dragon Soul and energy (`CLI-019`) | The Europe profile compiles all four feature defines. `uiinventory.py` conditionally opens costume/belt; `uidragonsoul.py` includes inventory/decks/refine; English layouts include Dragon Soul and energy windows. | Track each as a separate product capability. Prove real definitions, persistence, server validation, UI reachability, appearance/effect state and reconnect before marking implemented. |
| Options, help, restart and web (`CLI-020`) | `uisystem.py`, `uioption.py`, `uisystemoption.py`, `uihelp.py`, `uiselectmusic.py` and `uiweb.py`; [CWebBrowser][browser] embeds Windows `IWebBrowser2`. | Use Godot-native settings and explicit safe external navigation. Test persistence, live visual/audio/input changes, block/PvP settings, focus and restart lifecycle. Exclude COM/browser source and developer controls from player exports. |

The complete Python inventory is intentionally retained in the evidence JSON:
74 root Python modules, 79 generic UIScript modules and 18 English modules. Of
the root set, 46 are named `ui*.py`. It includes smaller but real surfaces that
must not disappear from the plan: auto-ban quiz, guild-war accept/declare,
equipment inspection, mark upload/list, money/password/question dialogs, map
name and player gauge, point reset, music selection, restart, tips, virtual
keyboard/IME and seasonal taskbar variants.

## Protocol behavior checklist

`Packet.h` contains 82 distinct `HEADER_CG_*` names and 128 distinct
`HEADER_GC_*` names under a clearly defined token filter. Across
`PythonNetworkStream*.cpp`, 309 top-level `CPythonNetworkStream` definitions
span offline, handshake, login, select, loading, game, actor and item paths.
The evidence JSON enumerates every header and summarizes each source file.

These names are useful because they expose omitted behavior:

- lifecycle, authentication variants, phase changes, ping/time synchronization,
  channel status, warp and disconnection;
- actors, observers, movement, motion, mount, walk mode, target and damage;
- item, shop, exchange, safebox, mall, quickslot, refine and Dragon Soul;
- chat, whisper, messenger, party, guild, land, lover, fishing and dungeon;
- quest script/confirm/input/item-select, NPC/target markers and affects;
- legacy integrity/authentication hooks such as CRC, XTrap, HackShield, matrix
  card, Passpod and OpenID.

The rebuild must not reproduce those packed structs. Each feature gets typed
tables/subscriptions and validated reducers, with explicit rejection and
connection-lifecycle behavior. Client-visible phase state should distinguish
request sent, server accepted, subscription confirmed, recoverable disconnect,
session refresh and terminal error. Automated acceptance requires two
independent identities on one actual server; queried rows and locally animated
actors are not sufficient evidence.

Legacy anti-cheat and integrity code is evidence for a separate threat model,
not a porting requirement. Server authority, input validation, account/session
security, rate limits, release integrity and abuse detection replace relevant
risks. `ProcessScanner`, CRC, XTrap/HShield and hidden client commands should not
be copied without a current threat and platform analysis.

## Content and format inventory

| Format/catalog | Tree count | Original reader/consumer evidence | Current coverage and required work |
| --- | ---: | --- | --- |
| C++ `.cpp` / `.h` | 326 / 295 | The complete `src/` tree was cached for inspection. | Reference only; do not port DirectX/Python embedding as runtime code. |
| Python `.py` | 430 | `PythonLauncher`, Python binding modules, `ui.py::PythonScriptLoader`. | Selected layouts were consulted; general import must parse data without executing code. |
| GR2 `.gr2` | 8,902 | [CGraphicThing::OnLoad][gr2-load] reads models/motions; `CGrannyModelInstance` binds animation and linked skeletons. | One warrior/four-motion fixture only. Enumerate versions, rigid/deformable meshes, skeleton signatures, LOD, pivots, materials and animations. |
| Race/item `.msm` | 2,884 | [CRaceData::LoadRaceData][race-load] reads base model/tree/attribute/motion list, shapes, skins, hair and attachments. | No general compiler. Parse all overrides and emit normalized appearance/attachment resources with dependency hashes. |
| Motion `.msa` | 6,393 | [CRaceMotionData::LoadMotionData][motion-load] reads GR2 path, duration, accumulation, combo, attack, loops and event records. | Four simple clips converted; batch modes/events/timing remain. See the dedicated motion contract below. |
| Motion sound `.mss` | 3,637 | `CRaceMotionData::LoadSoundScriptData` and `NSound::LoadSoundInformationPiece`. | Preserve event time/path/3D policy in normalized motion data; map to Godot audio. |
| Effect `.mse` / mesh `.mde` / fly `.msf` | 1,153 / 112 / 98 | [CEffectData::LoadScript][effect-load], effect mesh and [CFlyingData::LoadScriptFile][fly-load]. | Unparsed. Build safe readers for particles, mesh frames, lights, billboards, blend/depth/color/alpha, attachments, projectile paths and sounds. |
| Environment `.msenv` | 61 | `MapOutdoor::Load` and environment/sky/lens-flare classes. | Unparsed broadly; normalize lighting, fog, sky, lens flare, filters, wind and ambient/BGM references. |
| Model attributes `.mdatr` / property `.prb` | 1,180 / 1,128 | `CAttributeData::OnLoad`, collision loaders and `PropertyManager`. | Selected Yongan collision/property chain works; broaden shape types, flags, object kinds and precedence. |
| SpeedTree `.spt` | 118 | `CSpeedTreeForest::GetMainTree` and `SpeedTreeWrapper`. | Unsupported. Establish licensed conversion or project-authored replacements, including wind, season, LOD, billboard and collision behavior. |
| Map `.atr` / `.wtr` / `.raw` | 1,353 / 1,278 / 3,915 | Terrain/area readers load blocking, water, height/tile/shadow data. | Yongan supported in part. Validate every selected map, indoor/portal semantics and multi-level walk surfaces. |
| Images `.dds` / `.tga` / `.jpg` / `.png` / `.sub` | 8,178 / 4,191 / 571 / 2 / 1,957 | `CGraphicImage::OnLoad`, [CGraphicSubImage::OnLoad][sub-load], DevIL/JPEG and UI widgets. | 196 selected UI outputs and Yongan minimaps. Generalize atlas/layout import, color-space and alpha/blend rules, lossless UI verification and target-specific compression. |
| Audio `.wav` / `.mp3` | 1,601 / 34 | [CSoundManager][sound-manager] handles 2D/3D sound, listener, history and streamed music. | No catalog import. Normalize loops, crossfades, attenuation, event binding, ambient zones and browser start/resume behavior. |
| Root catalogs | named paths | `item_proto`, `mob_proto`, `skilldesc`, `skilltable`, `npclist`, `atlasinfo`, pack `Index`. | Presence only. Identify exact schema/version, parse defensively, join localization/visuals and generate authoritative server definitions. |

Character packs alone show the batch scale: `PC` has 2,705 files, `pc2` 1,739,
`Monster` 3,092, `monster2` 1,359, `NPC` 829, `item` 2,515 and `icon` 1,952.
Those counts use literal pack-root paths and therefore do not merge override
packs. Player MSA paths cover male/female warrior, assassin, sura and shaman;
general, one/two-hand, dual-hand, bow, fan, bell, fishing, horse, mounted weapon,
skill, action, intro and wedding families. A broad `.msa` count is not a count of
unique playable motions because patch packs and weighted variants overlap.

## Motion, rig and appearance compiler

This is an early foundation, not late content polish. The original [motion enum
and data model][motion-header] defines wait/move/attack/combo/damage/knockdown,
death, skill, stand-up, event and fishing types. Modes cover unarmed/general,
one-hand, two-hand, dual-hand, bow, fan, bell, fishing, horse, each mounted weapon
family and wedding dress. Named actions also cover intro poses, spawn, fishing,
digging, dances, paired affection/slap motions and social emotions.

MSA data is more than an animation filename. `LoadMotionData` requires duration
and can load:

- accumulation/root displacement;
- combo pre-input, direct-input and limit times;
- attack type, hit type, stiffness/invisibility/external force, attack start/end,
  attack bone/weapon length and time-sampled hit positions;
- loop count, cancel permission, loop start and end;
- timed effect, effect-to-target, screen wave, special attack, sound, fly,
  character show/hide and warp events. The header defines screen flashing too,
  while the inspected loader switch does not construct it; preserve that as a
  source inconsistency to resolve, not a silently supported event.

The compiler should:

1. Resolve each race's MSM, motion-list path and pack precedence. Expand shape,
   skin, hair, smoke and attachment dependencies. Record missing and conflicting
   virtual paths.
2. Decode GR2 model and animation data with source hash, format signature, axes,
   units, rest/bind transform, hierarchy, inverse binds, weights, pivots and
   materials. Compute a skeleton signature before sharing a library or retargeting.
3. Normalize every MSA/MSS event and measured curve duration. Generate stable
   action and clip IDs, Godot `AnimationLibrary`/state-machine resources and a
   matching server action-definition artifact. Root presentation and server
   displacement must not apply twice.
4. Generate attachment resources for `PART_MAIN`, `PART_WEAPON`, `PART_HEAD`,
   `PART_WEAPON_LEFT` and `PART_HAIR`. The [attachment path][attach] links models
   to named bones, starts weapon traces and attaches race/item collision and
   effects. Validate every referenced bone against the skeleton signature.
5. Cache by all source/dependency hashes, reader version, Blender/Godot versions
   and conversion settings. Rebuild only affected closures and make an offline
   build reproduce identical manifests.
6. Produce turntables, motion strips/video, bind/extreme pose probes, loop seams,
   root paths, event/hit-window timelines, bone/grip overlays, weapon trails and
   bounds. Compare identical cameras/times in Blender, Godot native and Web.

The first acceptance matrix must include male/female variants of all four classic
classes, a same-signature and different-signature rig, one- and two-hand swords,
dual daggers, bow/projectile, fan, bell, armour, hair, costume, rider/mount, NPC,
nonhumanoid monster, death/revive, skill, emote and wedding attire. Loading a GLB
does not prove deformation, attachment or timing fidelity.

## Effects, materials, rendering and sound

The original renderer is Direct3D 9 with fixed-function-style state management.
[Granny material loading][material] reads diffuse and opacity maps, two-sided
extended data and optional specular/sphere-map behavior. Effect scripts drive
particles, animated mesh textures and simple lights; instances apply billboard,
source/destination blend, color-operation and time-varying alpha. Outdoor maps
add terrain splats, water, object shadows, sky, lens flare, snow and SpeedTree.

Godot materials should encode the observed contract explicitly: alpha mode,
depth draw/test, culling, diffuse/opacity map role, vertex color, emission,
specular approximation, billboard axis and texture animation. Keep original UI
RGBA lossless, but select modern compression per 3D texture with semantic and
visual checks. Shared material/mesh/rig caches, instancing, spatial culling,
distance animation updates, measured LOD and effect budgets are desirable only
when fixed-camera comparisons stay within declared error bounds.

MSE/MDE/MSF conversion needs its own normalized intermediate form. Unsupported
nodes fail a selected production profile or appear as named omissions in an
experimental profile. Each effect preview should expose lifetime, live particle
count, draw calls, overdraw proxy, missing dependency, bone/target attachment and
event origin. Stress scenarios must retain nearby combat cues before ambient or
distant effects.

Miles is replaced with Godot audio, not emulated. Preserve MSS event timestamps,
2D/3D intent, attenuation and overlap; preserve map BGM/ambient transitions and
volume control. Automated capture should compare event deltas and measured mix
levels. Browser tests must cover first-user-gesture start, tab suspension/resume
and device/context recovery.

## Maps and content catalogs

There are 92 paths ending in `/setting.txt`; the evidence JSON enumerates all of
them. They include empire towns, desert/snow/flame/trent maps, guild maps,
wedding/duel/empire-war/event maps, monkey/spider/devil/Skipia dungeons and later
patch maps. Duplicate logical names exist across base, season and patch packs.
This is a source-map candidate list, not 92 unique or complete playable maps.

The map compiler must treat `bin/pack/Index` and virtual path normalization as
part of identity. For an explicit content profile, resolve settings, texture
sets, height/tile/splat, attributes, water, shadows/minimap, area placements,
property CRCs, GR2/material dependencies, model collision, SPT foliage, MSE
effects, portals/dungeon blocks, environment and audio. Emit client visuals,
authoritative server geometry/navigation and map/minimap transforms from one
versioned graph.

Acceptance is broader than loading all sections: terrain seams, texture layers,
water edges, landmarks, building transforms, collision clearance, bridge and
underpass choice, portals, spawn safety, camera occlusion, foliage/weather,
ambient/BGM, minimap coordinates, content streaming and isolated package
dependencies. Current Yongan evidence is a strong fixture, but unsupported 368
trees and six effects alone prevent complete visual parity there.

Item, mob, skill, NPC and atlas catalogs must be schema-identified before use.
Readers validate bounds, finite numbers, enums, references and text encoding,
preserve unknown fields in reports and never replace malformed required values
with zero. Compile separate client presentation and server authority artifacts
that share stable IDs and definition hashes. Item/mob/skill presence does not
establish drops, shops, spawns, AI, formula, progression or quest behavior;
those require server/data audits and end-to-end scenarios.

## UI fidelity, localization, fonts and Web

The original UI is a controller/layout/art system. `ui.py` wraps C++ windows,
text, edit lines, images, animated images, buttons, slots, gauges, boards,
scrollbars, lists and script loading. Layout dictionaries specify native pixel
rectangles and asset paths; locale packs override layouts and images. SUB files
crop shared atlases. Some centers/borders are drawn colors, so a bitmap-only
inventory will miss visible elements.

Build a safe Python-layout parser for the data subset actually used. It should
resolve constants and literal dictionaries without imports, calls or arbitrary
execution, normalize widget trees and anchors, retain source path/hash and emit
Godot scene/resources. Unsupported syntax enters a review queue. Shared widgets
should preserve the classic 32/16-pixel board systems, slot behavior, button
states, gauge frames, clipping, z-order, mouse pick rules, tooltip delay and
focus ownership. Modern resolution support should start from a native-pixel
reference canvas, use explicit anchors/safe regions and avoid fractional scaling
that blurs the art.

The tree contains 15 `locale_*` pack roots, each with roughly 229–234 blobs. This
is pack presence, not translation completeness. Compile keys, placeholders,
layout overrides, images, code pages and missing/extra keys into locale reports.
Exercise long strings, plural/number formatting, clipping/wrapping, input methods
and locale switching. Player text remains sanitized independently of trusted
locale resources.

The English locale names Tahoma at 12, 14 and 9, while original text rendering
uses GDI. The archive contains no `.ttf`, `.otf` or `.fnt` bytes. Do not package
a cached Microsoft font or claim parity from equal size numbers. Select a font
with explicit redistribution rights, then compare advance widths, baseline,
line height, antialiasing, clipping, outlined/shadowed text and dense labels
against lawful original-client captures. Until then, font fidelity stays open.

Web adds constraints absent from the original client: download size, WebGL 2,
single-threaded baseline, memory/quota, cache eviction, context loss, tab
suspension, input capture and audio gesture rules. Keep a small core pack and
stream versioned nearby content with retry/cancellation and bounded caches.
Measure initial bytes, first interactive/login/world times, memory peak and
section churn on named hardware/browser/network conditions. Every UI interaction
suite should run against native and browser exports; editor success alone is not
release evidence.

## Automation and development/admin support

The repeated work belongs in one content compiler and evidence system, described
in [development and administration](development-and-admin.md). Its minimum
commands should inventory/explain, dry-run/import, build, validate/diff,
preview/scenario, coverage/report and publish an already validated manifest.
Names in that document are proposed interfaces, not current commands.

For client work, the first-class tools are:

- a content graph browser with forward/reverse dependencies, precedence and
  source/normalized/output hashes;
- animation/equipment inspector with clip scrub/blend, rigs, bones, hit windows,
  attachments, trails, effects and deterministic capture;
- map inspector with visual/authoritative collision, portals, spawn/nav layers,
  missing scenery and fixed camera bookmarks;
- UI reference gallery that renders every stage/window/dialog/state at standard
  resolutions/locales and stores geometry, focus and image comparisons;
- scenario recorder for two or more normal authenticated clients, reducer
  rejection, disconnect/reconnect and network impairment;
- performance lab for dense towns/combat, content streaming and browser budgets;
  and
- release audit that proves exact client/server content compatibility and excludes
  MCP, script evaluation, tokens, logs and source archives.

Developer views may inspect state and emit ordinary validated actions. Privileged
repair, item, currency, moderation, event or release operations belong to a
separate server-authorized operator surface with preview, role checks and audit
records. MCP and importers remain local build tools and must never be player
dependencies.

## Completion criteria and gaps

A client feature is complete only when all applicable evidence exists:

1. source behavior and data dependencies are catalogued at immutable revisions;
2. safe readers normalize required formats and report every unsupported field or
   missing/ambiguous dependency;
3. server definitions and reducers own all consequential state and reject invalid
   intents;
4. Godot renders confirmed state using generated resources with classic layout,
   motion, VFX and SFX reference checks;
5. two independent exported clients pass success, rejection, disconnect and
   reconnect paths on one real server; and
6. the release manifest proves exact protocol/content compatibility and contains
   no development-only capability or source archive.

The largest client-side unknowns are full GR2 revision/rig coverage, 2,884 MSM
records, 6,393 MSA records and their 3,637 MSS companions, the complete
MSE/MDE/MSF graph, SpeedTree, indoor/portal/multilevel map behavior, pack override
semantics across every selected profile, safe parsing of all Python layouts and
catalog schemas, lawful font parity, and a comprehensive original-client capture
corpus. The machine inventory preserves those omissions so later milestones
cannot turn file presence into an unsupported completeness claim.

[primary]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7
[primary-readme]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/README.md
[solution]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/Metin2Client.sln
[ui-project]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/UserInterface.vcxproj
[vcpkg]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/vcpkg.json
[client-startup]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/UserInterface.cpp
[locale-profile]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/Locale.h
[app-module]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/PythonApplicationModule.cpp
[phase-select]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/PythonNetworkStreamPhaseSelect.cpp
[mouse-input]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/PythonPlayerInputMouse.cpp
[keyboard-input]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/PythonPlayerInputKeyboard.cpp
[phase-actor]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/PythonNetworkStreamPhaseGameActor.cpp
[phase-game]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/PythonNetworkStreamPhaseGame.cpp
[phase-items]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/PythonNetworkStreamPhaseGameItem.cpp
[taskbar-layout]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/bin/pack/locale_en/locale/en/ui/taskbar.py
[python-chat]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/PythonChat.cpp
[minimap-cpp]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/UserInterface/PythonMiniMap.cpp
[motion-header]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/GameLib/RaceMotionData.h
[browser]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/CWebBrowser/CWebBrowser.c
[gr2-load]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/EterGrnLib/Thing.cpp
[race-load]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/GameLib/RaceDataFile.cpp
[motion-load]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/GameLib/RaceMotionData.cpp
[effect-load]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/EffectLib/EffectData.cpp
[fly-load]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/GameLib/FlyingData.cpp
[sub-load]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/EterLib/GrpSubImage.cpp
[sound-manager]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/MilesLib/SoundManager.cpp
[material]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/EterGrnLib/Material.cpp
[attach]: https://git.old-metin2.com/metin2/client/src/commit/bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7/src/GameLib/ActorInstanceAttach.cpp
[supplementary]: https://github.com/NakiuS/Metin2Client/tree/40e2d9fef3bed9fa56a113001ae678efb72e06d3
