# Client distribution and deployment

The Web client runs in a browser; desktop exports bundle their own Godot runtime.
Players do not install Blender, Rust, Python, Node or the SDK. The current
development endpoint is [https://kcanakdag.com:8443](https://kcanakdag.com:8443/),
database `mt2-yongan-v2`, on `159.195.213.9`. It may restart during updates.
Current release `20260906T154235134255Z` includes the fixed test probe with the
user's explicit authorization. Its 45 public Chrome/Linux checks cover current
map/chat panels, inventory and multiplayer. Normal export commands below omit
that probe.

Browser/Linux multiplayer checks passed on the training ground and Yongan.
The corrected Yongan browser run also verifies terrain appearance, keyboard
combat, loot and both respawns, while scenery loads nearby during play.
Refresh an older tab after the content update. See [verification status](#verification-status).

## Export Web and Linux

Prepare the warrior, imported Yongan and collision bake using the root README.
Install matching Godot **4.7.2** export templates: `web_nothreads_release.zip`
for Web, `linux_release.x86_64` for Linux. Standard Godot/GDScript is used
throughout. Engine and template versions must match.

```sh
make export-web SERVER_URL=https://kcanakdag.com:8443 DB=mt2-yongan-v2
make export-linux SERVER_URL=https://kcanakdag.com:8443 DB=mt2-yongan-v2
```

The underlying command accepts `--godot`, `--templates`, `--server`,
`--database`, `--target web|linux`, and `--include-map`:

```sh
python3 tools/export_playable.py --target web --include-map \
  --server https://kcanakdag.com:8443 --database mt2-yongan-v2
```

Make includes Yongan by default. Use `INCLUDE_MAP=` only when intentionally
exporting for the training variant. Bare `export_playable.py` does not include
the map unless `--include-map` is supplied.

| Output | Contents and use |
| --- | --- |
| `dist/web/` | HTML, JavaScript, WASM, core PCK, optional `world/` packs, notices and build manifest; serve as a directory |
| `dist/linux/` | `MT2Spacetime.x86_64`, PCK, adjacent config, notices and manifest; keep together |
| `.local/export-web/`, `.local/export-linux/` | Isolated staging/import/export/audit logs |
| `dist/web-test/`, `dist/linux-test/` | Only produced with the explicit `--test-probe` option |

The helper copies the project into staging and strips MCP editor/runtime
bridges and tests. It preserves the runtime SDK, audits the actual PCK for
forbidden developer resources and required warrior meshes/bones/animations,
and packages runtime notices. A Yongan Web export also audits all 20 section
packs in fresh Godot processes, checking isolated dependencies and exact numeric
terrain texels. Its complete manifest covers the recursively published files,
including compressed payloads and section packs. It does not edit the open project.
Use the helper rather than assuming the editor's direct Export button applies
these project-specific exclusions.

Linux settings can be overridden on launch:

```sh
./dist/linux/MT2Spacetime.x86_64 -- \
  --server https://kcanakdag.com:8443 --database mt2-yongan-v2 \
  --profile alice --name Alice --auto-connect
```

Desktop settings load from built-in defaults, packaged config, saved profile,
then command-line overrides. Profiles separate local identities. Browser builds
use their page origin for the server and the packaged database, avoiding stale
saved endpoints after deployment. Browser guest identity storage belongs to
that origin; clearing site data can create a new identity on the next join.

## Loading assets during play

Web uses the Compatibility renderer, WebGL 2 and a single-threaded template.
The player first downloads the engine, scripts, warrior and core UI. Yongan's
export is split into one shared-resource pack and 20 section packs, with
SHA-256 filenames and a small `world/manifest.json`. The starting section loads
before entering the world; nearby sections are requested during movement.

The client verifies downloaded hashes and stores packs under
`user://world-cache`. The server's content hash must match the manifest.
Native builds check their bundled collision metadata too. A content update
requires a browser refresh or desktop restart; the loader refuses to combine a
new manifest with already mounted packs. A map change received during loading,
joining or play ends that connection with an update notice.
Distant scene instances are removed as the player moves, while downloaded packs
may remain cached. This does not eliminate all startup time, memory growth or
loading hitches. Background section loading and corrected terrain appearance
are verified on the tested workstation; broader hardware performance is unmeasured.
Initial shared textures/models are also a download cost.

Serve the exported directory over HTTP(S), not `file://`. Production uses
HTTPS and secure WebSockets at the same origin. This single-threaded preset
does not enable PWA installation or require the threaded template's cross-origin
isolation configuration. See [Godot Web export](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_web.html).
The current rendering/compression choices have been exercised in Chrome on
Linux; mobile Safari, mobile GPUs and other browsers are not covered.

Numeric tile/attribute textures must remain lossless, without mipmaps or GPU
block compression. Color textures may use the platform's imported compression.
The resource audit compares all 40 numeric textures against their source PNGs;
it catches wrong terrain IDs even when dimensions and resource loading look valid.

## Docker deployment

`deploy/Dockerfile` pins SpacetimeDB **2.8.3** by image digest and copies the
already-built module. It runs the service as the image's `spacetime` user.
`deploy/compose.yaml` pins Nginx **1.28.0 Alpine** by digest and gives the two
services separate CPU/memory/log limits.

| Resource | Scope |
| --- | --- |
| Remote directory | `/opt/metin2-godotime` |
| Compose project | `metin2-godotime` |
| Public game endpoint | TCP `8443`, HTTPS and WSS |
| Administrative database endpoint | `127.0.0.1:13210` on the VPS only |
| Database persistence | Compose named volume `world` |
| Static releases | `web/releases/<UTC timestamp>`, selected by `web/current` |
| Staged candidates | `incoming/<UTC timestamp>/`, isolated from active files |
| Database/runtime backups | `backups/<UTC timestamp>/world` and `runtime`, private directories |
| Deployment status | `deployment-status.json` and the candidate's `status.json` |

The deployment host must already have Docker with Compose, SSH access, Bash,
`curl`, `ss`, `timeout`, `flock`, `openssl`, `ufw`, and a valid certificate under
`/etc/letsencrypt/live/<certificate name>/`. The configured deployment reuses
the existing `kcanakdag.com` certificate read-only. The script does not install
Docker or provision/renew certificates. Existing HTTP/HTTPS services on ports
80/443 and other application containers are outside this Compose project.

```sh
make server-build
make export-web SERVER_URL=https://kcanakdag.com:8443 DB=mt2-yongan-v2
make deploy
```

Equivalent explicit deployment:

```sh
python3 tools/deploy.py --host root@159.195.213.9 \
  --public-name kcanakdag.com --certificate kcanakdag.com \
  --port 8443 --database mt2-yongan-v2 --web-dir dist/web
```

Before SSH, the script verifies every exported file against the build manifest,
including streamed packs, compressed files and the actual-PCK audit. Missing,
modified, extra, hidden or symbolic-link files fail validation. It uploads only
the game's context, module and Web files into a fresh candidate directory.

`deploy/apply.sh` takes the game's deployment lock, checks certificate hostname
and expiry, refuses unrelated port owners, validates Compose/Nginx, and builds
the candidate database image before downtime. It then stops only the game
database, takes a cold copy of its volume contents and prior runtime config,
starts the candidate, and checks that its identity-issuer public-key hash is
unchanged. Publication uses persistent `/data/publisher-v2.toml` and
`--delete-data=never`; destructive schema migration fails instead of wiping data.

After publication it atomically switches the Web symlink, recreates only the
game proxy, validates Nginx and verifies the HTTPS-served manifest hash. It
installs the game's certificate reload hook and opens the game port in UFW.
Game sessions can disconnect during the restart; players reconnect afterward.
No `docker compose down -v`, host-wide prune, unrelated-container restart or
existing database reset is part of this workflow.

The HTTPS proxy serves assets and permits fresh identity creation and the
configured database's game subscription WebSocket. Other `/v1/` routes are
denied, keeping publication, administration and direct HTTP SQL unavailable
through the game endpoint. Game actions still require server-side validation.
Browser WebSocket tokens appear in the handshake query, so access logging is
disabled and proxy error logging is restricted to avoid recording request URLs.

## Operation and recovery

Inspect only the game's services:

```sh
ssh root@159.195.213.9 'cd /opt/metin2-godotime && docker compose ps'
curl --fail https://kcanakdag.com:8443/health
```

A healthy route is a proxy check, not evidence of live gameplay or subscriptions.
After updates, use a browser and another independent client to verify movement
and disconnect behavior. The host's existing certificate process handles renewal.
The game adds `/etc/letsencrypt/renewal-hooks/deploy/metin2-godotime`, which
reloads only this Compose project's Nginx when its configured certificate renews.
An unrelated script already occupying that hook path is not overwritten.

Deployment status records the active phase or `failed:<phase>`. A failure before
publication restores the previous runtime/config where available and resumes
the stopped game database, without restoring or deleting its data. A publication
failure leaves the database running and the old Web release in place. A later
Web-activation failure can restore the previous Web symlink/proxy; it does not
roll the database schema back. Candidate files and private backups remain for
deliberate recovery.

The script has no automatic data restore, retention policy, off-host replication
or disaster-recovery guarantee. A previous client must still match the current
protocol/content. Preserve current data before a manual database recovery, and
use a tested migration strategy if publication changed schema. Deployment
failure handling is separate from a complete backup restore drill.

## Browser test builds

`--test-probe` adds a local browser/desktop test interface to inspect rendered
entities and send normal gameplay actions. It provides no privileged server
write path, but belongs only in deliberate test builds.

```sh
make browser-setup
make export-web TEST_PROBE=--test-probe DB=mt2-yongan-test
make export-linux TEST_PROBE=--test-probe DB=mt2-yongan-test
make deploy DB=mt2-yongan-test WEB_DIR=dist/web-test DEPLOY_FLAGS=--allow-test-build
make test-browser PUBLIC_URL=https://kcanakdag.com:8443 DB=mt2-yongan-test
```

Add `BROWSER_FLAGS=--hardware` to use a visible Chrome window and the system GPU.
The default software renderer is useful for connectivity checks but can run
Yongan too slowly for timing-sensitive combat verification.

The deployment command refuses test instrumentation without
`--allow-test-build`. This example temporarily switches the development game
endpoint to the test database; do not run it expecting existing sessions to
continue. Build and deploy a normal Web export for the intended game database
after testing. A disposable endpoint/world is preferable when other people
need an uninterrupted session.

The test runner uses Playwright/Chrome and a rendered exported Linux executable,
with independent identities, real subscriptions and scene-avatar observations.
It saves a report and screenshots in `.local/browser-proof/<timestamp>/`.
Failures also write partial reports. See [development](development.md#browser-integration-checks).

## Windows and temporary local hosting

`make export-windows SERVER_URL=<reachable address> WINDOWS_DB=mt2-training-v2`
retains the training-only `dist/windows-x86_64.zip` workflow. It omits Yongan
assets, so its database must run the training server variant. `WINDOWS_DB` is
separate from the Yongan `DB` Make default. Keep the EXE, PCK, configuration and
notices together. A graphical Windows-under-Wine training-ground test passed on
this Linux workstation, with two independent players and disconnect presence
checks. It does not verify physical Windows hardware or the current Yongan
export. See `.local/windows-playtest/` for that historical evidence.

`make share-setup`, `make share-start DB=mt2-training-v2`, and `make export-shared`
remain an optional temporary Windows tunnel for the local training server.
Publish it using `make server-publish SERVER_FEATURES= DB=mt2-training-v2` first.
Its hostname expires when the tunnel stops; its old Windows public gameplay test
remains unverified.
The Docker deployment is the current stable-address development path.
See [temporary playtesting](playtesting.md).

## Verification status

Evidence recorded on 2026-09-06:

The evidence includes several completed slices. The earlier normal release
`20260906T141816112109Z` passed direct browser UI/keyboard and Linux checks
without test instrumentation. The current authorized development release
`20260906T154235134255Z` includes the original HUD, inventory and map/chat panels,
with exact UI pixel audits and separate public versus loopback chat checks.

| Path | Evidence | Scope and limits |
| --- | --- | --- |
| Browser + exported Linux on the training ground | `.local/browser-proof/20260906-143520/report.json`, 14 checks and screenshots | Real HTTPS endpoint, independent identities, mutual rendered visibility/movement, rejection, disconnect/reconnect, browser refresh |
| Baseline Yongan Rust rules | 16 passing tests with `--features yongan` | Baked layout, spawn/height/bounds, circular clearance, bridge seam and combat reach/blocking |
| Yongan live SDK multiplayer | `.local/yongan-network-final.json`, 22 checks | Two SDK identities, mutual replicated state, both movement directions, rejection, duplicate session and reconnect |
| Yongan live SDK combat | `.local/yongan-combat-final.json`, 19 checks | Damage, death/respawn, reservation/duplicate pickup rules and preserved gold |
| Streamed Yongan browser + exported Linux | `.local/browser-proof/20260906-161458/report.json`, 26 checks | Mutual rendered movement, keyboard controls, background sections, rejection, reconnect/refresh, forced database-container replacement, attacks/damage/loot and both death/respawn paths |
| Yongan appearance | `browser-final.png`, `browser-combat.png` and `desktop.png` beside the final browser report; `.local/yongan-native-public.png` | Corrected terrain/textures, textured warrior, buildings and combat observed |
| Isolated streamed resources | `.local/export-web/world-pack-audit.json`, 20 sections and 40 numeric textures | Fresh process per shared/section pair; dependency loading and exact tile/attribute bytes |
| Baseline development checks | `make check`, 16 Rust and 66 Python tool tests, all linters and actual Godot parser/runtime | Owned source, server, conversion/deployment tools and real engine checks |
| Earlier normal release exports | `dist/web/build-manifest.json`, `dist/linux/build-manifest.json` | Actual PCK audits of 229 core Web files and 1,032 Linux files; both `test_probe=false` |
| Earlier normal public browser release | `.local/release-browser/evidence.json`, `observations.json` and screenshots | Actual connection UI, correct terrain textures, keyboard movement reflected in server diagnostics, no engine errors or test hooks |
| Earlier matching Linux release | `.local/release-native/report.json`, `client.png` | Export-template build, connected to the public database, both release players visible, no errors |
| Deployment/export failure tests | 14 tests in `tests/test_deploy_export.py` | Artifact inventory and apply-script failure sequencing with temporary command stand-ins; not a live data restore drill |
| Current public map/chat/inventory build | `.local/browser-proof/20260906-174806/report.json`, 45 checks | Independent Chrome/Linux clients, final panel drag/resize geometry, inventory, rejection, reconnect/refresh and no engine errors; no public chat sent |
| Chat-send/WASD regression | `.local/browser-proof/20260906-174144/report.json`, 45 loopback checks | Actual chat delivery to the other subscription and movement after send, Escape, world click and history submission |
| Current native panels | `.local/classic-panels-ui/`, `.local/classic-map/`, `.local/classic-chat-final/` | 15 UI, 17 map and 22 chat checks with screenshots |
| Current public native editor | `.local/classic-chat-native-editor/centered-chat.png` | Connected project, bottom-center chat, Escape leaves no focus/visible entry |
| Current test export/deployment | Web/Linux PCK audits: 582/1,385 files and 160 exact UI/map images; `.local/classic-panels-served-manifest.json` | Served/exported manifests match; fixed test probe explicitly authorized; no MCP/evaluator/tokens/source archives |
| Current tool checks | 70 passing tool tests and all lint groups | Source/tool validation, separate from rendered client evidence |
| Windows graphics | Historical local Wine report | No native Windows hardware or current Yongan Windows run |

The earlier corrected-Yongan test used Chrome with the workstation's AMD 860M GPU via
ANGLE. Engine readiness took 6.66 seconds and world readiness 12.97 seconds total
in that run. Sampled browser rates after loading ranged from 32 to 63 FPS while
a software-rendered Linux observer also ran. Earlier SwiftShader runs were much
slower and did not provide reliable combat timing. These are measured paths on
one workstation, not universal download times or frame-rate promises.

In the separate normal-release UI test, holding W for 1.2 seconds changed the
server position from approximately `(662.4, 198.625, 575.0)` to
`(662.4, 198.625, 569.2505)`; the rendered diagnostics showed 61–62 FPS.
`window.mt2Command` and `window.mt2Snapshot` were both absent. The Linux release
joined with an independent identity and rendered the browser and desktop
characters. Existing VPS application endpoints also returned HTTP 200 after
the final deployment.

The latest public panel run reached the world in 12.52 seconds and recorded
42 FPS in its final sample. The separate loopback chat run reached the world in
8.82 seconds with a final 21 FPS sample. These describe those particular runs;
they are not comparable load benchmarks. The loopback-only `--chat-focus` option
keeps synthetic chat away from public sessions.

The prototype has no large-player load benchmark, complete Metin2 visuals/content,
account system or full database-restore/disaster-recovery verification.
