# Classic characters and the import workflow

The character slice supports Warrior, Ninja, Sura and Shaman, each with male and
female appearances. Creation sends `(slot, name, character_class, sex)` to the
server. The class and sex are immutable server-owned properties of that character;
the public appearance projection drives the model shown by every client.

## Build selected original assets

Activate the development Python environment and install the baseline
`p0-warrior-dog` content first. Use a new output directory for every build:

```sh
. .local/venv-dev/bin/activate
make characters-build BLENDER=/path/to/blender \
  CHARACTER_OUTPUT=.local/characters/revision-1
# Subsequent build, using cached pinned sources and preserving the installation:
make characters-build BLENDER=/path/to/blender \
  CHARACTER_OUTPUT=.local/characters/revision-2 CHARACTER_FLAGS='--offline --replace'
python3 tools/import_metin_ui.py --offline
```

The UI command needs one online run when the selected portraits/title art have
not been fetched yet; omit `--offline` for that run. The same applies to character
inputs. No archive Python or original game executable is executed.

`content/profiles/classic-characters.json` selects the eight original race scripts
from the pinned client. The importer discovers the body, default hair, material
textures, attachment bones, weighted motions and fallback registrations. Class
starting points come from the pinned server's `JobInitialPoints` data. Background
Blender converts selected GR2 inputs into GLB animations, skinning and meshes;
the runtime package contains converted GLB/PNG assets and a public JSON catalog.

The output includes normalized definitions, source hashes, a Blender report,
conversion receipt and the `runtime/` package. With `--replace`, the old installed
package is retained as `runtime-previous-install/` beside the new runtime package.
Validation and staging happen before replacement. Never edit generated files to
fix an import: change the profile, parser or converter, then make a new build.

To inspect definitions before running Blender:

```sh
python3 tools/import_character_content.py --offline \
  --output .local/characters/definition-review
# Package an already completed conversion without repeating Blender:
python3 tools/build_character_catalog.py \
  --source .local/characters/revision-1 \
  --output .local/characters/package-review
```

The conversion checks the rest transforms of **actually weighted** hair bones
against the body in model space. Original hair can use several head, neck or
ponytail bones; an unused helper bone does not invalidate a compatible part.
Missing weighted bones, incompatible transforms, bad weights, missing motions
and changed artifacts fail the build. Animation deformation and Godot appearance
still need rendered qualification after a converter change.

## Shared gameplay definitions

The server compiles the installed character catalog and publishes its exact hash
in `world_info.character_catalog_hash`. The client requires a matching catalog
before entering the world. Regenerate bindings and publish a fresh database when
the application protocol changes; protocol 14 adds class creation arguments,
the class on private progression, and the catalog hash. Preserve existing databases.

| Class ID | Class | STR / VIT / DEX / INT | Initial HP / SP |
| --- | --- | --- | --- |
| 0 | Warrior | 6 / 4 / 3 / 3 | 760 / 260 |
| 1 | Ninja | 4 / 3 / 6 / 3 | 770 / 260 |
| 2 | Sura | 5 / 3 / 3 / 5 | 770 / 300 |
| 3 | Shaman | 3 / 4 / 3 / 6 | 860 / 320 |

Sex 0 means male and sex 1 female. These values differ from the original race
numbers; the catalog records that mapping explicitly. Class-specific HP/SP
growth and physical attack stat contributions share the progression/combat
mechanics. An accepted attack captures its damage stats, including its class
contribution, so later state changes cannot rewrite a queued hit.

All eight appearances have general movement and basic unarmed attacks. Warrior,
Ninja and Sura receive Sword+0 and use their original four-step common sword chain
in both appearances. Every class receives five small red potions. Shaman currently
starts unarmed; its fan item and fan combat are pending. Holding Space sends
ordinary attack intents at the current action's source input windows. The server
owns every transition, hit and equipment check. Releasing Space, focusing chat or
losing window focus stops new held-key intents; an already accepted link may finish.

Creation shows all four classes in the original circular arrangement, with the
selected class in front. Both creation and roster previews use each model's
original `intro.wait` animation. The separate character package includes the male
Warrior's intro clips; world gameplay retains the accepted baseline Warrior model.

The original loader ignores legacy `ComboInputData.LinkTime`; some source files
contain an uninitialized value there. The class adapter explicitly omits that
unused field. Finite Sura combo input times extending beyond the clip remain in
source metadata; the playable common chain expires at clip end. Terminal input
metadata never enables a fifth hit. Warrior/Ninja finishers use their original
area-event timing and the shared validated area policy; the source's disabled
ordinary 0..0 hit window cannot produce an extra hit. Sura's fourth hit currently
uses ordinary damage; its original force-15 knockback remains pending. Advanced
combo registrations are imported as data but are not enabled as gameplay.

Skills, Ninja daggers/bows, Sura abilities, Shaman fans/bells, additional armor,
hair styles and additional classes remain separate content/gameplay slices.
The current catalog deliberately validates four classic classes and eight
appearances. A future class extends those validators and the supported mechanics
alongside its data; it does not need a separate account or networking system.
Quests remain deferred.

## Qualification

```sh
python3 tools/test_classic_ui.py --suite intro --native --godot /path/to/godot \
  --output .local/characters/intro-qa
make test-classes GODOT=/path/to/godot \
  SERVER_URL=http://127.0.0.1:8186 GAME_SERVER_URL=http://127.0.0.1:13223 \
  DB=mt2-p2-classes-your-revision CHARACTER_OUTPUT=.local/characters/live-qa
```

The live test uses two ordinary authenticated accounts, creates all eight
appearances, checks rejected IDs and private subscriptions, moves both players,
attacks actual mobs, and reconnects without duplicating starter items. It requires
a disposable `mt2-p2-` database with the normal six-dog Yongan population.

For actual Web/Linux exports, use the existing export commands with the intended
endpoint/database. Package audits load every added character model and verify
textures, skinning, attachment bones and registered animation clips. Then run
`tools/test_browser_accounts.py --classes` with matching `--url`, `--database`,
`--native` and `--output` arguments. This uses visible browser controls for all
eight previews and plays female Ninja and male Shaman with an independent native
peer. Its probe is confined to explicitly instrumented development exports.

See the [status ledger](rebuild/implementation-status.md) for actual evidence,
deployment differences and remaining work. Asset and tooling terms are recorded
in [third-party.md](third-party.md).
