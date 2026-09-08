# Client distribution and deployment

The Web client runs in a browser; desktop exports bundle their own Godot runtime.
Players do not install Blender, Rust, Python, Node or the SDK. The current
development endpoint is [https://kcanakdag.com:8443](https://kcanakdag.com:8443/),
on `159.195.213.9`. It may restart during updates.

The current release is `20260908T220207351930Z`, fixing world play to use the
expanded male Warrior character package, including imported skill motions.
It preserves protocol 26, database `mt2-public-skills-v26-20260908`, current
characters, auth accounts and issuer keys. The server module is unchanged, SHA-256
`750f0c44bb4784dcc6d53eb35387ff07b8efe0932fc0907bc5bd12676f00279e`.
Web/Linux package audits and the served-manifest check pass. Public Chrome/Linux
QA passes 76 checks, including matching 2,859-mob/44-species subscriptions,
movement, character switching, saved position, reconnect, reload and logout/login.
Browser engine errors are empty. Artifacts and evidence are in
`.local/public-skill-actors-r1/`.
The local focused two-Chrome skill replay passed 32 checks with fresh replicated
casts and no engine errors; this is separate from public casting qualification.

The preceding release is `20260908T212416762304Z`, using protocol 26 and database
`mt2-public-skills-v26-20260908`. It includes the four selected Warrior skills and
original Yongan population. Both public Web/Linux exports pass package audits;
local matching exports passed 76 hardware-rendered Chrome/Linux account/world
checks. The deployment verified its served manifest, retained auth accounts and
issuer keys, and used `delete_data=never`. Previous world databases remain intact;
accounts have a separate character roster in this new database. Public hardware-rendered Chrome/Linux QA passes 76 checks, including matching
2859-mob/44-species subscriptions, mutual rendering, movement, skill-panel
input, character switching, reconnect, reload and logout/login. Browser engine
errors are empty. The public skill-panel capture was reviewed. Frozen artifacts, module hash and logs are in
`.local/public-skills-v26-r1/`. The module uses the public issuer, guests disabled
and no QA bootstrap privileges. New-skill browser casting remains unqualified.

The preceding release is `20260908T181619790682Z`, source `e0e2b22`. It adds
streamed-map UID restoration and preserves the protocol-24 database, accounts,
characters and server module. Its web export and all 20 isolated map-section audits
passed with no UID warnings. Evidence is in `.local/public-world-uids-r1/`;
the targeted public browser/native field replay passed 43 checks. Ordinary browser
reentry and WASD reached the native peer, with zero warning or error messages.
Browser field and ordinary-world captures were reviewed. Short browser cadence
measured 38.5 frames/sec with diagnostics and 60.1 without; this is not engine FPS
or evidence of a performance gain from UID restoration. The unchanged native
peer used the previous export. Full combat/lifecycle QA was not repeated.

The preceding diagnostics release is `20260908T180128789164Z`, source `4102a94`, on the same
protocol-24 database `mt2-public-population-v24-20260908`. The opt-in diagnostics
update preserved the module, accounts and characters. Frozen exports, deployment
log, served manifest and hashed acceptance are in `.local/public-probe-opt-in-r1/`.
Public activation QA passed both startup modes and reloads with no console errors.
The focused `field-qa/report.json` passed 52 checks, including all eight previews,
replicated field mobs and ordinary browser reentry/WASD observed by a native peer.
Browser errors were empty; 876 map UID warning/location messages remain. Short
browser cadence samples were 37.2 frames/sec instrumented and 58.9 ordinary;
these are not engine FPS or a controlled benchmark. This run does not repeat the
previous release's full 114-check combat/lifecycle qualification below.

The preceding population rollout deployed protocol 24, database
`mt2-public-population-v24-20260908`, release `20260908T170855056942Z`.
The selected original population package contains 945 regeneration entries and
44 possible species, with converted mob models, current held-attack handling and
original coin/potion ground models plus separated labels. Auth accounts, signing
keys and previous world databases were preserved (`delete_data=never`). Existing
accounts have a separate character roster in this new world. Evidence and frozen
module/exports are in `.local/public-population-r1/`.

Deployment/package audits and all 114 public browser/Linux checks passed in
`browser-qa-r3/report.json`: independent accounts, replicated movement, original
field combat/death, matching ground models, full return route, character switching,
disconnect/reconnect, reload and logout/login. Browser errors and native engine/
script errors are empty. Both loot captures were reviewed. Chrome's instrumented
field median was 26.5 FPS; this is not a release-performance qualification.

The initial two-client run reached the world with identical 2,812-mob,
42-species subscriptions, then stopped at an incorrect all-catalog-species census
assertion. Original random group selection does not guarantee every species at
once; the corrected test retains peer equality and valid unique registered mobs
while reporting unobserved variants. No runtime or database was modified to force
the census. A second run demonstrated that the fixed local hunting route ends
beyond the public group's camera/combat range. The successful third run used the
offline collision-checked route to the actual subscribed public group. Both failed
reports are retained. The earlier local combat-return stall was not reproduced
in this public run; its root cause and broader performance remain unresolved.

The preceding public development endpoint used protocol 19,
database `mt2-public-progress-v19-20260908`, release `20260908T121524155504Z`.
This supersedes the older public protocol-4 deployment. The user explicitly
requested this update. Existing auth accounts, issuer keys and prior databases
were retained; the new world has a separate character roster.
Artifacts and hashed acceptance are under `.local/public-progress-r1`: frozen
`module.wasm`, matched `web/` and `linux/` exports, export audits, `deploy.log`
and `acceptance.json`. The module was built with the public auth issuer and guests
disabled. Both exports use the explicitly authorized development test probe;
editor MCP bridges, private state and source archives remain excluded.
`browser-qa/report.json` passes 114 actual public Chrome/Linux checks using two
independent accounts: registration/login, private roster, replicated movement,
21 entry NPCs and City Guard, independent dialogue, dummy selection/damage,
skill-panel input, character switching, disconnect/reentry, reload and logout.
Browser engine errors are empty. The browser world and guard-dialogue captures
were reviewed. Chrome MCP new_page timed out; the separate automated Chrome
runner completed. Windows execution and full original-client parity are not
qualified. All 44 candidate mobs and the remaining abilities are still not live.
The localhost area endpoint remains separate and was not replaced by this rollout.

The preceding guest release `20260906T154235134255Z` passed 45 public Chrome/Linux
checks for map/chat panels, inventory and multiplayer. Earlier Yongan gameplay,
terrain and normal-release checks remain historical evidence; they do not prove
the new account flow. See the evidence table below.

## Select a frozen deployment module

`tools/deploy.py --module <frozen-release.wasm>` selects a specific server artifact
and prints its SHA-256 before remote operations. Without this option, the existing
`server/target/wasm32-unknown-unknown/release/mt2_server.wasm` default remains.
Prefer an explicit frozen module when local QA builds use a different issuer,
population or bootstrap permissions. Selecting a file does not verify those
policies: build it for the intended public issuer with guests disabled and no QA
bootstrap identities, and pair it with matching exported content/protocol.
The command archives that file directly; it does not replace the local build.

## Export Web and Linux

Prepare the warrior, imported Yongan and collision bake using the root README.
Install matching Godot **4.7.2** export templates: `web_nothreads_release.zip`
for Web, `linux_release.x86_64` for Linux. Standard Godot/GDScript is used
throughout. Engine and template versions must match.

```sh
make export-web SERVER_URL=https://kcanakdag.com:8443 DB=mt2-p1-v4
make export-linux SERVER_URL=https://kcanakdag.com:8443 DB=mt2-p1-v4
```

The underlying command accepts `--godot`, `--templates`, `--server`,
`--database`, `--target web|linux`, and `--include-map`:

```sh
python3 tools/export_playable.py --target web --include-map \
  --server https://kcanakdag.com:8443 --database mt2-p1-v4
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
  --server https://kcanakdag.com:8443 --database mt2-p1-v4 \
  --profile alice
```

Desktop settings load from built-in defaults, packaged config, saved profile,
then command-line overrides. Profiles separate remembered account sessions;
they are not account or character identifiers. Browser builds use their page
origin for both game and auth routes, plus the packaged database. Clearing site
data removes the remembered login, while the server account and its character
roster remain recoverable by signing in. The public account origin must match
the module's compiled trusted issuer and the auth service configuration.

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
`deploy/compose.yaml` pins Nginx **1.28.0 Alpine** by digest and gives the
game, auth and Web services separate CPU/memory/log limits. Auth uses
`auth/Dockerfile`, pinned Node 24.20.0 and Better Auth 1.7.3, running as UID 1000.
Its internal port 3219 is not published to the host; `AUTH_TRUST_PROXY=true`
accepts only the isolated proxy's overwritten client-IP header.

| Resource | Scope |
| --- | --- |
| Remote directory | `/opt/metin2-godotime` |
| Compose project | `metin2-godotime` |
| Public game endpoint | TCP `8443`, HTTPS and WSS |
| Public P1 database | `mt2-p1-v4`, selected explicitly in export/deploy commands |
| Retained previous databases | `mt2-accounts-v3` and `mt2-yongan-v2`; stored but not exposed by the P1 proxy |
| Administrative database endpoint | `127.0.0.1:13210` on the VPS only |
| Game persistence | Compose named volume `world` |
| Account/session/key persistence | Separate Compose named volume `accounts`, mounted at auth `/data` |
| Production auth issuer | `https://kcanakdag.com:8443/auth` |
| Static releases | `web/releases/<UTC timestamp>`, selected by `web/current` |
| Staged candidates | `incoming/<UTC timestamp>/`, isolated from active files |
| Cold backups | `backups/<UTC timestamp>/world`, `accounts` and `runtime`, private directories |
| Deployment status | `deployment-status.json` and the candidate's `status.json` |

The deployment host must already have Docker with Compose, SSH access, Bash,
`curl`, `ss`, `timeout`, `flock`, `openssl`, `ufw`, and a valid certificate under
`/etc/letsencrypt/live/<certificate name>/`. The configured deployment reuses
the existing `kcanakdag.com` certificate read-only. The script does not install
Docker or provision/renew certificates. Existing HTTP/HTTPS services on ports
80/443 and other application containers are outside this Compose project.

```sh
make server-build
make export-web SERVER_URL=https://kcanakdag.com:8443 DB=mt2-p1-v4
make deploy DB=mt2-p1-v4
```

Equivalent explicit deployment:

```sh
python3 tools/deploy.py --host root@159.195.213.9 \
  --public-name kcanakdag.com --certificate kcanakdag.com \
  --port 8443 --database mt2-p1-v4 --web-dir dist/web
```

Before SSH, the script verifies every exported file against its build manifest,
including streamed packs, compressed files and the actual-PCK audit. Missing,
modified, extra, hidden or symbolic-link files fail validation. The staged
archive contains the game's module/Web files and ten selected auth build inputs:
Dockerfile, ignore/config files, package/lock files, four service sources and the
HTTP test source. Auth data, secrets, node_modules, caches and unrelated sources
are excluded. The auth image runs its tests during the build and retains only
production dependencies and compiled service code.

Deployment also requires Godot on the local workstation (`--godot`, or the
`GODOT` environment variable; default `godot`). A fresh isolated headless
process mounts the actual Web PCK and reads its packaged `client_config.json`
without starting the game or its autoloads. The packaged database must equal
the requested deployment database before any SSH command can run. File hashes
alone do not establish that client configuration and proxy routes agree.

`deploy/apply.sh` takes the game deployment lock, validates certificate/ports,
Compose and Nginx (including the `db` and `auth` upstream names), and builds both
candidate service images before downtime. It stops only this game's DB/auth
services, takes cold data and runtime backups, restarts candidates and checks
the SpacetimeDB issuer-key and auth-secret hashes. Auth must become healthy
before publication. Its SQLite database and encrypted JWT signing keys persist
in the separate account volume.

Publication uses `/data/publisher-v2.toml` and preserves data with
`--delete-data=never`. The account rollout creates `mt2-accounts-v3`, retaining
the old guest database. With matching test exports targeting the new database:

```sh
make deploy DB=mt2-accounts-v3 WEB_DIR=dist/web-test DEPLOY_FLAGS='--allow-test-build'
```

The earlier requested reset was rejected by automatic approval review, so this
rollout creates a separate database without deleting the guest data. Auth
accounts and issuer keys remain persistent. The public proxy switches its exact
game routes to the new database; the retained guest database is no longer the
active public world. Local defaults remain `mt2-yongan-v2`, so public commands
must supply the account database explicitly.

The deployment tool retains an optional `--reset-database` flag, but it is not
used by this rollout. That flag applies `--delete-data=always` only to the staged
game database for that invocation, without removing volumes, auth accounts or
signing keys. A mismatched staged database is rejected before services stop,
and reset is not saved as a future default. Other applications remain outside
this Compose project.

After publication, the script atomically selects the new Web release, recreates
the proxy and verifies HTTPS health, auth health/discovery, database availability
and the served manifest hash. It installs only this game's certificate reload
hook and opens the game port. Sessions may disconnect during restart.

The proxy exposes `/auth/`, the configured database's subscription WebSocket
and exact GET identity/availability route, plus exact POST `/v1/identity` and
`/v1/identity/websocket-token` routes. Other `/v1/` routes are denied, including
publication, administration and HTTP SQL. `/auth/` takes precedence over the
hidden-file rule so discovery remains reachable; it overwrites `X-Real-IP`
and forwarded headers, preserving the service's per-client rate limiting.
The channel-identity response has `Cache-Control: no-store`. Browser WebSocket
tokens may be in the query; URL access logs are disabled and proxy error logs
are restricted. Game reducers still validate account and character authority.

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

Deployment status records phase or `failed:<phase>`, database name and reset mode. A failure before
publication restores previous runtime/image tags where available and resumes
the stopped game/auth services, without automatically restoring their data.
Even a preflight build failure restores image tags before leaving old services
running. The auth secret is never regenerated as a recovery action. A publication
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

`--test-probe` adds the fixed browser/desktop inspection and ordinary-action
interface. It provides no privileged server writes; normal exports omit it.
The development build is explicitly authorized to include this probe.

In newly exported test builds, capture is opt-in at startup. Browser automation
must install `window.mt2ProbeEnabled = true` with a context init script before
loading the page; both standard browser runners do this, including on reload.
Desktop capture activates with a nonempty `--probe-report` or `--probe-commands`
argument. Without activation, the node frees itself before attaching connection
signals, collecting histories, allocating snapshots or exposing the browser command
bridge. This is a performance switch, not a permission boundary; server actions
retain normal authorization. Normal release exports still omit the probe entirely.
Previously exported/published builds retain their old activation behavior until
rebuilt. The current public release includes this optimization.

`tools/test_probe_activation.py --url <test-endpoint> --output <fresh-directory>`
checks both browser startup modes with captures. The account runner's
`--ordinary-reload --field-only --mob-route <route>` additionally transfers the
same account's browser storage (including Godot's IndexedDB) in memory to a clean
context without init scripts. It verifies reentry and keyboard movement through
the independent native client's subscription. Five-second browser animation-frame
cadence samples are reported separately from Godot FPS; short sequential samples
are not a controlled release benchmark. Credential storage is never written to
the report or an extra credentials file.

```sh
make browser-setup
make export-web SERVER_URL=https://kcanakdag.com:8443 DB=mt2-p1-v4 TEST_PROBE=--test-probe
make export-linux SERVER_URL=https://kcanakdag.com:8443 DB=mt2-p1-v4 TEST_PROBE=--test-probe
make deploy DB=mt2-p1-v4 WEB_DIR=dist/web-test DEPLOY_FLAGS=--allow-test-build
.local/venv-dev/bin/python tools/test_browser_accounts.py \
  --url https://kcanakdag.com:8443 --database mt2-p1-v4 \
  --hardware --inventory --panels
```

The account rollout and regular test deployment both preserve existing data.
Both account services and a matching module must be available before running the
clients. The runner creates actual test accounts/characters, uses visible browser
entry controls and an independent rendered Linux export, and records private
results under `.local/browser-accounts/<timestamp>/`. Do not run the public
credentialed qualification against P1 until explicit user approval is granted.
Add `--session-refresh` to verify both real four-minute token-refresh timers;
this extends the run.
`--hardware` uses the
workstation GPU; software-rendered Yongan can be too slow for reliable combat
timing. See [development](development.md#browser-integration-checks).

The older `make test-browser` runner exercises guest gameplay and is retained
for disposable guest-enabled test worlds. It is not account-flow evidence.

## Local P2 progression candidate

P2 is local-only and default-deny. Export qualification uses the disposable
Yongan database `mt2-p2-yongan-20260906`; the separate training-map database
`mt2-p2-progression-20260906` preserves the accepted 298-check headless
progression fixture and is also the target of the still-pending bootstrap
approval. Both use `http://127.0.0.1:13223` through the local issuer
`http://127.0.0.1:8186/auth`. Neither is the public P1 route, and neither may
reuse, reset, or publish over the P1 database. The current generated
client-binding schema is
`c3e5a8acbff528458936815c8a8903830e35a86b7573a1452cc302e011328fb3`; the
Yongan default-deny module WASM SHA-256 is
`c7a9535d10a8642fc55d7b46d92e76512248a9c0d0208ecdc3dfdc05f283d8b8`.

The bindings may contain typed progression rows and narrow admin reducer
metadata. They do not contain a bootstrap identity, grant a capability, expose
private audit data, or add a general evaluator. A normal export must exclude
the local operator CLI and its isolated Godot driver, credentials/tokens,
private reports and logs, MCP bridges, original GR2/Blender/source archives,
and `server/content` trusted definitions. The export helper removes the bridge
and test tree before packaging; its actual-PCK audit enforces these exclusions.

The local default-deny smoke passed 15 two-account checks in
`.local/p2/admin-default-deny-report.json`: independent identities and selected
characters, denial of both typed admin requests, unchanged progression/items,
private feedback, and absence from public chat. The unshipped operator CLI also
recorded its expected bootstrap-required denial with `applied: false` in
`.local/p2/operator-default-deny-report.json`. This is denial evidence only.
The bootstrap-enabled artifact is prepared but unpublished; no capability grant,
operator provisioning, or public P2 qualification has occurred.

Actual local Web/Linux progression-combat qualification passes 199 checks in
`.local/p2/browser-positive-progression-fresh-read/report.json`. Two independent
exports used ordinary movement and Space input for five Wild Dog lives and exact
+15 rewards, rendered the first 75-EXP quarter and +2 potion result, applied VIT
without healing current HP, and preserved the positive state through lifecycle
changes and both real four-minute refresh timers. Browser and native engine
errors were empty. This is local default-deny P2 evidence; the public route still
serves P1, and privileged capability success remains unqualified.

The P2 content rebuild and staged client boundary pass are recorded in
`.local/p2/content-rebuild-report.json` and `.local/p2/readiness-audit.md`.
They validate schema-2 trusted definitions and a current 1,576-file staged
client with no forbidden path prefixes. They are not actual PCK/export evidence.
Fresh Web/Linux P2 exports against `mt2-p2-yongan-20260906`, their PCK audits and
two-client exported-client gameplay now have the bounded evidence above. They do
not qualify public reachability, privileged controls, other classes/content, or
the full P2 milestone.

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
Any legacy guest test use needs a disposable training module compiled with
`MT2_ALLOW_GUESTS=1`. Current account login on Windows remains unverified.
Its hostname expires when the tunnel stops; its old Windows public gameplay test
remains unverified.
The Docker deployment is the current stable-address development path.
See [temporary playtesting](playtesting.md).

## Verification status

Evidence recorded on 2026-09-06:

The table records historical completed gameplay slices and current component checks. The earlier normal release
`20260906T141816112109Z` passed direct browser UI/keyboard and Linux checks
without test instrumentation. The preceding authorized guest release
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
| Account deployment/export tests | 25 tests in `tests/test_deploy_export.py` | Auth packaging, recovery fixtures, scoped reset/default preservation, artifact checks and prevention of remote commands when packaged database inspection fails or mismatches; one existing 10-second shell-fixture timeout passed on isolated retry |
| Auth HTTP and container checks | Four suites in `auth/test/auth.test.ts`; remote image build in `.local/accounts/public-deploy.log` | Real HTTP authentication/JWT/session rules; a separate local container recreation retained a bearer session and identical public JWKS using the same private volume |
| Actual account subscriptions | `.local/accounts/integration-report.json`, 58 checks | Two headless Godot accounts through real auth and SpacetimeDB; private raw roster/state/access/inventory reads, four slots, rejected actions, mutual movement, switching and reconnect |
| Local account browser/Linux | `.local/browser-accounts/20260906-193823/report.json`, 103 checks | Actual entry/menu/inventory/panel controls, independent accounts, mutual movement, rejection, switching/reconnect/reload/logout and real timed token renewal; no browser engine errors |
| Public account browser/Linux | `.local/browser-accounts/20260906-194508/report.json`, 103 checks | Same actual exported-client coverage on HTTPS `mt2-accounts-v3`, including real four-minute renewal with preserved identities/positions; no browser engine errors |
| Current native account UI | `.local/classic-intro/`, `.local/classic-system/` | 27 intro and 19 main-UI checks; menu centering, viewport resizing and actual button clicks |
| Live native editor account flow | `.local/accounts/mcp-select.png`, `mcp-world.png`, `mcp-login-final.png`, `mcp-public-server.png` | Correct project, character creation/preview, Yongan entry with two starter item instances, leave/reentry and login observed; final start screen checks public `mt2-accounts-v3` and shows CH1 Online |
| Current account test exports | `dist/web-test/build-manifest.json`, `dist/linux-test/build-manifest.json` | Actual Web/Linux PCK audits: 684/1,487 files, all 197 UI/map images pixel-verified; fixed test probe present as authorized |
| Actual nginx container validation | Configuration in `.local/accounts/nginx/`; `.local/accounts/public-deploy.log` | Local and deployment Docker `nginx -t` passed with the auth/game proxy configuration |
| Local client-origin proxy | `.local/accounts/local-entry-report.json` | Actual HTTP: auth health, configured database identity and Web index return 200; administrative schema route returns 403 and traversal returns 404 |
| Public account deployment | `.local/accounts/public-deploy.log`, release `20260906T173802450337Z` | Created `mt2-accounts-v3` with `--delete-data=never`, retained guest database/auth/issuer keys, built auth with four passing HTTP suites |
| Public account HTTPS checks | `.local/accounts/public-http-report.json` | Workstation HTTPS: auth health/discovery, public-only JWKS, database identity and served manifest exactly matching the Web export |
| Current P1 publication | `.local/p1/public-deploy.log`, release `20260906T204513591109Z` | Created `mt2-p1-v4` with reset mode `never`, retained auth accounts and issuer keys, and served the verified manifest; public credentialed gameplay qualification remains pending explicit user approval |
| Current source checks | `.local/accounts/final-check.log`, deployment guard checks above | 22 Rust, 81 Python checks verified (79 in full `make check` plus two guard regressions), four auth HTTP suites, all linters and real Godot parser/runtime |
| Current schema legacy gameplay checks | `.local/accounts/legacy-multiplayer.json`, `legacy-combat.json`, `legacy-inventory.json`: 22/19/60 checks | Disposable guest-enabled `mt2-account-legacy`; real subscribed movement/combat, direct account inventory RLS, foreign item rejection and privacy/persistence through reconnect/death; no account login or lobby coverage |
| Previous public map/chat/inventory build | `.local/browser-proof/20260906-174806/report.json`, 45 checks | Independent Chrome/Linux clients, final panel drag/resize geometry, inventory, rejection, reconnect/refresh and no engine errors; no public chat sent |
| Chat-send/WASD regression | `.local/browser-proof/20260906-174144/report.json`, 45 loopback checks | Actual chat delivery to the other subscription and movement after send, Escape, world click and history submission |
| Previous native panels | `.local/classic-panels-ui/`, `.local/classic-map/`, `.local/classic-chat-final/` | 15 UI, 17 map and 22 chat checks with screenshots |
| Previous public native editor | `.local/classic-chat-native-editor/centered-chat.png` | Connected project, bottom-center chat, Escape leaves no focus/visible entry |
| Previous test export/deployment | Web/Linux PCK audits: 582/1,385 files and 160 exact UI/map images; `.local/classic-panels-served-manifest.json` | Served/exported manifests match; fixed test probe explicitly authorized; no MCP/evaluator/tokens/source archives |
| Previous tool checks | 70 passing tool tests and all lint groups | Source/tool validation, separate from rendered client evidence |
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

The preceding public panel run reached the world in 12.52 seconds and recorded
42 FPS in its final sample. The separate loopback chat run reached the world in
8.82 seconds with a final 21 FPS sample. These describe those particular runs;
they are not comparable load benchmarks. The loopback-only `--chat-focus` option
keeps synthetic chat away from public sessions.

The prototype has no large-player load benchmark, complete Metin2 parity or
full database-restore/disaster-recovery verification.
The account implementation passes 58 headless integration checks, 22 Yongan/16
training Rust tests, Clippy and the native UI checks above. The connected native
editor also rendered character selection, entry with two starter item instances
and return to the lobby. The final local and public browser/Linux runs each
pass 103 checks. During the public real-timer test, browser connection time
advanced from 10,857 to 249,002 ms and native time from 64,369 to 304,703 ms;
both accounts retained their identities and positions after renewal.
The additional public headless account-suite run was not executed because
automatic approval review rejected its synthetic credential exchange; the
58-check account report is local evidence. Public HTTP/deployment and browser
checks are recorded separately. Earlier 160-image export audits belong to the
previous fixture; the current 197-image test exports pass exact pixel checks.
