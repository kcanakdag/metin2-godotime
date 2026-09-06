# Upstream dependency

Source: https://github.com/flametime/Godot-SpacetimeDB-SDK
Commit: `f6c59d7068e5dacbde0559906746d0a6c5933ffb` (2026-08-08)
Upstream plugin version: **0.3.2**; branch `0.2`. License: MIT (see LICENSE).
Copied directory: `godot-client/addons/SpacetimeDB`.

Verified with standard Godot 4.7.2 and SpacetimeDB 2.8.3. This version uses
`v3.bsatn.spacetimedb`, whose message schema is v2 with message coalescing.
The capitalized directory is intentional: upstream hardcodes this resource path.
No .NET or platform-specific binary is required.

Local changes (keep these when updating):

- `spacetimedb_client.gd`: expose `protocol_error` and `subscription_error` signals,
  allowing the application to stop a failed connection with useful diagnostics.
- `spacetimedb_client.gd`: honor `ConnectionOptions.save_token`.
- `spacetimedb_rest_api.gd`: omit raw authentication response bodies from console
  errors, so unexpected identity responses cannot print a token.

The application owns retries, request timeouts, and scoped identity persistence in
`client/scripts/net/game_connection.gd`. It uses a fresh SDK instance on reconnect
and synchronous BSATN decoding to keep lifecycle transitions on the main thread.
It also preserves the application window-close policy when retiring a socket.
All public subscribed tables must have primary keys. Brotli is unsupported; this
project requests no compression. Original file hashes are in
`upstream-files.sha256.json` to make local changes reviewable.
