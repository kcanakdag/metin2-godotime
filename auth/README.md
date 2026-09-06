# Game account service

This small Node service handles username/password accounts separately from game
characters. Better Auth owns password hashing, session validation, username
normalization, token signing and rate limiting. It sends no email and has no
social login, password recovery, profile dashboard or OAuth consent flow.

## Run and check

Use Node 24.10 or newer in the Node 24 line:

```sh
cd auth
npm ci
npm test
AUTH_DATA_DIR=../.local/auth AUTH_PORT=3219 npm start
```

`npm test` compiles with strict TypeScript and exercises actual HTTP endpoints on
ephemeral loopback ports, using temporary databases. It checks duplicate
accounts, invalid passwords, case-insensitive login, signed bearer validation,
minimal JWT claims and cryptographic verification, session/JWT expiry, logout,
database/key persistence, request limits and persistent rate limiting. It does
not connect to the game's SpacetimeDB process.

| Setting | Default / purpose |
| --- | --- |
| `AUTH_HOST` | `127.0.0.1`; explicit IP to bind |
| `AUTH_PORT` | `3219`; separate from game and editor tooling |
| `AUTH_ISSUER` | `http://127.0.0.1:3219/auth` using the selected port |
| `AUTH_DATA_DIR` | `data` relative to the working directory |
| `AUTH_TRUST_PROXY` | `false`; enable only behind the project's isolated proxy |

The public issuer is **`https://kcanakdag.com:8443/auth`**. Keep this stable:
SpacetimeDB derives identity from issuer plus subject. HTTPS is required except
for loopback development issuers. With `AUTH_TRUST_PROXY=true`, the reverse proxy
must overwrite `X-Real-IP` with the real connecting client IP and keep this
service private. Otherwise, the socket peer supplies rate-limit identity;
untrusted forwarding headers cannot override it.

On first startup, the service creates a random `auth.secret` with mode `0600`
inside its `0700` data directory. This same secret must survive restarts: it signs
bearer sessions and encrypts Better Auth's private JWT keys. `auth.sqlite` and
its WAL hold accounts, sessions, keys and rate limits. Back up the whole data
directory consistently while stopped; never regenerate its secret to resolve a
login failure. Startup runs the pinned library's additive schema migration and
refuses unsafe or inconsistent schema changes.

## HTTP contract

POST requests use `Content-Type: application/json`. Native clients must send
`Origin: <issuer origin>`, such as `https://kcanakdag.com:8443`; browsers supply
their same-origin header. Origin/CSRF checks remain enabled. There is no
cross-origin access policy and no wildcard CORS exception.

| Method and path | Body / result |
| --- | --- |
| `POST /auth/sign-up/email` | `{username,email,password,name}`; `name` may be the username. Creates account and session. |
| `POST /auth/sign-in/username` | `{username,password,rememberMe}`; returns session and user. |
| `GET /auth/get-session` | Returns `{session,user}` or `null` for an invalid/expired session. |
| `POST /auth/sign-out` | `{}`; revokes the current session and clears its cookies. |
| `GET /auth/token` | Returns `{token}` containing the short-lived game JWT; invalid sessions receive `401`. |
| `GET /auth/jwks` | Public signing keys only; private fields never leave the service. |
| `GET /auth/.well-known/openid-configuration` | Issuer, JWKS URL, signing algorithm and claim metadata. |
| `GET /.well-known/openid-configuration` | Alias to the same metadata; the canonical issuer still ends in `/auth`. |
| `GET /auth/health` | `{status:"ok"}` after initialization. |

Only these paths/methods are exposed. Library account mutation, password reset,
OAuth and arbitrary JWT-signing endpoints are unavailable. Requests have a
16 KiB body limit. Auth responses use `Cache-Control: no-store`; the service
does not log credentials, tokens, request bodies or library exception objects.

After sign-up/sign-in, read the **`set-auth-token` response header**. This signed
bearer token is exposed to browser HTTP clients. Supply it in
`Authorization: Bearer <session token>` for session, JWT and logout requests.
Do not use the unsigned `token` field in the sign-in response body as the bearer
credential: unsigned bearer tokens are rejected. Also capture a replacement
`set-auth-token` header if a session refresh returns one. Godot can use this same
HTTP contract on desktop and Web without depending on cookie access.

Usernames contain 3–24 ASCII letters, digits or underscores and compare case
insensitively. Passwords contain 8–128 characters; hashing is the pinned library's
default. Email is required but is not verified in this milestone. No recovery
claim is made. Remembered sessions last up to 30 days and refresh after one day;
Better Auth's `rememberMe:false` creates its shorter session. The client should
persist bearer credentials only when Remember Me is selected, in its private
account store, and erase them on logout. Never put session credentials in game
snapshots, console output, URLs or export archives.

Sign-in is limited to 5 requests per IP per minute; sign-up to 5 per IP per five
minutes. Limits survive service restarts. A rejection returns `429` and
`X-Retry-After` in seconds. Validation errors use Better Auth's JSON `code` and
`message`; wrong username/password combinations share the same generic error.

## Game token and SpacetimeDB boundary

The Better Auth JWT plugin issues RS256 JWTs with a 2048-bit key. Payloads contain
only `iss`, `aud`, `sub`, `iat` and `exp`: no email, username, password or session
credential. Issuer is the configured stable URL, audience is `mt2-game`, subject
is Better Auth's opaque account ID and lifetime is five minutes. JWT keys remain
encrypted in SQLite using `auth.secret` and persist across container replacement.

This service supplies JWT validation discovery; it is not a general OAuth/OIDC
authorization-code provider. SpacetimeDB **2.8.3** explicitly supports RS256 and
fetches `{issuer}/.well-known/openid-configuration` followed by its `jwks_uri`.
Its own integration fixture advertises only `jwks_uri`. See the pinned
[token validator](https://github.com/clockworklabs/SpacetimeDB/blob/v2.8.3/crates/core/src/auth/token_validation.rs).
Game code must independently require the intended issuer, audience and expiry:
the host accepts multiple issuers and does not enforce this game's audience.

The pinned Godot SDK sends the game JWT as an Authorization header on native
WebSocket connections. Browser WebSockets cannot set that header, so the SDK
uses a `token` query parameter for this short-lived JWT. Keep SDK debug logging
disabled and exclude request query strings from proxy/access logs. The SDK's
`one_time_token` option does not make an explicitly supplied JWT single-use.
Remembered auth session credentials remain in HTTP Authorization headers.

Logout prevents new JWT issuance for that session. Already-issued JWTs remain
cryptographically valid until their five-minute expiry; logging out must also
disconnect the game client. The game connection must obtain fresh JWTs before
expiry and preserve the same account/character on authenticated reconnect.
Actual Godot → SpacetimeDB integration is a separate end-to-end check.

Account-to-character mappings, account state, inventory ownership mappings and
inventory rows have account-identity visibility filters. The `player` table is
public, including offline character names, positions, health and gold. The
client's `online = true` query controls presentation; it does not make those
other player rows private.

JWT expiry rejects gameplay actions and the simulation removes active presence.
Revocation of already-established read subscriptions at expiry/logout has not
been demonstrated. Current row filters use identity alone, so a stale
same-account socket may retain read access unless the host closes it. This is a
source-review concern, not a reproduced runtime result; the pinned
[WebSocket route](https://github.com/clockworklabs/SpacetimeDB/blob/v2.8.3/crates/client-api/src/routes/subscribe.rs)
and [connection handling](https://github.com/clockworklabs/SpacetimeDB/blob/v2.8.3/crates/core/src/client/client_connection.rs)
do not establish an expiry-driven subscription cutoff.
Do not describe session logout as retroactive revocation of all game reads.

From the repository root, `make auth-setup`, `make auth-start` and `make test-auth`
install, run and test this service. `make auth-start` resolves `AUTH_DATA_DIR`
relative to the repository, even though npm runs inside `auth/`. TypeScript
lint includes this service and its HTTP tests.

After publishing an account-aware game module and regenerating bindings, run
the real account/subscription check against an origin that proxies both services:

```sh
make test-accounts SERVER_URL=http://127.0.0.1:8184 DB=mt2-yongan-v2
```

Use a disposable game database with the corresponding compiled issuer. The
runner creates two unique accounts with `example.invalid` emails using normal
sign-up requests, exchanges signed bearer sessions for game JWTs, and starts an
isolated Godot project containing only networking dependencies and smoke tests.
Its credential fixture has mode `0600` inside a private temporary directory;
tokens and passwords are absent from command arguments and sanitized logs.
The fixture is removed and sessions are logged out on completion. Test accounts
and character state remain in their databases for inspection. Repeated runs
respect the service's five-signups-per-five-minutes limit; a `429` requires
waiting for the returned interval. The default report is
`.local/accounts-report.json`; `tools/test_accounts.py --report` overrides it.

The 2026-09-06 loopback run passed 58 checks through real Godot clients and
SpacetimeDB 2.8.3: authentication, private ownership, mutual presence and
movement, rejected actions, character switching, disconnect/reconnect and
preserved inventory. Its report is `.local/accounts/integration-report.json`.
This is headless native networking evidence; rendered/browser input uses the
separate client integration suite.

The public release `20260906T173802450337Z` on database `mt2-accounts-v3` passed
103 checks using rendered Chrome and Linux exports, including both actual
four-minute credential renewals with preserved characters and positions.
Its report is `.local/browser-accounts/20260906-194508/report.json`. The separate
58-check headless suite was not run publicly: automatic approval review blocked
that credential-bearing execution, including its evidence-backed retry. Public
evidence comes from the separately approved browser/native run; the 58-check
headless result above is local only.

## Container and dependency provenance

```sh
docker build -t mt2-auth-dev auth
```

Run the image with a dedicated named volume at `/data`, keep its internal port
private behind the game's HTTPS proxy, and set the public issuer explicitly.
The image runs as Node's unprivileged user (UID 1000); its build runs the HTTP
suite on pinned Node **24.20.0**. The official Node image is pinned by manifest
digest in `Dockerfile`. The final image contains production dependencies and
compiled service code, without tests, source caches, local data or credentials.

| Dependency | Exact version | Terms / source |
| --- | --- | --- |
| Better Auth | `1.7.3` | MIT; [username](https://better-auth.com/docs/plugins/username), [bearer](https://better-auth.com/docs/plugins/bearer), [JWT](https://better-auth.com/docs/plugins/jwt), [rate limits](https://better-auth.com/docs/concepts/rate-limit) |
| better-sqlite3 | `12.11.1` | MIT; supported Better Auth peer range, [upstream](https://github.com/WiseLibs/better-sqlite3) |
| TypeScript | `7.0.2` | Apache-2.0, build only |
| jose | `6.2.12` | MIT; explicit test dependency for verification; Better Auth also depends on jose |
| Node type declarations | `24.13.3` | MIT, build only |
| better-sqlite3 type declarations | `9.6.0` | MIT, build only |

`package-lock.json` pins transitive versions and integrity hashes. Dependency
license files remain inside the deployed npm packages. The SQLite driver has an
upstream deprecated `prebuild-install` dependency; installation and runtime are
tested with its supported prebuilt Node 24 binary, without overriding peer checks.
