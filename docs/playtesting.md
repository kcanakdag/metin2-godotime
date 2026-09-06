# Play together over the Internet

This is the optional **temporary local-server tunnel** workflow. The current
VPS browser deployment and Docker update instructions are in
[distribution](distribution.md); players can use its HTTPS address without
keeping this workstation or a tunnel running.

The host can publish a temporary HTTPS address for the local development map, then build a Windows ZIP containing that address. Your friend extracts the ZIP, runs `MT2Spacetime.exe`, chooses a character name and clicks **Enter world**. The friend needs no VPN, Cloudflare account, Godot installation or server tooling.

## Start a session

Keep the local database running in one terminal:

```sh
make server-start
```

If this is a new checkout, follow the root README's tool and warrior-asset steps
first. This Windows export omits Yongan and needs the training server variant:

```sh
make server-publish SERVER_FEATURES= DB=mt2-training-v2
```

The share launcher requires that existing database; it does not create or replace
one. Always pass `DB=mt2-training-v2` here because the main Make defaults now
select Yongan. The standalone launcher retains its older `mt2-dev-world`
database default. Both use `127.0.0.1:3210`.

In another terminal, install the pinned host tool once and start the public link:

```sh
make share-setup
make share-start DB=mt2-training-v2
```

Keep this second terminal running too. Startup checks the local database, launches a game gateway on loopback port **3211**, and connects `cloudflared` to it. When the public health check passes, the launcher prints a URL such as `https://example-name.trycloudflare.com` and its database name. Use the actual printed URL, not the example.

In a third terminal:

```sh
make share-status
make export-shared
```

Send `dist/windows-x86_64.zip`. `export-shared` verifies the active launcher and public health response before embedding the current URL in `client_config.json`. It uses the same Windows export and asset checks as a normal build. Both players can run that ZIP; a developer using the Godot editor can enter the printed public URL or keep using the existing local database address. All connect to the same database and map.

Keep the host computer awake and connected to the Internet while both the database and share launcher run. The host helper currently supports Linux x86_64. It installs only the pinned binary under the repository's `.cache`; it does not install a system service or change router/firewall settings.

## Check or stop the link

```sh
make share-status
make share-stop
```

`share-status` checks the saved owner's PID, process start time, command and public `/health` response. A leftover state file is not treated as a running server. `share-stop` sends a termination request only to that verified launcher, which closes its gateway and tunnel children. The local SpacetimeDB process and its database stay running. Pressing **Ctrl+C** in the share terminal has the same effect.

The equivalent commands, including custom ports, are:

```sh
python3 tools/share_server.py start \
  --database mt2-training-v2 --server-port 3210 \
  --gateway-port 3211 --metrics-port 3212
python3 tools/share_server.py status
python3 tools/share_server.py url
python3 tools/share_server.py export --wine-smoke
python3 tools/share_server.py stop
```

The launcher uses an outbound HTTP/2 tunnel. Its metrics listener binds only to `127.0.0.1:3212`. Logs and session state are in `.local/playtest/`: inspect `gateway.log` for local proxy errors and `cloudflared.log` for tunnel startup or connectivity errors. If a chosen local port is already occupied, stop the process you own or choose another port; the launcher does not take over existing listeners.

For a new hostname, startup waits for a positive public DNS answer through Cloudflare's JSON DNS-over-HTTPS endpoint before making the first system-resolver health request. This avoids asking a local resolver before the temporary hostname has been published: during testing, the host router cached that early `NXDOMAIN` answer for about 30 minutes. The launcher then uses normal system DNS for the public health check and clients. It changes no resolver configuration. See [Cloudflare's JSON DNS-over-HTTPS API](https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/make-api-requests/dns-json/).

## Addresses and saved characters

A Quick Tunnel receives a temporary hostname. Restarting the share launcher normally produces a new address, so run `make export-shared` again or update the client's server field. A ZIP from an earlier session can still point to an expired hostname. Saved profile settings take precedence over packaged defaults: an existing player should change the server on the connection screen if the old address is still selected.

This development client scopes saved guest identities to **server URL + database + local profile**. Changing the tunnel hostname therefore starts a new identity namespace and usually creates a new character, even when the database is unchanged. Returning to an old URL with its original saved profile uses that profile's existing token. Character names are display names, not account credentials. For lasting characters and repeat sessions, use a stable endpoint and add an account/identity migration strategy before relying on guest profiles.

The link is public: anyone who has the address can join as a guest. The gateway exposes the game's connection routes; it does not turn the URL into a private invitation system.

## What the gateway exposes

`tools/playtest_gateway.py` is the only local service reached by the tunnel. Its route allowlist is:

| Request | Purpose |
| --- | --- |
| `GET /health` | Launcher and public health verification |
| Empty `POST /v1/identity` | Create the guest identity required by the Godot SDK |
| WebSocket upgrade `GET /v1/database/<configured database>/subscribe` | Game subscriptions and reducer messages |

Other database names, administration endpoints and other HTTP routes are rejected. Publishing, deleting databases and direct HTTP SQL access remain local. Game reducers still enforce their own authorization and movement validation because gameplay messages travel over the allowed WebSocket connection.

## Service limits and longer-lived hosting

Cloudflare describes Quick Tunnels as a development service with randomly assigned hostnames and no uptime guarantee. Its documented limit is 200 concurrent in-flight requests; this gateway additionally caps its own connections at 128. Use it for small playtests. See [Cloudflare's Quick Tunnel documentation](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/).

Cloudflare supports WebSocket traffic, but connections can close during network updates or idle periods. If the client reports a lost connection, check the live share status and use **Retry**. A healthy HTTP endpoint alone does not prove that gameplay replication works; verify a real client session too. See [Cloudflare's WebSocket documentation](https://developers.cloudflare.com/network/websockets/).

For a stable address without keeping this PC running, SpacetimeDB Maincloud is an alternative. Its documented setup requires `spacetime login`, followed by publication to `--server maincloud`; clients use `https://maincloud.spacetimedb.com` and the published database name. That is a separate deployment, with its own account and data. See [Maincloud deployment](https://spacetimedb.com/docs/how-to/deploy/maincloud/).

Choose a hosted plan from measured usage. The current [server scheduler](../server/src/lib.rs) runs every 50 ms and updates its simulation clock even when the map is empty. At 20 ticks per second, continuous operation produces **51,840,000 scheduled calls in 30 days**, before player actions. Idle scheduling should be optimized before treating this as an inexpensive permanent world. Check [current Maincloud pricing](https://spacetimedb.com/pricing); this project does not promise that an always-running world fits the free allowance.

## Verification status

On 2026-09-06, the Windows ZIP was rebuilt with the active public HTTPS address and audited for packaged assets, a blank default player name, and absence of saved identities or developer MCP code. A fresh independent Godot SDK client completed guest identity creation, secure WebSocket subscription and `enter_world` through that address. Its token-free evidence is `.local/public-playtest/peer-report.json`. The gateway accepts Cloudflare's empty chunked forwarding of the identity request while rejecting nonempty bodies. Public health, route restrictions, verified TLS edge traffic and launcher stop/restart behavior were checked separately in `.local/playtest/`.

The historical local two-client and graphical Windows-under-Wine playtests
passed. That Windows EXE was not subsequently verified through the temporary
tunnel. The later VPS training-ground browser/Linux test did pass public
two-client visibility, movement, rejection, disconnect/reconnect and browser
refresh; it is separate from Windows execution and does not establish current
Yongan streaming. See [current verification](distribution.md#verification-status)
for the recorded paths and remaining limits. No physical Windows PC was used
for the historical automated evidence.
